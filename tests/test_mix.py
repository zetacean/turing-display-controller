"""Tests para el modo Mix."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

from turing_display.modes.base import RenderContext
from turing_display.modes.mix import MixMode, _render_phrase
from turing_display.phrases import Phrase, PhraseRepo


@pytest.fixture
def images_dir(tmp_path: Path) -> Path:
    """Crea un directorio con 2 imágenes."""
    for color in [(255, 0, 0), (0, 0, 255)]:
        Image.new("RGB", (640, 480), color).save(tmp_path / f"{color[0]}.png")
    return tmp_path


@pytest.fixture
async def repo(tmp_path: Path) -> PhraseRepo:
    """Crea un repo de frases con 2 frases."""
    r = PhraseRepo(tmp_path / "phrases.db")
    await r.init()
    await r.add_many(
        [
            {"text": "Frase uno", "author": "A1", "category": "Cat1"},
            {"text": "Frase dos", "author": "A2", "category": "Cat2"},
        ]
    )
    return r


async def test_mix_mode_initializes(images_dir: Path, repo: PhraseRepo) -> None:
    """El modo Mix se puede instanciar y entrar."""
    mode = MixMode(images_dir, repo, image_ms=50, phrase_ms=50, width=320, height=480)
    mode.on_enter()


def test_render_phrase_with_phrase() -> None:
    """``_render_phrase`` devuelve imagen 320x480 con la frase."""
    p = Phrase(id=1, text="Hola mundo", author="Test", category="Demo")
    img = _render_phrase(p, 320, 480)
    assert img.size == (320, 480)
    assert img.mode == "RGB"


def test_render_phrase_none_returns_gradient() -> None:
    """``_render_phrase(None)`` devuelve fondo con degradado feliz (no negro)."""
    img = _render_phrase(None, 320, 480)
    assert img.size == (320, 480)
    # El degradado asegura que NO sea negro plano
    assert img.getpixel((160, 240)) != (0, 0, 0)


def test_render_phrase_with_fallback() -> None:
    """``_render_phrase(None, fallback=...)`` devuelve la imagen fallback."""
    fb = Image.new("RGB", (320, 480), (255, 0, 0))
    img = _render_phrase(None, 320, 480, fallback=fb)
    assert img.getpixel((160, 240)) == (255, 0, 0)


async def test_mix_tick_returns_valid_frame(images_dir: Path, repo: PhraseRepo) -> None:
    """``tick`` devuelve un frame de tamaño nativo."""
    mode = MixMode(images_dir, repo, image_ms=50, phrase_ms=50, width=320, height=480)
    mode.on_enter()
    frame = mode.tick(RenderContext(320, 480))
    assert frame.size == (320, 480)
    assert frame.mode == "RGB"


async def test_mix_alternates_image_and_phrase(images_dir: Path, repo: PhraseRepo) -> None:
    """El modo Mix alterna entre imagen y frase."""
    import time

    mode = MixMode(images_dir, repo, image_ms=100, phrase_ms=100, width=320, height=480)
    mode.on_enter()
    ctx = RenderContext(320, 480)

    # Primer tick: imagen (showing_phrase=False)
    f1 = mode.tick(ctx)
    assert mode._showing_phrase is False  # type: ignore[attr-defined]

    # Pasado image_ms → frase
    time.sleep(0.15)
    f2 = mode.tick(ctx)
    assert mode._showing_phrase is True  # type: ignore[attr-defined]

    # Pasado phrase_ms → imagen otra vez
    time.sleep(0.15)
    f3 = mode.tick(ctx)
    assert mode._showing_phrase is False  # type: ignore[attr-defined]

    # Las frases son distintas de las imágenes (frase = fondo gris oscuro)
    # y las imágenes son colores puros
    assert f1.getpixel((160, 240)) != f2.getpixel((160, 240))


async def test_mix_with_no_images(images_dir: Path, repo: PhraseRepo) -> None:
    """Si no hay imágenes, igualmente muestra frases."""
    empty = images_dir / "subdir"
    empty.mkdir()
    mode = MixMode(empty, repo, image_ms=10, phrase_ms=10, width=320, height=480)
    mode.on_enter()
    ctx = RenderContext(320, 480)

    # Primer tick → imagen vacía (placeholder negro)
    f1 = mode.tick(ctx)
    # Tras image_ms → frase
    import time

    time.sleep(0.02)
    f2 = mode.tick(ctx)
    assert mode._showing_phrase is True  # type: ignore[attr-defined]


async def test_mix_with_no_phrases(images_dir: Path, tmp_path: Path) -> None:
    """Si no hay frases, sólo muestra imágenes."""
    repo = PhraseRepo(tmp_path / "phrases.db")
    await repo.init()
    mode = MixMode(images_dir, repo, image_ms=10, phrase_ms=10, width=320, height=480)
    mode.on_enter()
    ctx = RenderContext(320, 480)
    # Debe seguir mostrando imágenes
    f = mode.tick(ctx)
    assert f.size == (320, 480)


async def test_mix_set_durations(images_dir: Path, repo: PhraseRepo) -> None:
    """``set_image_duration`` y ``set_phrase_duration`` funcionan."""
    mode = MixMode(images_dir, repo, image_ms=100, phrase_ms=100)
    mode.set_image_duration(200)
    mode.set_phrase_duration(300)
    assert mode._image_ms == 200  # type: ignore[attr-defined]
    assert mode._phrase_ms == 300  # type: ignore[attr-defined]


async def test_mix_phrase_cycling(images_dir: Path, repo: PhraseRepo) -> None:
    """Las frases se ciclan a través de las disponibles."""
    mode = MixMode(images_dir, repo, image_ms=10, phrase_ms=10)
    mode.on_enter()
    # Consumir todas las frases y verificar que cicla
    phrases_seen: list[Phrase] = []
    for _ in range(4):
        p = mode._current_phrase()  # type: ignore[attr-defined]
        phrases_seen.append(p)
    # Hay 2 frases; al consumir 4 debemos haber ciclado
    assert phrases_seen[0].text == phrases_seen[2].text
    assert phrases_seen[1].text == phrases_seen[3].text


async def test_mix_exit_clears_cache(images_dir: Path, repo: PhraseRepo) -> None:
    """``on_exit`` libera el caché del slideshow."""
    mode = MixMode(images_dir, repo, image_ms=10, phrase_ms=10, width=320, height=480)
    mode.on_enter()
    mode.tick(RenderContext(320, 480))
    mode.on_exit()
    assert mode._slideshow._cache == {}  # type: ignore[attr-defined]
