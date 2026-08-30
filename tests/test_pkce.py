"""Tests para PKCE, tokens y cliente Spotify (sin red)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from turing_display.spotify_integration import (
    SpotifyClient,
    SpotifyPoller,
    TokenBundle,
    TokenStore,
    derive_code_challenge,
    generate_code_verifier,
)
from turing_display.spotify_integration.client import SpotifyAuthError


# ---------------------------------------------------------------------- #
# PKCE
# ---------------------------------------------------------------------- #
def test_generate_code_verifier_length() -> None:
    """El verifier tiene la longitud correcta."""
    v = generate_code_verifier(64)
    assert len(v) > 64  # base64url expande


def test_generate_code_verifier_validates_range() -> None:
    """Longitudes fuera de [43..128] lanzan ValueError."""
    with pytest.raises(ValueError):
        generate_code_verifier(42)
    with pytest.raises(ValueError):
        generate_code_verifier(129)


def test_code_verifier_is_unique() -> None:
    """Genera verifiers únicos."""
    a = generate_code_verifier()
    b = generate_code_verifier()
    assert a != b


def test_derive_code_challenge_s256() -> None:
    """``S256`` produce un challenge determinístico a partir del verifier."""
    v = generate_code_verifier()
    c1 = derive_code_challenge(v, "S256")
    c2 = derive_code_challenge(v, "S256")
    assert c1 == c2
    assert c1 != v  # debe ser distinto al verifier


def test_derive_code_challenge_plain() -> None:
    """``plain`` devuelve el verifier sin alterar."""
    v = generate_code_verifier()
    assert derive_code_challenge(v, "plain") == v


def test_derive_code_challenge_unknown_method() -> None:
    """Método desconocido lanza ValueError."""
    with pytest.raises(ValueError):
        derive_code_challenge("x", "MD5")


# ---------------------------------------------------------------------- #
# TokenStore
# ---------------------------------------------------------------------- #
async def test_token_store_init(tmp_path: Path) -> None:
    """Inicialización crea la tabla."""
    store = TokenStore(tmp_path / "tokens.db")
    await store.init()
    assert (tmp_path / "tokens.db").exists()


async def test_token_store_save_load(tmp_path: Path) -> None:
    """Guardar y cargar preserva el bundle."""
    store = TokenStore(tmp_path / "tokens.db")
    await store.init()
    bundle = TokenBundle(access_token="abc", refresh_token="xyz", expires_at=9999999999.0)
    await store.save(bundle)

    loaded = await store.load()
    assert loaded is not None
    assert loaded.access_token == "abc"
    assert loaded.refresh_token == "xyz"
    assert loaded.expires_at == 9999999999.0


async def test_token_store_load_empty(tmp_path: Path) -> None:
    """``load`` devuelve ``None`` si no hay tokens."""
    store = TokenStore(tmp_path / "tokens.db")
    await store.init()
    assert await store.load() is None


async def test_token_store_clear(tmp_path: Path) -> None:
    """``clear`` elimina el bundle."""
    store = TokenStore(tmp_path / "tokens.db")
    await store.init()
    await store.save(TokenBundle("a", "b", 1.0))
    await store.clear()
    assert await store.load() is None


async def test_token_store_overwrite(tmp_path: Path) -> None:
    """Guardar dos veces sobrescribe el primer bundle."""
    store = TokenStore(tmp_path / "tokens.db")
    await store.init()
    await store.save(TokenBundle("first", None, 1.0))
    await store.save(TokenBundle("second", None, 2.0))
    loaded = await store.load()
    assert loaded.access_token == "second"


def test_token_bundle_is_expired() -> None:
    """``is_expired`` con margen de 60 s."""
    import time

    bundle = TokenBundle("a", None, time.time() + 120)
    assert not bundle.is_expired()
    bundle = TokenBundle("a", None, time.time() - 1)
    assert bundle.is_expired()


# ---------------------------------------------------------------------- #
# SpotifyClient
# ---------------------------------------------------------------------- #
async def test_spotify_client_requires_config(tmp_path: Path) -> None:
    """Falla si client_id o redirect_uri están vacíos."""
    store = TokenStore(tmp_path / "tokens.db")
    with pytest.raises(ValueError):
        SpotifyClient(client_id="", redirect_uri="http://x", token_store=store)
    with pytest.raises(ValueError):
        SpotifyClient(client_id="abc", redirect_uri="", token_store=store)


async def test_build_authorize_url(tmp_path: Path) -> None:
    """``build_authorize_url`` genera URL con todos los parámetros."""
    store = TokenStore(tmp_path / "tokens.db")
    client = SpotifyClient(client_id="myid", redirect_uri="http://localhost/cb", token_store=store)
    url = client.build_authorize_url(code_challenge="chal123", state="state456")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert "accounts.spotify.com" in parsed.netloc
    assert qs["client_id"] == ["myid"]
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge"] == ["chal123"]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["state"] == ["state456"]
    assert "user-read-currently-playing" in qs["scope"][0]


# ---------------------------------------------------------------------- #
# SpotifyPoller (sin red)
# ---------------------------------------------------------------------- #
def test_poller_initial_state() -> None:
    """El poller no arranca hasta llamar a ``start``."""
    # Creamos un cliente con tokens vacíos; el poller no debería poder llamar
    # a currently_playing porque no hay tokens, pero eso no debe lanzar aquí.
    # Como necesitamos un cliente, usamos un Mock inline.

    class _Stub:
        async def currently_playing(self):
            return None

    poller = SpotifyPoller(_Stub(), poll_interval_s=0.01, idle_timeout_s=0.05)
    assert poller._thread is None  # type: ignore[attr-defined]


def test_poller_triggers_fallback_on_idle() -> None:
    """Cuando no se reproduce nada durante ``idle_timeout_s``, dispara callback."""

    class _Stub:
        async def currently_playing(self):
            return None  # nunca hay reproducción

    called = {"count": 0}

    def on_fallback() -> None:
        called["count"] += 1

    poller = SpotifyPoller(
        _Stub(),
        poll_interval_s=0.01,
        idle_timeout_s=0.05,
        on_idle_fallback=on_fallback,
    )
    poller.start()
    # El poller necesita ver al menos UNA vez "is_playing=True" para iniciar
    # el contador de idle. Lo simulamos manualmente.
    poller._last_playing_ts = 0  # type: ignore[attr-defined]
    import time

    time.sleep(0.1)
    # Sin haber visto reproducción, no debe disparar
    assert called["count"] == 0

    poller._last_playing_ts = time.time() - 1.0  # hace 1 s que "reprodujo"
    poller._process(None)  # procesa respuesta vacía → debe disparar fallback
    assert called["count"] >= 1

    poller.stop()
