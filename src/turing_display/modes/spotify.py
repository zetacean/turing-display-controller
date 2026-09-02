"""Modo Spotify: muestra la canción en reproducción."""

from __future__ import annotations

import io
import logging
import threading
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

from ..display.fonts import load_font
from .base import RenderContext

logger = logging.getLogger(__name__)


class SpotifyMode:
    """Modo Spotify: renderiza carátula + título + artista.

    Si no hay reproducción activa, muestra un placeholder indicando que
    está en pausa. El ``SpotifyPoller`` dispara el fallback automático
    a slideshow cuando la inactividad supera ``idle_timeout_s``.
    """

    name = "spotify"

    def __init__(
        self,
        width: int = 320,
        height: int = 480,
        cover_max_px: int = 280,
    ) -> None:
        self._width = width
        self._height = height
        self._cover_max_px = cover_max_px
        self._lock = threading.Lock()
        self._current_track: dict[str, Any] | None = None
        self._cover_cache: Image.Image | None = None
        self._cover_url: str | None = None

    def on_enter(self) -> None:
        """Hook de activación."""
        logger.debug("Spotify mode entered")

    def on_exit(self) -> None:
        """Hook de salida: limpia caché de carátula."""
        with self._lock:
            self._cover_cache = None
            self._cover_url = None

    def update_track(self, data: dict[str, Any]) -> None:
        """Actualiza el track actual (llamado por el poller).

        Si la carátula cambió, la descarga en segundo plano en el
        siguiente ``tick``.
        """
        item = data.get("item") or {}
        track = {
            "title": _join_names(item.get("name"), "Unknown Title"),
            "artist": _join_names(
                [a.get("name") for a in item.get("artists", [])], "Unknown Artist"
            ),
            "album": _join_names(item.get("album", {}).get("name"), ""),
            "is_playing": bool(data.get("is_playing")),
            "cover_url": _extract_cover_url(item.get("album", {}).get("images", [])),
        }
        with self._lock:
            self._current_track = track
            if track["cover_url"] != self._cover_url:
                self._cover_cache = None  # forzar re-descarga
                self._cover_url = track["cover_url"]

    def _ensure_cover(self) -> Image.Image | None:
        """Descarga y cachea la carátula si es necesario."""
        with self._lock:
            url = self._cover_url
            cached = self._cover_cache

        if cached is not None or not url:
            return cached

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
            cover = Image.open(io.BytesIO(resp.content)).convert("RGB")
            cover.thumbnail((self._cover_max_px, self._cover_max_px), Image.Resampling.LANCZOS)
            with self._lock:
                self._cover_cache = cover
            return cover
        except (httpx.HTTPError, OSError) as e:
            logger.warning("Cover download failed: %s", e)
            return None

    def tick(self, ctx: RenderContext) -> Image.Image:
        """Renderiza el frame actual del modo Spotify."""
        with self._lock:
            track = self._current_track

        if track is None or not track.get("is_playing"):
            return self._render_paused(ctx.width, ctx.height)

        return self._render_now_playing(track, ctx.width, ctx.height)

    def _render_paused(self, width: int, height: int) -> Image.Image:
        """Placeholder para "pausado".

        Mismo layout horizontal que ``_render_now_playing`` para que la
        transición de pausado → reproduciendo no mueva los elementos.
        """
        h_w, h_h = 480, 240
        img_h = Image.new("RGB", (h_w, h_h), (16, 16, 16))
        draw_h = ImageDraw.Draw(img_h)

        font = load_font(22)
        sub_font = load_font(14)

        assert isinstance(font, ImageFont.BaseImageFont)
        assert isinstance(sub_font, ImageFont.BaseImageFont)

        # Carátula placeholder a la izquierda (cuadrada 240x240 para caber
        # en el canvas horizontal de 240px de alto).
        ph = Image.new("RGB", (240, 240), (16, 16, 16))
        ImageDraw.Draw(ph).text((90, 110), "ART", fill=(150, 150, 150))
        img_h.paste(ph, (0, 0))

        # Texto a la derecha (área 230px ancho = 480 - 250)
        text_w = h_w - 250
        msg = "Spotify en pausa"
        bbox = font.getbbox(msg)
        tw = bbox[2] - bbox[0]
        msg_x = 250 + (text_w - tw) // 2
        msg_y = (h_h - 60) // 2
        draw_h.text((msg_x, msg_y), msg, font=font, fill=(255, 255, 255))

        sub = "Reanuda la música"
        bbox2 = sub_font.getbbox(sub)
        sw = bbox2[2] - bbox2[0]
        sub_x = 250 + (text_w - sw) // 2
        draw_h.text((sub_x, msg_y + 35), sub, font=sub_font, fill=(180, 180, 180))

        # Regla: imagen horizontal → pre-rotar 90 + stretch (fill)
        img_rot = img_h.transpose(Image.Transpose.ROTATE_90)
        return img_rot.resize((width, height), Image.Resampling.LANCZOS)

    def _render_now_playing(self, track: dict[str, Any], width: int, height: int) -> Image.Image:
        """Renderiza carátula (izquierda) + título/artista/álbum (derecha).

        Layout aplicado: el contenido se pinta en un canvas HORIZONTAL
        480×240 (carátula 320 a la izquierda, texto 150 a la derecha),
        luego se pre-rota 90° y se estira a ``width × height`` (regla
        fill+stretch para imágenes horizontales). Cuando el driver
        rota el frame 90° al enviarlo al panel, la carátula queda
        arriba y el texto abajo, ocupando toda la pantalla.
        """
        # Canvas horizontal auxiliar: 480x240
        h_w, h_h = 480, 240
        # La caratula debe caber en h_h (240) de alto. Cuadrada -> 240x240.
        cover_size = h_h  # 240
        text_x = cover_size + 10  # 250
        text_w = h_w - text_x  # 230

        img_h = Image.new("RGB", (h_w, h_h), (15, 15, 25))
        draw_h = ImageDraw.Draw(img_h)

        # Carátula a la izquierda (cuadrada 240x240)
        cover = self._ensure_cover()
        if cover is not None:
            cover_resized = cover.resize((cover_size, cover_size), Image.Resampling.LANCZOS)
            img_h.paste(cover_resized, (0, 0))
        else:
            # Placeholder cuando no hay carátula
            ph = Image.new("RGB", (cover_size, cover_size), (40, 40, 40))
            ImageDraw.Draw(ph).text((90, 110), "ART", fill=(150, 150, 150))
            img_h.paste(ph, (0, 0))

        # Texto a la derecha
        font_label = load_font(14)
        font_value = load_font(18)

        assert isinstance(font_label, ImageFont.BaseImageFont)
        assert isinstance(font_value, ImageFont.BaseImageFont)

        def _draw_centered(draw, y, text, font, fill, area_x, area_w):
            """Centra el texto dentro del área [area_x, area_x+area_w]."""
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            x = area_x + (area_w - tw) // 2
            draw.text((x, y), text, font=font, fill=fill)

        def _truncate_with_ellipsis(text: str, font: ImageFont.BaseImageFont, max_w: int) -> str:
            """Corta el texto y agrega '...' si no cabe en max_w."""
            if font.getbbox(text)[2] - font.getbbox(text)[0] <= max_w:
                return text
            ellipsis = "..."
            ellipsis_w = font.getbbox(ellipsis)[2] - font.getbbox(ellipsis)[0]
            while text and (font.getbbox(text)[2] - font.getbbox(text)[0] + ellipsis_w) > max_w:
                text = text[:-1]
            return text + ellipsis if text else ellipsis

        # Layout vertical: titulo, artista, album (1 linea cada uno)
        line_h = 22
        y = 16
        _draw_centered(draw_h, y, "TITULO", font_label, (150, 150, 150), text_x, text_w)
        y += line_h
        title_text = _truncate_with_ellipsis(track["title"], font_value, text_w)
        _draw_centered(draw_h, y, title_text, font_value, (255, 255, 255), text_x, text_w)

        y += line_h + 8
        _draw_centered(draw_h, y, "ARTISTA", font_label, (150, 150, 150), text_x, text_w)
        y += line_h
        artist_text = _truncate_with_ellipsis(track["artist"], font_value, text_w)
        _draw_centered(draw_h, y, artist_text, font_value, (200, 200, 200), text_x, text_w)

        if track.get("album"):
            y += line_h + 8
            _draw_centered(draw_h, y, "ALBUM", font_label, (150, 150, 150), text_x, text_w)
            y += line_h
            album_text = _truncate_with_ellipsis(track["album"], font_value, text_w)
            _draw_centered(draw_h, y, album_text, font_value, (180, 180, 180), text_x, text_w)

        # Regla: imagen horizontal → pre-rotar 90 + stretch (fill)
        img_rot = img_h.transpose(Image.Transpose.ROTATE_90)
        return img_rot.resize((width, height), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _join_names(value: Any, default: str) -> str:
    """Une una lista de nombres en una cadena o devuelve ``default``."""
    if isinstance(value, list):
        names = [v for v in value if v]
        return ", ".join(names) if names else default
    if isinstance(value, str) and value:
        return value
    return default


def _extract_cover_url(images: list[dict]) -> str | None:
    """Extrae la URL de la imagen más pequeña (300px si existe)."""
    if not images:
        return None
    # Preferir tamaño mediano (~300px) para no descargar demasiado
    target = 300
    best = min(images, key=lambda img: abs(img.get("height", 0) - target))
    return best.get("url")


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Wrap manual por palabras."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur: list[str] = [words[0]]
    for w in words[1:]:
        candidate = " ".join(cur + [w])
        bbox = font.getbbox(candidate)
        if bbox[2] - bbox[0] <= max_w:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
    lines.append(" ".join(cur))
    return lines
