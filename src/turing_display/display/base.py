"""Interfaz abstracta para drivers de pantalla Turing."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, Optional

import serial
from PIL import Image

if TYPE_CHECKING:
    import queue


class Orientation(IntEnum):
    """Orientación de la pantalla.

    Notas
    -----
    El protocolo Rev A de Turing usa internamente ``portrait = 0`` y
    ``landscape = 2``; las variantes inversas no se soportan en hardware
    para Rev A, por lo que se dejan como referencia pero no se aplican.
    """

    PORTRAIT = 0
    LANDSCAPE = 2
    REVERSE_PORTRAIT = 1


class LcdComm(ABC):
    """Clase base abstracta para todos los drivers de pantalla.

    Define la API común de bajo nivel: conexión serie, comandos simples,
    y envío de imágenes. Las subclases implementan los detalles del
    protocolo específico de cada revisión.

    Attributes
    ----------
    com_port : str
        Puerto serie configurado (``"AUTO"``, ``"COM3"``, ``"/dev/ttyUSB0"``...).
    display_width : int
        Ancho nativo de la pantalla en orientación portrait.
    display_height : int
        Alto nativo de la pantalla en orientación portrait.
    orientation : Orientation
        Orientación activa actual.
    lcd_serial : serial.Serial | None
        Conexión serie abierta (asignada por :meth:`open_serial`).
    update_queue : queue.Queue | None
        Cola opcional para serializar escrituras desde múltiples hilos.
    update_queue_mutex : threading.Lock
        Mutex para ráfagas atómicas de escrituras encoladas.
    """

    def __init__(
        self,
        com_port: str = "AUTO",
        display_width: int = 320,
        display_height: int = 480,
        update_queue: Optional["queue.Queue"] = None,
    ) -> None:
        self.com_port = com_port
        self.display_width = display_width
        self.display_height = display_height
        self.orientation = Orientation.PORTRAIT
        self.lcd_serial: serial.Serial | None = None
        self.update_queue: Optional["queue.Queue"] = update_queue
        self.update_queue_mutex = threading.Lock()

    # ------------------------------------------------------------------ #
    # Propiedades derivadas
    # ------------------------------------------------------------------ #
    def get_width(self) -> int:
        """Devuelve el ancho efectivo según la orientación activa."""
        return self.display_width

    def get_height(self) -> int:
        """Devuelve el alto efectivo según la orientación activa."""
        return self.display_height

    # ------------------------------------------------------------------ #
    # Ciclo de vida de la conexión serie
    # ------------------------------------------------------------------ #
    @abstractmethod
    def open_serial(self) -> None:
        """Abre la conexión serie. Debe reintentar ante fallos transitorios."""
        raise NotImplementedError

    def close_serial(self) -> None:
        """Cierra la conexión serie si está abierta."""
        if self.lcd_serial is not None:
            self.lcd_serial.close()
            self.lcd_serial = None

    def serial_write(self, data: bytes) -> None:
        """Escribe datos directamente al puerto serie.

        Parameters
        ----------
        data : bytes
            Búfer a enviar.

        Raises
        ------
        AssertionError
            Si la conexión serie no está abierta.
        """
        if self.lcd_serial is None:
            raise RuntimeError("Serial port not open")
        self.lcd_serial.write(data)

    def serial_read(self, size: int) -> bytes:
        """Lee hasta ``size`` bytes del puerto serie."""
        if self.lcd_serial is None:
            raise RuntimeError("Serial port not open")
        return self.lcd_serial.read(size)

    def serial_flush_input(self) -> None:
        """Descarta cualquier dato pendiente en el búfer de entrada."""
        if self.lcd_serial is not None:
            self.lcd_serial.reset_input_buffer()

    # ------------------------------------------------------------------ #
    # API pública de control
    # ------------------------------------------------------------------ #
    @abstractmethod
    def initialize_comm(self) -> None:
        """Inicializa la comunicación (handshake HELLO, configuración)."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reinicia la pantalla. Puede provocar reconexión."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Limpia la pantalla a blanco."""
        raise NotImplementedError

    @abstractmethod
    def screen_off(self) -> None:
        """Apaga la pantalla."""
        raise NotImplementedError

    @abstractmethod
    def screen_on(self) -> None:
        """Enciende la pantalla."""
        raise NotImplementedError

    @abstractmethod
    def set_brightness(self, level: int) -> None:
        """Ajusta el brillo.

        Parameters
        ----------
        level : int
            Nivel en porcentaje [0..100].
        """
        raise NotImplementedError

    @abstractmethod
    def set_orientation(self, orientation: Orientation) -> None:
        """Cambia la orientación activa."""
        raise NotImplementedError

    @abstractmethod
    def display_pil_image(self, image: Image.Image) -> None:
        """Envía una imagen PIL al LCD completo."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Auto-detección
    # ------------------------------------------------------------------ #
    @staticmethod
    def auto_detect_com_port() -> Optional[str]:
        """Devuelve el primer puerto serie que parezca una pantalla Turing.

        Returns
        -------
        str | None
            Nombre del dispositivo (``"/dev/ttyUSB0"``, ``"COM3"``...) o
            ``None`` si no se detecta ninguno.
        """
        return None
