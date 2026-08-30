"""Tests de la API REST + WebSocket."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from turing_display.api import WSBroadcaster, build_app
from turing_display.api.routes import APIState
from turing_display.notifications.overlay import NotificationOverlay


# ---------------------------------------------------------------------- #
# Stubs mínimos para no depender del Controller completo
# ---------------------------------------------------------------------- #
@dataclass
class StubController:
    """Sustituto de Controller con la mínima API usada por los endpoints."""

    _mode: str = "slideshow"
    _brightness: int = 50
    _port: str | None = "COM-FAKE"
    _is_playing: bool = False

    def current_mode(self) -> str:
        return self._mode

    def is_playing(self) -> bool:
        return self._is_playing

    def brightness(self) -> int:
        return self._brightness

    def port(self) -> str | None:
        return self._port

    def config_snapshot(self) -> dict:
        return {"display.brightness": str(self._brightness)}

    async def change_mode(self, mode: str, automatic: bool = False) -> None:
        if mode not in ("slideshow", "spotify", "mix"):
            raise ValueError(f"Modo inválido: {mode}")
        self._mode = mode

    async def update_config(self, values: dict) -> None:
        for k, v in values.items():
            if k == "display.brightness":
                self._brightness = int(v)


@dataclass
class StubPhrases:
    """Sustituto mínimo de PhraseRepo."""

    _cache: list[Any] = field(default_factory=list)
    _next_id: int = field(default=1)

    def list_active(self) -> list[Any]:
        return list(self._cache)

    async def add_many(self, items: list[dict]) -> list[int]:
        ids = []
        for item in items:
            ids.append(self._next_id)
            self._next_id += 1
            self._cache.append(
                type(
                    "Phrase",
                    (),
                    {
                        "to_dict": lambda self, i=item, idx=ids[-1]: {
                            "id": idx,
                            "text": i["text"],
                            "author": i.get("author"),
                            "category": i.get("category"),
                        },
                    },
                )()
            )
        return ids

    async def delete(self, phrase_id: int) -> bool:
        for i, p in enumerate(self._cache):
            if p.to_dict()["id"] == phrase_id:
                self._cache.pop(i)
                return True
        return False


# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #
@pytest.fixture
def state() -> APIState:
    """Estado con stubs para los tests de API."""
    overlay = NotificationOverlay(default_duration=1.0)
    controller = StubController()
    phrases = StubPhrases()
    broadcaster = WSBroadcaster()
    return APIState(
        controller=controller,  # type: ignore[arg-type]
        overlay=overlay,
        phrases=phrases,  # type: ignore[arg-type]
        broadcaster=broadcaster,
    )


@pytest.fixture
def client(state: APIState) -> TestClient:
    """Cliente de pruebas FastAPI."""
    app = build_app(state, web_dir=Path(__file__).parent.parent / "src" / "turing_display" / "web")
    return TestClient(app)


# ---------------------------------------------------------------------- #
# Tests REST
# ---------------------------------------------------------------------- #
def test_health(client: TestClient) -> None:
    """El endpoint /healthz responde 200."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_status(client: TestClient) -> None:
    """GET /api/status devuelve el estado actual."""
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "slideshow"
    assert body["brightness"] == 50
    assert body["port"] == "COM-FAKE"


def test_change_mode(client: TestClient) -> None:
    """POST /api/mode cambia el modo."""
    r = client.post("/api/mode", json={"mode": "mix"})
    assert r.status_code == 200
    status = client.get("/api/status").json()
    assert status["mode"] == "mix"


def test_change_mode_invalid(client: TestClient) -> None:
    """POST /api/mode con modo inválido → 400."""
    r = client.post("/api/mode", json={"mode": "invalid"})
    assert r.status_code == 422  # Pydantic valida el Literal


def test_change_mode_missing_mode(client: TestClient) -> None:
    """POST /api/mode sin campo 'mode' → 422."""
    r = client.post("/api/mode", json={})
    assert r.status_code == 422


def test_push_notification(client: TestClient) -> None:
    """POST /api/notify encola una notificación."""
    r = client.post("/api/notify", json={"message": "Hola", "duration": 3})
    assert r.status_code == 200
    status = client.get("/api/status").json()
    assert status["notification_queue_size"] == 1


def test_push_notification_empty_message(client: TestClient) -> None:
    """POST /api/notify con mensaje vacío → 422."""
    r = client.post("/api/notify", json={"message": "", "duration": 3})
    assert r.status_code == 422


