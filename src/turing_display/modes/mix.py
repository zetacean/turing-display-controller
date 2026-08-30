"""Modo Mix: alterna fotos del slideshow y frases del repositorio."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..display.gradients import happy_background
from ..display.renderer import fit_letterbox
from ..phrases.repo import Phrase, PhraseRepo
from .base import Mode, RenderContext
from .slideshow import SlideshowMode

logger = logging.getLogger(__name__)


def _render_phrase(
    phrase: Phrase | None,
    width: int,
    height: int,
    fallback: Image.Image | None = None,
) -> Image.Image:
    """Renderiza una frase centrada en una imagen.

    Si ``phrase`` es ``None``, devuelve el ``fallback`` (o un fondo negro).

    Aplica la regla de orientación del panel: el texto se pinta en un
    canvas horizontal 480×240 y luego se pre-rota 90° + stretch a
    ``width × height``. Cuando el driver rota el frame al enviarlo al
    panel, la frase queda horizontal y centrada.
    """
    if phrase is None:
        if fallback is not None:
            return fallback
        # Fallback: degradado feliz pre-rotado + stretch (regla horizontal)
        img_fb = happy_background(480, 240, seed=hash("fallback") % 6)
        return img_fb.transpose(Image.Transpose.ROTATE_90).resize(
            (width, height), Image.Resampling.LANCZOS
        )

    # Tipografía (con fallback al default)
    try:
        font_text = ImageFont.truetype("arial.ttf", 36)
        font_author = ImageFont.truetype("arial.ttf", 20)
        font_cat = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font_text = ImageFont.load_default()
        font_author = ImageFont.load_default()
        font_cat = ImageFont.load_default()

    # Wrap manual simple por palabras
    def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        cur: list[str] = []
        for w in words:
            candidate = " ".join(cur + [w])
            bbox = font.getbbox(candidate)
            if bbox[2] - bbox[0] <= max_w:
                cur.append(w)
            else:
                if cur:
                    lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return lines or [""]

    # Regla: pintar en canvas horizontal 480x240 (ancho > alto)
    h_w, h_h = 480, 240
    margin = 20
    inner_w = h_w - 2 * margin

    assert isinstance(font_text, ImageFont.FreeTypeFont)
    text_lines = wrap(phrase.text, font_text, inner_w)
    line_h = font_text.getbbox("Ay")[3] - font_text.getbbox("Ay")[1] + 6

    # Posición vertical centrada (considerando también autor/categoría)
    extra_h = 0
    if phrase.author:
        extra_h += 30
    if phrase.category:
        extra_h += 20

    total_h = len(text_lines) * line_h + extra_h
    y = (h_h - total_h) // 2

    # Fondo: degradado feliz en vez de negro plano
    seed = hash(phrase.text) % 6
    img_h = happy_background(h_w, h_h, seed=seed)
    draw_h = ImageDraw.Draw(img_h)

    for line in text_lines:
        bbox = font_text.getbbox(line)
        tw = bbox[2] - bbox[0]
        draw_h.text(((h_w - tw) // 2, y), line, font=font_text, fill=(255, 255, 255))
        y += line_h

    if phrase.author:
        author = f"— {phrase.author}"
        bbox = font_author.getbbox(author)
        aw = bbox[2] - bbox[0]
        draw_h.text(
            ((h_w - aw) // 2, y + 6),
            author,
            font=font_author,
            fill=(255, 255, 255),
        )
        y += 30

    if phrase.category:
        bbox = font_cat.getbbox(f"[{phrase.category}]")
        bw = bbox[2] - bbox[0]
        draw_h.text(
            ((h_w - bw) // 2, y + 4),
            f"[{phrase.category}]",
            font=font_cat,
            fill=(255, 255, 255),
        )

    # Regla: imagen horizontal → pre-rotar 90 + stretch (fill)
    return img_h.transpose(Image.Transpose.ROTATE_90).resize(
        (width, height), Image.Resampling.LANCZOS
    )


class MixMode:
    """Modo Mix: alterna fotos del slideshow y frases del ``PhraseRepo``.

    Estrategia:
        - Muestra una foto durante ``image_ms``.
        - Muestra una frase durante ``phrase_ms``.
        - Cicla hasta agotar imágenes/frases, luego empieza de nuevo.
    """

    name = "mix"

    def __init__(
        self,
        images_dir: str | Path,
        phrases_repo: PhraseRepo,
        image_ms: int = 4000,
        phrase_ms: int = 6000,
        width: int = 320,
        height: int = 480,
    ) -> None:
        self._slideshow = SlideshowMode(
            images_dir, transition_ms=image_ms, width=width, height=height
        )
        self._phrases = phrases_repo
        self._image_ms = image_ms
        self._phrase_ms = phrase_ms
        self._width = width
        self._height = height
        self._phrase_index = 0
        self._showing_phrase = False
        self._last_switch_ms = 0
        self._lock = threading.Lock()

    def on_enter(self) -> None:
        """Activa el slideshow interno y reinicia el ciclo."""
        self._slideshow.on_enter()
        with self._lock:
            self._phrase_index = 0
            self._showing_phrase = False
            self._last_switch_ms = 0

    def on_exit(self) -> None:
        """Libera el caché del slideshow."""
        self._slideshow.on_exit()

    def _current_phrase(self) -> Phrase | None:
        phrases = self._phrases.list_active()
        if not phrases:
            return None
        with self._lock:
            phrase = phrases[self._phrase_index % len(phrases)]
            self._phrase_index += 1
        return phrase

    def tick(self, ctx: RenderContext) -> Image.Image:
        """Genera el siguiente frame del modo Mix."""
        now_ms = int(time.monotonic() * 1000)

        with self._lock:
            if self._last_switch_ms == 0:
                self._last_switch_ms = now_ms
                self._showing_phrase = False
            elapsed = now_ms - self._last_switch_ms
            current_duration = self._phrase_ms if self._showing_phrase else self._image_ms
            if elapsed >= current_duration:
                self._showing_phrase = not self._showing_phrase
                self._last_switch_ms = now_ms

        if self._showing_phrase:
            phrase = self._current_phrase()
            return _render_phrase(phrase, ctx.width, ctx.height)
        return self._slideshow.tick(ctx)

    def set_image_duration(self, ms: int) -> None:
        """Cambia la duración del segmento de imagen."""
        self._image_ms = ms
        self._slideshow._transition_ms = ms  # type: ignore[attr-defined]

    def set_phrase_duration(self, ms: int) -> None:
        """Cambia la duración del segmento de frase."""
        self._phrase_ms = ms
