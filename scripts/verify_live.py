"""Verificación final end-to-end: API + WebSocket + Display real."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import websockets

from turing_display.api import WSBroadcaster, build_app
from turing_display.api.routes import APIState
from turing_display.controller import Controller
from turing_display.display import create_display
from turing_display.modes import SlideshowMode
from turing_display.modes.base import RenderContext
from turing_display.modes.spotify import SpotifyMode
from turing_display.notifications.overlay import NotificationOverlay
from turing_display.phrases import PhraseRepo


async def run_verification() -> int:
    """Lanza servidor + cliente WS en el mismo proceso y valida el flujo."""
    com_port = "COM5"
    print("[verify] Conectando display...")
    try:
        display = create_display(com_port=com_port)
    except Exception as e:  # noqa: BLE001
        print(f"[verify] ERROR display: {e}")
        return 1

    overlay = NotificationOverlay(default_duration=2.0)
    broadcaster = WSBroadcaster()
    repo = PhraseRepo(Path("data") / "verify_phrases.db")
    await repo.init()
    await repo.add_many(
        [
            {"text": "Frase de prueba E2E", "author": "SmokeTest", "category": "Test"},
            {"text": "Segunda frase del verify", "author": "E2E", "category": "Test"},
        ]
    )

    slideshow = SlideshowMode("./images", transition_ms=2000, width=320, height=480)
    spotify_mode = SpotifyMode(width=320, height=480)
    slideshow.on_enter()

    controller = Controller(
        display=display,
        modes={"slideshow": slideshow, "spotify": spotify_mode, "mix": slideshow},
        overlay=overlay,
        broadcaster=broadcaster,
        default_mode="slideshow",
    )
    controller.set_port(com_port)

    api_state = APIState(
        controller=controller, overlay=overlay, phrases=repo, broadcaster=broadcaster
    )
    app = build_app(api_state)
    print(f"[verify] App construida. Sub_revision={display.sub_revision}")

    # Lanzar uvicorn en hilo
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    time.sleep(2)
    print("[verify] Servidor arrancado en http://127.0.0.1:8765")

    base = "http://127.0.0.1:8765"

    try:
        # 1. Health check
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base}/healthz")
            assert r.status_code == 200, f"healthz failed: {r.status_code}"
            print(f"[verify] [OK] /healthz: {r.json()}")

            # 2. Status
            r = await client.get(f"{base}/api/status")
            body = r.json()
            assert r.status_code == 200
            print(f"[verify] [OK] /api/status: {body['mode']}, brightness={body['brightness']}")

            # 3. Add phrase via REST
            r = await client.post(
                f"{base}/api/phrases",
                json={"phrases": [{"text": "REST frase", "author": "Verify"}]},
            )
            assert r.status_code == 200
            print("[verify] [OK] POST /api/phrases")

            # 4. List phrases
            r = await client.get(f"{base}/api/phrases")
            phrases = r.json()
            assert len(phrases) >= 3, f"expected >=3 phrases, got {len(phrases)}"
            print(f"[verify] [OK] GET /api/phrases: {len(phrases)} frases")

            # 5. Push notification
            r = await client.post(
                f"{base}/api/notify", json={"message": "Hola desde REST", "duration": 2}
            )
            assert r.status_code == 200
            assert overlay.queue_size() == 1
            print("[verify] [OK] POST /api/notify")

            # 6. Change mode via REST
            r = await client.post(f"{base}/api/mode", json={"mode": "spotify"})
            assert r.status_code == 200
            assert controller.current_mode() == "spotify"
            print("[verify] [OK] POST /api/mode spotify")

        # 7. WebSocket: conectar y enviar change_mode
        async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:

            async def _send_and_expect_ack(action: str, payload: dict) -> None:
                await ws.send(json.dumps({"action": action, "payload": payload}))
                for _ in range(15):
                    msg = json.loads(await ws.recv())
                    if msg.get("event") == "ack" and msg.get("payload", {}).get("action") == action:
                        return
                raise AssertionError(f"No se recibió ack de {action}")

            await _send_and_expect_ack("change_mode", {"mode": "slideshow"})
            print("[verify] [OK] WS change_mode")

            await _send_and_expect_ack("push_notification", {"message": "WS push", "duration": 1})
            print("[verify] [OK] WS push_notification")

            await _send_and_expect_ack("add_phrases", {"phrases": [{"text": "WS frase e2e"}]})
            print("[verify] [OK] WS add_phrases")

            await _send_and_expect_ack("update_config", {"values": {"display.brightness": "80"}})
            print("[verify] [OK] WS update_config")

        # 8. Renderizar y enviar frame real al display
        print("[verify] Renderizando y enviando frame al display...")
        ctx = RenderContext(320, 480)
        frame = slideshow.tick(ctx)
        overlay.tick()
        final = overlay.compose(frame)
        controller.send_frame(final)
        print("[verify] [OK] Frame enviado al display")

        # 9. Generar frase y renderizar
        print("[verify] Renderizando frame de frase...")
        # Crear una imagen negra con texto
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (320, 480), (16, 16, 16))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except OSError:
            font = ImageFont.load_default()
        draw.text((20, 200), "Verificacion E2E", font=font, fill=(255, 255, 255))
        controller.send_frame(img)
        print("[verify] [OK] Frame de frase enviado")

        # 10. Limpiar
        await asyncio.sleep(0.5)
        display.screen_off()
        print("[verify] [OK] Pantalla apagada")
        display.close_serial()
        print("[verify] [OK] Puerto cerrado")

        print("\n[OK] VERIFICACIÓN E2E COMPLETADA — todos los flujos operativos")
        return 0

    except Exception as e:  # noqa: BLE001
        print(f"[verify] ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        server.should_exit = True
        server_thread.join(timeout=3)


if __name__ == "__main__":
    sys.exit(asyncio.run(run_verification()))