def test_get_config(client: TestClient) -> None:
    """GET /api/config devuelve el snapshot."""
    r = client.get("/api/config")
    assert r.status_code == 200
    assert "display.brightness" in r.json()


def test_patch_config(client: TestClient) -> None:
    """PATCH /api/config actualiza valores."""
    r = client.patch("/api/config", json={"values": {"display.brightness": "75"}})
    assert r.status_code == 200
    cfg = client.get("/api/config").json()
    assert cfg["display.brightness"] == "75"


def test_list_phrases_empty(client: TestClient) -> None:
    """GET /api/phrases devuelve lista vacía inicialmente."""
    r = client.get("/api/phrases")
    assert r.status_code == 200
    assert r.json() == []


def test_add_phrases(client: TestClient) -> None:
    """POST /api/phrases añade frases."""
    r = client.post(
        "/api/phrases",
        json={"phrases": [{"text": "Frase de prueba", "author": "Anónimo", "category": "Test"}]},
    )
    assert r.status_code == 200
    phrases = client.get("/api/phrases").json()
    assert len(phrases) == 1
    assert phrases[0]["text"] == "Frase de prueba"
    assert phrases[0]["author"] == "Anónimo"


def test_delete_phrase(client: TestClient) -> None:
    """DELETE /api/phrases/{id} elimina una frase."""
    client.post("/api/phrases", json={"phrases": [{"text": "Temp"}]})
    phrases = client.get("/api/phrases").json()
    assert len(phrases) == 1
    r = client.delete(f"/api/phrases/{phrases[0]['id']}")
    assert r.status_code == 200
    assert client.get("/api/phrases").json() == []


def test_delete_phrase_not_found(client: TestClient) -> None:
    """DELETE de frase inexistente → 404."""
    r = client.delete("/api/phrases/9999")
    assert r.status_code == 404


def test_index_renders(client: TestClient) -> None:
    """GET / renderiza el dashboard."""
    r = client.get("/")
    assert r.status_code == 200
    assert "Turing Display" in r.text


def test_static_served(client: TestClient) -> None:
    """Los archivos estáticos se sirven correctamente."""
    r = client.get("/static/app.js")
    assert r.status_code == 200


# ---------------------------------------------------------------------- #
# Tests WebSocket
# ---------------------------------------------------------------------- #
def test_websocket_connect_and_ack(client: TestClient) -> None:
    """WS: conectar, enviar comando, recibir ack."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"action": "change_mode", "payload": {"mode": "mix"}})
        msg = ws.receive_json()
        assert msg["event"] == "ack"
        assert msg["payload"]["action"] == "change_mode"


def test_websocket_change_mode_broadcasts(client: TestClient) -> None:
    """WS: change_mode emite evento mode_changed."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"action": "change_mode", "payload": {"mode": "spotify"}})
        # Consumir mensajes hasta recibir mode_changed o agotar timeout
        for _ in range(5):
            msg = ws.receive_json()
            if msg["event"] == "mode_changed":
                assert msg["payload"]["mode"] == "spotify"
                break
        else:
            pytest.fail("No se recibió mode_changed")


def test_websocket_push_notification(client: TestClient) -> None:
    """WS: push_notification encola y emite evento."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {"action": "push_notification", "payload": {"message": "WS test", "duration": 2}}
        )
        # Recibir ack
        ack = ws.receive_json()
        assert ack["event"] == "ack"


def test_websocket_invalid_json(client: TestClient) -> None:
    """WS: JSON inválido → mensaje de error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not json")
        msg = ws.receive_json()
        assert msg["event"] == "error"


def test_websocket_unknown_action(client: TestClient) -> None:
    """WS: acción desconocida → error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"action": "invalid_action", "payload": {}})
        msg = ws.receive_json()
        assert msg["event"] == "error"


def test_websocket_add_phrases(client: TestClient) -> None:
    """WS: add_phrases añade frases."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {
                "action": "add_phrases",
                "payload": {"phrases": [{"text": "WS frase", "author": "Test"}]},
            }
        )
        ack = ws.receive_json()
        assert ack["event"] == "ack"


def test_websocket_update_config(client: TestClient) -> None:
    """WS: update_config actualiza valores."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {
                "action": "update_config",
                "payload": {"values": {"display.brightness": "80"}},
            }
        )
        ack = ws.receive_json()
        assert ack["event"] == "ack"
