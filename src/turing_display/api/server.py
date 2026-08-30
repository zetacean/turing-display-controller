"""Factoría del servidor FastAPI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from .routes import APIState, build_router
from .spotify_auth import PKCEState, build_spotify_router
from .ws import WSBroadcaster, make_ws_handler

if TYPE_CHECKING:
    from ..spotify_integration import SpotifyClient

logger = logging.getLogger(__name__)


def build_app(
    state: APIState,
    web_dir: Path | None = None,
    spotify_client: "SpotifyClient | None" = None,
) -> FastAPI:
    """Crea la aplicación FastAPI con todas las rutas y WS.

    Parameters
    ----------
    state : APIState
        Estado con controller, overlay, phrases y broadcaster.
    web_dir : Path | None
        Directorio que contiene ``templates/`` y ``static/``.
    spotify_client : SpotifyClient | None
        Cliente de Spotify. Si se proporciona, se exponen los endpoints
        ``/api/spotify/*``.
    """
    from fastapi.templating import Jinja2Templates

    app = FastAPI(
        title="Turing Display Controller",
        version="0.1.0",
        description='API REST + WebSocket para controlar una pantalla Turing Smart Display 3.5".',
    )

    app.state.api_state = state
    app.state.broadcaster = state.broadcaster
    app.state.pkce = PKCEState()

    if web_dir is None:
        web_dir = Path(__file__).parent.parent / "web"
    web_dir = web_dir.resolve()

    templates_dir = web_dir / "templates"
    static_dir = web_dir / "static"

    app.state.templates = Jinja2Templates(directory=str(templates_dir))
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(build_router(state))
    app.include_router(build_spotify_router(spotify_client))

    handler = make_ws_handler(state)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await handler(websocket)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    return app


def create_broadcaster() -> WSBroadcaster:
    """Atajo para construir un broadcaster."""
    return WSBroadcaster()
