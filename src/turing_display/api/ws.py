"""Endpoint WebSocket y broadcaster para eventos en tiempo real."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from collections.abc import Callable

    from .routes import APIState

logger = logging.getLogger(__name__)


class WSBroadcaster:
    """Mantiene conexiones WebSocket activas y hace broadcast de eventos.

    Es seguro llamar a :meth:`broadcast` desde cualquier hilo (incluidos
    los del display loop). Internamente delega al loop principal de
    asyncio usando ``call_soon_threadsafe``.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """Registra una nueva conexión WS."""
        await ws.accept()
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        self._connections.add(ws)
        logger.info("WS connected (total=%d)", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        """Elimina la conexión WS del registro."""
        self._connections.discard(ws)
        logger.info("WS disconnected (total=%d)", len(self._connections))

    async def broadcast_async(self, event: str, payload: dict) -> None:
        """Envía un evento a todos los clientes conectados (async)."""
        if not self._connections:
            return
        msg = json.dumps({"event": event, "payload": payload})
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(msg)
            except (WebSocketDisconnect, RuntimeError):
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    def broadcast(self, event: str, payload: dict) -> None:
        """Envía un evento desde cualquier hilo (sync-safe)."""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast_async(event, payload), self._loop)
        except RuntimeError:
            # El loop aún no está listo (race condition al iniciar)
            pass

    @property
    def connection_count(self) -> int:
        """Número de conexiones activas."""
        return len(self._connections)


async def handle_ws(ws: WebSocket, state: "APIState") -> None:
    """Maneja el ciclo de vida de un cliente WebSocket.

    Acepta comandos JSON del cliente y los enruta a las acciones del
    ``APIState``. Emite broadcasts automáticos cuando el estado cambia.
    """
    broadcaster: WSBroadcaster = state.broadcaster
    await broadcaster.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                cmd = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(
                    json.dumps({"event": "error", "payload": {"detail": "Invalid JSON"}})
                )
                continue

            action = cmd.get("action")
            payload = cmd.get("payload", {})
            try:
                if action == "change_mode":
                    mode = payload.get("mode")
                    handled = await state.change_mode(mode)
                elif action == "push_notification":
                    handled = await state.push_notification(
                        message=payload.get("message", ""),
                        duration=float(payload.get("duration", 5.0)),
                    )
                elif action == "update_config":
                    handled = await state.update_config(payload.get("values", payload))
                elif action == "add_phrases":
                    handled = await state.add_phrases(payload.get("phrases", []))
                else:
                    await ws.send_text(
                        json.dumps(
                            {"event": "error", "payload": {"detail": f"Unknown action: {action}"}}
                        )
                    )
                    continue
                if handled:
                    await ws.send_text(json.dumps({"event": "ack", "payload": {"action": action}}))
                else:
                    await ws.send_text(
                        json.dumps(
                            {
                                "event": "error",
                                "payload": {"detail": f"Action not handled: {action}"},
                            }
                        )
                    )
            except (ValueError, KeyError) as e:
                await ws.send_text(json.dumps({"event": "error", "payload": {"detail": str(e)}}))
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(ws)


def make_ws_handler(state: "APIState"):
    """Crea un handler de WebSocket con ``state`` capturado en closure."""

    async def handler(ws: WebSocket) -> None:
        await handle_ws(ws, state)

    return handler
