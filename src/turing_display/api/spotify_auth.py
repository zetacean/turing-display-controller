"""Endpoints de autenticación OAuth con Spotify (PKCE)."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..spotify_integration import (
    SpotifyAuthError,
    SpotifyClient,
    derive_code_challenge,
    generate_code_verifier,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PKCEState:
    """Contenedor en memoria del ``code_verifier`` y ``state`` durante el flujo.

    Se almacena en ``app.state`` mientras dure la sesión del servidor.
    """

    def __init__(self) -> None:
        self.verifier: str | None = None
        self.state: str | None = None

    def new(self) -> tuple[str, str]:
        """Genera un par (verifier, state) nuevo y los devuelve."""
        self.verifier = generate_code_verifier()
        self.state = secrets.token_urlsafe(16)
        return self.verifier, self.state


def build_spotify_router(client: SpotifyClient | None) -> APIRouter:
    """Crea el router de endpoints OAuth de Spotify.

    Parameters
    ----------
    client : SpotifyClient | None
        Cliente de Spotify. Si es ``None``, los endpoints devuelven 503.
    """
    router = APIRouter()

    @router.get("/api/spotify/auth/start")
    async def auth_start(request: Request):  # type: ignore[no-untyped-def]
        if client is None:
            raise HTTPException(status_code=503, detail="Spotify not configured")
        pkce: PKCEState = request.app.state.pkce
        verifier, state = pkce.new()
        challenge = derive_code_challenge(verifier, "S256")
        url = client.build_authorize_url(code_challenge=challenge, state=state)
        return RedirectResponse(url=url, status_code=302)

    @router.get("/api/spotify/callback")
    async def auth_callback(request: Request, code: str, state: str):  # type: ignore[no-untyped-def]
        if client is None:
            raise HTTPException(status_code=503, detail="Spotify not configured")
        pkce: PKCEState = request.app.state.pkce
        if pkce.state is None or state != pkce.state:
            raise HTTPException(status_code=400, detail="Invalid state")
        if pkce.verifier is None:
            raise HTTPException(status_code=400, detail="No verifier in progress")
        try:
            await client.exchange_code(code=code, code_verifier=pkce.verifier)
        except SpotifyAuthError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            pkce.verifier = None
            pkce.state = None

        return HTMLResponse(
            "<html><body style='font-family:sans-serif;background:#111;color:#0f0;padding:2rem'>"
            "<h1>✅ Conectado a Spotify</h1>"
            "<p>Puedes cerrar esta ventana y volver al panel.</p>"
            "</body></html>"
        )

    @router.get("/api/spotify/status")
    async def auth_status() -> dict:
        if client is None:
            return {"configured": False, "authenticated": False}
        return {"configured": True, "authenticated": await client.is_authenticated()}

    return router
