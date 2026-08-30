"""Sistema de notificaciones push con cola FIFO y overlay temporal."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from ..display.fonts import load_font

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notification:
    """Una notificación a renderizar en pantalla.

    Attributes
    ----------
    message : str
        Texto a mostrar.
    duration : float
        Segundos que permanece en pantalla antes de desaparecer.
    timestamp : float
        Marca temporal de creación (``time.time()``). Se usa internamente
        para el orden FIFO y para depuración.
    """

    message: str
    duration: float = 5.0
    timestamp: float = field(default_factory=time.time)


class NotificationOverlay:
    """Renderiza notificaciones como overlay sobre cualquier frame.

    El overlay es *thread-safe* y se compone con el frame del modo activo
    mediante :meth:`compose`. Las notificaciones se gestionan a través de
    una cola FIFO interna (:attr:`queue`) y se procesan una a una sin
    solapamientos.
    """

    def __init__(self, default_duration: float = 5.0) -> None:
        self._queue: queue.Queue[Notification] = queue.Queue()
        self._active: Notification | None = None
        self._active_until: float = 0.0
        self._lock = threading.Lock()
        self._default_duration = default_duration

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def push(self, message: str, duration: float | None = None) -> None:
        """Encola una notificación (no bloquea).

        Parameters
        ----------
        message : str
            Texto a mostrar.
        duration : float | None
            Duración en segundos. Si es ``None``, usa ``default_duration``.
        """
        if not message:
            raise ValueError("Notification message must not be empty")
        d = self._default_duration if duration is None else duration
        if d <= 0:
            raise ValueError(f"Duration must be > 0, got {d}")
        self._queue.put(Notification(message=message, duration=d))

    def push_notification(self, notification: Notification) -> None:
        """Encola un objeto :class:`Notification` ya construido."""
        self._queue.put(notification)

    def is_active(self) -> bool:
        """Indica si hay un overlay en pantalla en este momento.

        La lectura es segura sin lock: la única incoherencia posible es
        que el resultado quede obsoleto un instante después. Los métodos
        que mutan (``tick``, ``compose``) usan ``self._lock`` para garantizar
        consistencia durante la escritura.
        """
        if self._active is None:
            return False
        return time.time() < self._active_until

    def current(self) -> Notification | None:
        """Devuelve la notificación activa actual (``None`` si no hay)."""
        if self.is_active():
            return self._active
        return None

    def queue_size(self) -> int:
        """Tamaño actual de la cola de notificaciones pendientes."""
        return self._queue.qsize()

    def tick(self) -> None:
        """PROMUEVE la siguiente notificación de la cola si no hay activa.

        Llamar periódicamente desde el display loop. La promoción solo
        ocurre si la notificación activa anterior ya expiró.
        """
        with self._lock:
            if self._active is not None and time.time() < self._active_until:
                return  # sigue activa
            try:
                self._active = self._queue.get_nowait()
                self._active_until = time.time() + self._active.duration
                logger.info("Notification active: %r", self._active.message)
            except queue.Empty:
                self._active = None
                self._active_until = 0.0

    def force_clear(self) -> None:
        """Fuerza la finalización del overlay actual y vacía la cola."""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._active = None
            self._active_until = 0.0

    # ------------------------------------------------------------------ #
    # Renderizado
    # ------------------------------------------------------------------ #
    def compose(self, base_frame: Image.Image) -> Image.Image:
        """Devuelve el frame final a mostrar.

        Si hay notificación activa, devuelve la notificación como
        **imagen completa** que reemplaza la pantalla entera. Si no,
        devuelve una copia del ``base_frame`` del modo activo.
        """
        # Auto-expirar si corresponde
        with self._lock:
            if self._active is not None and time.time() >= self._active_until:
                self._active = None
                self._active_until = 0.0
            active = self._active

        if active is None:
            return base_frame.copy()

        # La notificación es una imagen completa del tamaño de la pantalla
        return _render_fullscreen(base_frame.size, active.message)

    @property
    def notification_queue(self) -> queue.Queue[Notification]:
        """Acceso directo a la cola FIFO (para tests o extensiones)."""
        return self._queue


# ---------------------------------------------------------------------- #
# Renderizado puro (funciones puras, fáciles de testear)
# ---------------------------------------------------------------------- #
def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Divide ``text`` en líneas que caben en ``max_width`` píxeles."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = [words[0]]
    for word in words[1:]:
        candidate = " ".join(current + [word])
        bbox = font.getbbox(candidate)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    lines.append(" ".join(current))
    return lines


def _render_overlay(base: Image.Image, message: str) -> Image.Image:
    """Compatibilidad hacia atrás: delega en :func:`_render_fullscreen`.

    Mantiene la firma antigua (recibe ``base``) pero ignora el contenido
    del frame y devuelve la notificación como imagen completa. Esto
    evita que la notificación aparezca como capa sobre la imagen de fondo.
    """
    return _render_fullscreen(base.size, message)


def _render_fullscreen(
    size: tuple[int, int],
    message: str,
) -> Image.Image:
    """Genera una imagen completa con la notificación.

    La imagen tiene el tamaño ``size`` (típicamente ``(320, 480)``), fondo
    sólido y el texto centrado. El texto se pinta primero en un canvas
    auxiliar del tamaño exacto del texto (cada línea centrada
    horizontalmente), luego se pre-rota 90° (``rotate(90, expand=True)``)
    y se pega centrado en el frame final. Cuando el driver rota el
    frame al enviarlo al panel, el texto se ve derecho y centrado.
    """
    width, height = size
    frame = Image.new("RGB", (width, height), (20, 20, 20))

    # Fuente
    font = load_font(22)

    assert isinstance(font, ImageFont.BaseImageFont)

    # Ancho disponible para el wrap del texto
    side_padding = 20
    inner_w = width - 2 * side_padding

    # Wrap manual del texto al ancho disponible
    lines = _wrap_text(message, font, inner_w)
    line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1] + 8
    total_h = len(lines) * line_height

    # Calcular el ancho máximo real del texto (para que el canvas tenga
    # el tamaño exacto y el texto quede centrado tras la rotación)
    max_line_w = 0
    for line in lines:
        bbox = font.getbbox(line)
        line_w = bbox[2] - bbox[0]
        if line_w > max_line_w:
            max_line_w = line_w

    # Canvas auxiliar del tamaño EXACTO del texto (no fijo a inner_w)
    canvas_w = max_line_w + 20
    canvas_h = total_h + 10
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (20, 20, 20, 0))
    cdraw = ImageDraw.Draw(canvas)

    # Pintar cada línea centrada horizontalmente dentro del canvas
    y = 5
    for line in lines:
        bbox = font.getbbox(line)
        line_w = bbox[2] - bbox[0]
        x = (canvas_w - line_w) // 2
        cdraw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    # Pre-rotar 90 grados
    rotated = canvas.rotate(90, expand=True)
    rw, rh = rotated.size

    # Pegar centrado en el frame 320x480
    paste_x = width // 2 - rw // 2
    paste_y = height // 2 - rh // 2
    frame.paste(rotated, (paste_x, paste_y), rotated)

    return frame
