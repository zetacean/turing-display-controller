"""Cliente HTTP de Spotify con refresh automático de tokens."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .tokens import TokenBundle, TokenStore

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"  # noqa: S105 - documented public URL
API_BASE = "https://api.spotify.com/v1"

#: Scopes mínimos para leer la reproducción actual.
DEFAULT_SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
]


class SpotifyAuthError(Exception):
    """Error de autenticación o refresh de tokens."""


class SpotifyClient:
    """Cliente asíncrono para la Web API de Spotify.

    Maneja automáticamente el ciclo de vida de los tokens: si el
    ``access_token`` está vencido, usa el ``refresh_token`` para
    obtener uno nuevo antes de cada llamada.
    """

    def __init__(
        self,
        client_id: str,
        redirect_uri: str,
        token_store: TokenStore,
        scopes: list[str] | None = None,
    ) -> None:
        if not client_id:
            raise ValueError("client_id is required")
        if not redirect_uri:
            raise ValueError("redirect_uri is required")
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._scopes = scopes or DEFAULT_SCOPES
        self._tokens = token_store
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(timeout=10.0)

    @property
    def token_store(self) -> TokenStore:
        """Almacén de tokens persistido (acceso público para inicialización)."""
        return self._tokens

    async def init_token_store(self) -> None:
        """Inicializa el almacén de tokens (crea la tabla si no existe)."""
        await self._tokens.init()

    @property
    def scopes(self) -> list[str]:
        """Scopes OAuth solicitados."""
        return list(self._scopes)

    # ------------------------------------------------------------------ #
    # Auth flow
    # ------------------------------------------------------------------ #
    def build_authorize_url(self, code_challenge: str, state: str) -> str:
        """Compone la URL de autorización de Spotify (paso 1 de PKCE)."""
        from urllib.parse import urlencode

        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "scope": " ".join(self._scopes),
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, code_verifier: str) -> TokenBundle:
        """Intercambia el ``code`` recibido en el callback por tokens (paso 2)."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "client_id": self._client_id,
            "code_verifier": code_verifier,
        }
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(TOKEN_URL, data=data)
            if resp.status_code != 200:
                raise SpotifyAuthError(f"Token exchange failed ({resp.status_code}): {resp.text}")
            bundle = TokenStore.from_oauth_response(resp.json())
            await self._tokens.save(bundle)
            return bundle

    async def refresh_tokens(self, refresh_token: str) -> TokenBundle:
        """Renueva el ``access_token`` usando el ``refresh_token``."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id,
        }
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(TOKEN_URL, data=data)
            if resp.status_code != 200:
                raise SpotifyAuthError(f"Token refresh failed ({resp.status_code}): {resp.text}")
            payload = resp.json()
            # Spotify puede o no devolver un nuevo refresh_token
            existing = await self._tokens.load()
            if "refresh_token" not in payload and existing is not None:
                payload["refresh_token"] = existing.refresh_token
            bundle = TokenStore.from_oauth_response(payload)
            await self._tokens.save(bundle)
            return bundle

    async def _get_valid_token(self) -> str:
        """Devuelve un ``access_token`` válido (refresca si es necesario)."""
        async with self._lock:
            bundle = await self._tokens.load()
            if bundle is None:
                raise SpotifyAuthError("Not authenticated: no tokens stored")
            if bundle.is_expired():
                if not bundle.refresh_token:
                    raise SpotifyAuthError("Access token expired and no refresh_token")
                bundle = await self.refresh_tokens(bundle.refresh_token)
            return bundle.access_token

    async def is_authenticated(self) -> bool:
        """Indica si hay tokens persistidos."""
        return (await self._tokens.load()) is not None

    # ------------------------------------------------------------------ #
    # API calls
    # ------------------------------------------------------------------ #
    async def currently_playing(self) -> dict[str, Any] | None:
        """Llama a ``/v1/me/player/currently-playing``.

        Returns
        -------
        dict | None
            Respuesta parseada, o ``None`` si no hay nada reproduciéndose
            (Spotify devuelve 204 en ese caso).
        """
        token = await self._get_valid_token()
        resp = await self._http.get(
            f"{API_BASE}/me/player/currently-playing",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 204:
            return None
        if resp.status_code == 401:
            # Token inválido a pesar de la verificación previa: forzar refresh
            bundle = await self._tokens.load()
            if bundle and bundle.refresh_token:
                bundle = await self.refresh_tokens(bundle.refresh_token)
                resp = await self._http.get(
                    f"{API_BASE}/me/player/currently-playing",
                    headers={"Authorization": f"Bearer {bundle.access_token}"},
                )
        if resp.status_code >= 400:
            raise SpotifyAuthError(f"Spotify API error {resp.status_code}: {resp.text}")
        return resp.json()

    async def close(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._http.aclose()
