"""Tests para el watcher de imágenes (hot-reload)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from turing_display.utils.images_watcher import ImagesWatcher


def test_watcher_starts_and_stops(tmp_path: Path) -> None:
    """Arranca y detiene el watcher correctamente."""
    calls = {"n": 0}

    def on_change() -> None:
        calls["n"] += 1

    w = ImagesWatcher(tmp_path, on_change, debounce_s=0.1)
    w.start()
    assert w._observer is not None  # type: ignore[attr-defined]
    w.stop()
    assert w._observer is None  # type: ignore[attr-defined]


def test_watcher_detects_new_image(tmp_path: Path) -> None:
    """Detecta la creación de una imagen."""
    calls = {"n": 0}

    def on_change() -> None:
        calls["n"] += 1

    w = ImagesWatcher(tmp_path, on_change, debounce_s=0.1)
    w.start()
    try:
        # Crear imagen
        (tmp_path / "test.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        time.sleep(1.0)
        assert calls["n"] >= 1
    finally:
        w.stop()


def test_watcher_ignores_non_image_files(tmp_path: Path) -> None:
    """No dispara callback con archivos no-imagen."""
    calls = {"n": 0}

    def on_change() -> None:
        calls["n"] += 1

    w = ImagesWatcher(tmp_path, on_change, debounce_s=0.1)
    w.start()
    try:
        (tmp_path / "doc.txt").write_text("hello")
        time.sleep(0.5)
        assert calls["n"] == 0
    finally:
        w.stop()


def test_watcher_detects_deletion(tmp_path: Path) -> None:
    """Detecta eliminación de imagen."""
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    calls = {"n": 0}

    def on_change() -> None:
        calls["n"] += 1

    w = ImagesWatcher(tmp_path, on_change, debounce_s=0.1)
    w.start()
    try:
        img.unlink()
        time.sleep(1.0)
        assert calls["n"] >= 1
    finally:
        w.stop()


def test_watcher_debounces(tmp_path: Path) -> None:
    """Múltiples cambios rápidos se consolidan en 1 callback."""
    calls = {"n": 0}

    def on_change() -> None:
        calls["n"] += 1

    w = ImagesWatcher(tmp_path, on_change, debounce_s=0.2)
    w.start()
    try:
        for i in range(5):
            (tmp_path / f"img{i}.png").write_bytes(b"\x89PNG" + b"\x00" * 20)
            time.sleep(0.05)
        time.sleep(0.5)
        # Debe haber menos callbacks que archivos creados
        assert calls["n"] < 5
        assert calls["n"] >= 1
    finally:
        w.stop()


def test_watcher_handles_missing_directory(tmp_path: Path) -> None:
    """Si el directorio no existe, el watcher no arranca pero no falla."""
    bogus = tmp_path / "nonexistent"
    w = ImagesWatcher(bogus, lambda: None)
    w.start()  # no debe lanzar
    assert w._observer is None  # type: ignore[attr-defined]
