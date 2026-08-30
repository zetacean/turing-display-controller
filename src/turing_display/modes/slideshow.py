"""Modo slideshow: muestra cíclicamente las fotos de un directorio."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from ..display.renderer import fit_letterbox
from .base import Mode, RenderContext

logger = logging.getLogger(__name__)


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}


class SlideshowMode:
    """Modo slideshow.

    Escanea el directorio configurado al activarse, ordena las imágenes y
    las muestra en orden cíclico. Mantiene un caché en memoria para evitar
    recargar las mismas imágenes en cada tick.
    """

    name = "slideshow"

    def __init__(
        self,
        images_dir: str | Path,
        transition_ms: int = 5000,
        width: int = 320,
        height: int = 480,
    ) -> None:
        self._dir = Path(images_dir)
        self._transition_ms = transition_ms
        self._width = width
        self._height = height
        self._images: list[Path] = []
        self._cache: dict[Path, Image.Image] = {}
        self._lock = threading.Lock()
        self._index = 0
        self._last_tick_ms = 0
        self._placeholder = self._make_placeholder()

    @property
    def images(self) -> list[Path]:
        """Lista inmutable de rutas de imágenes."""
        with self._lock:
            return list(self._images)

    def _scan(self) -> list[Path]:
        """Escanea el directorio en busca de imágenes soportadas."""
        if not self._dir.is_dir():
            logger.warning("Images directory does not exist: %s", self._dir)
            return []
        files: Iterable[Path] = (
            p
            for p in sorted(self._dir.iterdir())
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        return list(files)

    def _make_placeholder(self) -> Image.Image:
        """Placeholder que se muestra cuando no hay imágenes."""
        img = Image.new("RGB", (self._width, self._height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        text = "No images found"
        try:
            font = ImageFont.load_default()
        except OSError:
            font = None
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((self._width - tw) // 2, (self._height - th) // 2),
            text,
            fill=(255, 255, 255),
            font=font,
        )
        return img

    def _load_cached(self, path: Path) -> Image.Image:
        """Carga una imagen desde disco (con caché thread-safe)."""
        with self._lock:
            if path not in self._cache:
                self._cache[path] = Image.open(path)
        # Devolvemos copia para no compartir el objeto cacheado con operaciones posteriores
        return self._cache[path].copy()

    def on_enter(self) -> None:
        """Reescanea el directorio y reinicia el índice."""
        with self._lock:
            self._images = self._scan()
            self._index = 0
            self._last_tick_ms = 0
        logger.info("Slideshow started with %d images", len(self._images))

    def on_exit(self) -> None:
        """Limpia el caché de imágenes."""
        with self._lock:
            self._cache.clear()

    def tick(self, ctx: RenderContext) -> Image.Image:
        """Genera el siguiente frame del slideshow.

        Muestra la imagen actual durante ``transition_ms`` milisegundos antes
        de avanzar al siguiente índice.
        """
        now_ms = _now_ms()

        with self._lock:
            if not self._images:
                return self._placeholder.copy()
            if self._last_tick_ms == 0:
                # Primer tick: mostrar la imagen inicial sin avanzar
                self._last_tick_ms = now_ms
            elif (now_ms - self._last_tick_ms) >= self._transition_ms:
                self._index = (self._index + 1) % len(self._images)
                self._last_tick_ms = now_ms
            current = self._images[self._index]

        image = self._load_cached(current)
        return fit_letterbox(image, ctx.width, ctx.height)

    def add_image(self, path: str | Path) -> None:
        """Añade una imagen al slideshow (recarga desde disco)."""
        p = Path(path)
        if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Not a supported image: {p}")
        with self._lock:
            if p not in self._images:
                self._images.append(p)
                self._images.sort()

    def reload(self) -> None:
        """Reescanea el directorio desde cero."""
        with self._lock:
            self._images = self._scan()
            self._index = 0
            self._last_tick_ms = 0


def _now_ms() -> int:
    """Devuelve el tiempo actual en milisegundos."""
    import time

    return int(time.monotonic() * 1000)


def _ensure_size_matches_image(image_path: str | os.PathLike[str]) -> None:
    """Helper de validación (placeholder, no usado en runtime)."""
    Image.open(image_path).load()
