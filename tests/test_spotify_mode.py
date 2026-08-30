"""Tests para el modo Spotify (sin red)."""

from __future__ import annotations

import pytest

from turing_display.modes.base import RenderContext
from turing_display.modes.spotify import SpotifyMode, _extract_cover_url, _join_names, _wrap


def test_join_names_string() -> None:
    """Une un string normal."""
    assert _join_names("hola", "X") == "hola"


def test_join_names_empty_string() -> None:
    """String vacío devuelve default."""
    assert _join_names("", "Default") == "Default"


def test_join_names_list() -> None:
    """Une una lista con comas."""
    assert _join_names(["A", "B", "C"], "X") == "A, B, C"


def test_join_names_empty_list() -> None:
    """Lista vacía devuelve default."""
    assert _join_names([], "X") == "X"


def test_extract_cover_url_empty() -> None:
    """Sin imágenes devuelve None."""
    assert _extract_cover_url([]) is None


def test_extract_cover_url_picks_smallest() -> None:
    """Elige la imagen de tamaño cercano a 300px."""
    images = [
        {"url": "huge.jpg", "height": 1000},
        {"url": "small.jpg", "height": 300},
        {"url": "tiny.jpg", "height": 64},
    ]
    assert _extract_cover_url(images) == "small.jpg"


def test_wrap_short() -> None:
    """Texto corto cabe en una línea."""
    from PIL import ImageFont

    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    lines = _wrap("Hola", font, 200)
    assert lines == ["Hola"]


def test_wrap_long() -> None:
    """Texto largo se divide en varias líneas."""
    from PIL import ImageFont

    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    lines = _wrap("Esta es una frase muy larga que no cabe en una línea", font, 80)
    assert len(lines) >= 2


def test_spotify_mode_initializes() -> None:
    """El modo se instancia correctamente."""
    mode = SpotifyMode(width=320, height=480)
    assert mode.name == "spotify"


def test_spotify_mode_tick_paused() -> None:
    """Sin track activo, muestra placeholder de pausa."""
    mode = SpotifyMode(width=320, height=480)
    frame = mode.tick(RenderContext(320, 480))
    assert frame.size == (320, 480)
    assert frame.mode == "RGB"


def test_spotify_mode_update_track() -> None:
    """``update_track`` parsea una respuesta de Spotify."""
    mode = SpotifyMode(width=320, height=480)
    mode.update_track(
        {
            "is_playing": True,
            "item": {
                "id": "track1",
                "name": "Mi Canción",
                "artists": [{"name": "Artista Uno"}, {"name": "Artista Dos"}],
                "album": {
                    "name": "Álbum X",
                    "images": [{"url": "http://x/y.jpg", "height": 300}],
                },
            },
        }
    )
    assert mode._current_track is not None  # type: ignore[attr-defined]
    assert mode._current_track["title"] == "Mi Canción"  # type: ignore[attr-defined]
    assert mode._current_track["artist"] == "Artista Uno, Artista Dos"  # type: ignore[attr-defined]
    assert mode._current_track["cover_url"] == "http://x/y.jpg"  # type: ignore[attr-defined]


def test_spotify_mode_tick_with_track() -> None:
    """Con track activo, devuelve frame de 320x480."""
    mode = SpotifyMode(width=320, height=480)
    mode.update_track(
        {
            "is_playing": True,
            "item": {
                "id": "t",
                "name": "X",
                "artists": [{"name": "A"}],
                "album": {"name": "", "images": []},
            },
        }
    )
    frame = mode.tick(RenderContext(320, 480))
    assert frame.size == (320, 480)


def test_spotify_mode_paused_track() -> None:
    """Si is_playing=False, muestra placeholder."""
    mode = SpotifyMode(width=320, height=480)
    mode.update_track(
        {
            "is_playing": False,
            "item": {
                "id": "t",
                "name": "X",
                "artists": [{"name": "A"}],
                "album": {"name": "Y", "images": []},
            },
        }
    )
    frame = mode.tick(RenderContext(320, 480))
    assert frame.size == (320, 480)


def test_spotify_mode_exit_clears_cache() -> None:
    """``on_exit`` limpia caché de carátula."""
    mode = SpotifyMode(width=320, height=480)
    mode._cover_cache = "fake"  # type: ignore[attr-defined]
    mode._cover_url = "http://x"  # type: ignore[attr-defined]
    mode.on_exit()
    assert mode._cover_cache is None  # type: ignore[attr-defined]
    assert mode._cover_url is None  # type: ignore[attr-defined]
