"""Tests para el modo slideshow."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from turing_display.modes.base import RenderContext
from turing_display.modes.slideshow import SlideshowMode


@pytest.fixture
def images_dir(tmp_path: Path) -> Path:
    """Crea un directorio con 3 imágenes de colores distintos."""
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        img = Image.new("RGB", (640, 480), color)
        img.save(tmp_path / f"img{i}.png")
    return tmp_path


def test_slideshow_scans_images(images_dir: Path) -> None:
    """Encuentra todas las imágenes soportadas en el directorio."""
    mode = SlideshowMode(images_dir, transition_ms=1)
    mode.on_enter()
    assert len(mode.images) == 3


def test_slideshow_returns_render(images_dir: Path) -> None:
    """``tick`` devuelve una imagen PIL de tamaño nativo."""
    mode = SlideshowMode(images_dir, transition_ms=1, width=320, height=480)
    mode.on_enter()
    frame = mode.tick(RenderContext(320, 480))
    assert frame.size == (320, 480)
    assert frame.mode == "RGB"


def test_slideshow_cycles_after_transition(images_dir: Path) -> None:
    """Tras ``transition_ms``, avanza al siguiente índice."""
    mode = SlideshowMode(images_dir, transition_ms=80, width=320, height=480)
    mode.on_enter()
    first = mode.tick(RenderContext(320, 480))
    # Capturar color del primer frame
    assert first.getpixel((160, 240)) == (255, 0, 0)
    # Esperar más de transition_ms
    import time

    time.sleep(0.12)
    second = mode.tick(RenderContext(320, 480))
    assert second.getpixel((160, 240)) == (0, 255, 0)
    time.sleep(0.12)
    third = mode.tick(RenderContext(320, 480))
    assert third.getpixel((160, 240)) == (0, 0, 255)


def test_slideshow_wraps_around(images_dir: Path) -> None:
    """El índice vuelve a 0 tras la última imagen."""
    import time

    mode = SlideshowMode(images_dir, transition_ms=30, width=320, height=480)
    mode.on_enter()
    # Forzar índice al final
    mode._index = 2  # type: ignore[attr-defined]
    mode._last_tick_ms = 0  # type: ignore[attr-defined]
    # Primer tick: fija el timestamp sin avanzar
    mode.tick(RenderContext(320, 480))
    time.sleep(0.04)
    # Segundo tick: avanza de 2 → 0 (wrap)
    mode.tick(RenderContext(320, 480))
    assert mode._index == 0  # type: ignore[attr-defined]


def test_slideshow_empty_directory(tmp_path: Path) -> None:
    """Si no hay imágenes, muestra el placeholder."""
    mode = SlideshowMode(tmp_path, transition_ms=1, width=320, height=480)
    mode.on_enter()
    assert mode.images == []
    frame = mode.tick(RenderContext(320, 480))
    # Placeholder con texto "No images found"
    assert frame.size == (320, 480)


def test_slideshow_nonexistent_directory(tmp_path: Path) -> None:
    """Si el directorio no existe, no falla."""
    bogus = tmp_path / "nonexistent"
    mode = SlideshowMode(bogus, transition_ms=1, width=320, height=480)
    mode.on_enter()
    assert mode.images == []
    frame = mode.tick(RenderContext(320, 480))
    assert frame.size == (320, 480)


def test_slideshow_vertical_image_letterboxed(tmp_path: Path) -> None:
    """Una imagen vertical se ajusta con bandas."""
    vertical = Image.new("RGB", (480, 1280), (128, 128, 128))
    vertical.save(tmp_path / "vert.png")
    mode = SlideshowMode(tmp_path, transition_ms=1, width=320, height=480)
    mode.on_enter()
    frame = mode.tick(RenderContext(320, 480))
    assert frame.size == (320, 480)


def test_slideshow_add_image(images_dir: Path) -> None:
    """``add_image`` registra una nueva imagen sin re-escanear."""
    mode = SlideshowMode(images_dir, transition_ms=1, width=320, height=480)
    mode.on_enter()
    initial = len(mode.images)
    new_img = Image.new("RGB", (100, 100), (255, 255, 0))
    new_path = images_dir / "yellow.png"
    new_img.save(new_path)
    mode.add_image(new_path)
    assert len(mode.images) == initial + 1


def test_slideshow_add_image_rejects_non_image(tmp_path: Path) -> None:
    """``add_image`` rechaza archivos no soportados."""
    bogus = tmp_path / "doc.txt"
    bogus.write_text("not an image")
    mode = SlideshowMode(tmp_path, transition_ms=1, width=320, height=480)
    with pytest.raises(ValueError):
        mode.add_image(bogus)


def test_slideshow_caches_images(images_dir: Path) -> None:
    """Las imágenes se cachean en memoria."""
    mode = SlideshowMode(images_dir, transition_ms=1, width=320, height=480)
    mode.on_enter()
    mode.tick(RenderContext(320, 480))
    assert len(mode._cache) == 1  # type: ignore[attr-defined]


def test_slideshow_exit_clears_cache(images_dir: Path) -> None:
    """``on_exit`` libera el caché."""
    mode = SlideshowMode(images_dir, transition_ms=1, width=320, height=480)
    mode.on_enter()
    mode.tick(RenderContext(320, 480))
    mode.on_exit()
    assert mode._cache == {}  # type: ignore[attr-defined]
