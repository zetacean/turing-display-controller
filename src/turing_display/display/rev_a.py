"""Driver para pantallas Turing Smart Screen Revisión A (3.5"/5"/7")."""

from __future__ import annotations

import logging
import threading
import time
from enum import IntEnum
from typing import TYPE_CHECKING, Optional

import serial
from PIL import Image

if TYPE_CHECKING:
    import queue

from .base import LcdComm, Orientation
from .serialize import chunked, image_to_rgb565

logger = logging.getLogger(__name__)

#: Número de reintentos al abrir el puerto serie.
#: La pantalla se resetea al conectar y el puerto puede desaparecer brevemente.
SERIAL_OPEN_ATTEMPTS = 10
SERIAL_OPEN_RETRY_DELAY = 1.0  # segundos

#: Baud-rate fijo del protocolo Rev A.
BAUDRATE = 115200


class Command(IntEnum):
    """Códigos de comando del protocolo Rev A."""

    RESET = 101
    CLEAR = 102
    SCREEN_OFF = 108
    SCREEN_ON = 109
    SET_BRIGHTNESS = 110
    SET_ORIENTATION = 121
    SET_MIRROR = 122
    DISPLAY_PIXELS = 195
    DISPLAY_BITMAP = 197
    HELLO = 69  # identifica sub-revisión (no soportado por oficiales 3.5")


class SubRevision:
    """Sub-revisiones conocidas del protocolo Rev A."""

    TURING_3_5 = "TURING_3_5"
    USBMONITOR_3_5 = "USBMONITOR_3_5"  # 320x480
    USBMONITOR_5 = "USBMONITOR_5"  # 480x800
    USBMONITOR_7 = "USBMONITOR_7"  # 600x1024


# Respuestas de HELLO (6 bytes) por sub-revisión
_HELLO_RESPONSES = {
    bytes([0x01] * 6): (SubRevision.USBMONITOR_3_5, 320, 480),
    bytes([0x02] * 6): (SubRevision.USBMONITOR_5, 480, 800),
    bytes([0x03] * 6): (SubRevision.USBMONITOR_7, 600, 1024),
}


class LcdCommRevA(LcdComm):
    """Driver para pantallas Turing 3.5" y UsbPCMonitor 3.5"/5"/7".

    Protocolo:
        - 115200 baudios, 8N1, RTS/CTS activo.
        - Comandos como paquetes de 6 bytes con coordenadas bit-packed.
        - Imágenes como RGB565 little-endian en chunks de ``width * 8`` bytes.
    """

    def __init__(
        self,
        com_port: str = "AUTO",
        display_width: int = 320,
        display_height: int = 480,
        update_queue: Optional["queue.Queue"] = None,
    ) -> None:
        logger.debug("HW revision: A")
        self.sub_revision: str = SubRevision.TURING_3_5
        self._open_lock = threading.Lock()
        super().__init__(com_port, display_width, display_height, update_queue)
        self.open_serial()
        self.initialize_comm()

    # ------------------------------------------------------------------ #
    # Auto-detección
    # ------------------------------------------------------------------ #
    @staticmethod
    def auto_detect_com_port() -> Optional[str]:
        """Detecta automáticamente el puerto serie de una pantalla Rev A.

        Busca dispositivos con VID/PID ``1A86:5722`` o número de serie
        ``USB35INCHIPSV2``.
        """
        try:
            from serial.tools.list_ports import comports
        except ImportError:
            return None

        for port in comports():
            if port.serial_number == "USB35INCHIPSV2":
                return port.device
            if port.vid == 0x1A86 and port.pid == 0x5722:
                return port.device
        return None

    # ------------------------------------------------------------------ #
    # Conexión serie
    # ------------------------------------------------------------------ #
    def open_serial(self) -> None:
        """Abre el puerto serie con reintentos ante fallos transitorios.

        Si ``com_port == 'AUTO'``, se re-detecta en cada intento porque
        el puerto puede cambiar durante el reset de la pantalla.
        """
        with self._open_lock:
            for attempt in range(1, SERIAL_OPEN_ATTEMPTS + 1):
                port = self.com_port
                if port == "AUTO":
                    detected = self.auto_detect_com_port()
                    if not detected:
                        logger.warning(
                            "Cannot auto-detect COM port (attempt %d/%d)",
                            attempt,
                            SERIAL_OPEN_ATTEMPTS,
                        )
                        time.sleep(SERIAL_OPEN_RETRY_DELAY)
                        continue
                    port = detected
                    logger.debug("Auto-detected COM port: %s", port)

                try:
                    self.lcd_serial = serial.Serial(
                        port=port,
                        baudrate=BAUDRATE,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=1,
                        rtscts=True,
                    )
                    return
                except (serial.SerialException, OSError) as exc:
                    logger.warning(
                        "Cannot open COM port %s: %s (attempt %d/%d)",
                        port,
                        exc,
                        attempt,
                        SERIAL_OPEN_ATTEMPTS,
                    )
                    time.sleep(SERIAL_OPEN_RETRY_DELAY)

            raise RuntimeError(
                f"Cannot open COM port after {SERIAL_OPEN_ATTEMPTS} attempts. "
                "Check that the display is connected."
            )

    # ------------------------------------------------------------------ #
    # Comandos de bajo nivel
    # ------------------------------------------------------------------ #
    def _send_command(
        self,
        cmd: Command,
        x: int = 0,
        y: int = 0,
        ex: int = 0,
        ey: int = 0,
        bypass_queue: bool = False,
    ) -> None:
        """Empaqueta y envía un comando de 6 bytes con coordenadas bit-packed.

        Formato del paquete (6 bytes):
            [0]: x[9:2]
            [1]: x[1:0]<<6 | y[9:4]
            [2]: y[3:0]<<4 | ex[9:6]
            [3]: ex[5:0]<<2 | ey[9:8]
            [4]: ey[7:0]
            [5]: cmd
        """
        buf = bytearray(6)
        buf[0] = (x >> 2) & 0xFF
        buf[1] = (((x & 0x3) << 6) | ((y >> 4) & 0x3F)) & 0xFF
        buf[2] = (((y & 0xF) << 4) | ((ex >> 6) & 0x0F)) & 0xFF
        buf[3] = (((ex & 0x3F) << 2) | ((ey >> 8) & 0x03)) & 0xFF
        buf[4] = ey & 0xFF
        buf[5] = int(cmd) & 0xFF

        if self.update_queue is None or bypass_queue:
            self._write_raw(bytes(buf))
        else:
            with self.update_queue_mutex:
                self.update_queue.put((self._write_raw, [bytes(buf)]))

    def _write_raw(self, data: bytes) -> None:
        """Escribe bytes al puerto serie (con flush en macOS)."""
        if self.lcd_serial is None:
            raise RuntimeError("Serial port not open")
        try:
            self.lcd_serial.write(data)
            import platform

            if platform.system() == "Darwin":
                # macOS requiere flush explícito para evitar corrupción
                self.lcd_serial.flush()
        except serial.SerialTimeoutException:
            logger.warning("(write) Serial timeout - slow down")
        except serial.SerialException as exc:
            logger.error("SerialException on write: %s - reconnecting", exc)
            self.close_serial()
            time.sleep(1)
            self.open_serial()
            if self.lcd_serial is not None:
                self.lcd_serial.write(data)

    # ------------------------------------------------------------------ #
    # Handshake
    # ------------------------------------------------------------------ #
    def _hello(self) -> None:
        """Envía HELLO y ajusta resolución según la respuesta."""
        hello = bytes([Command.HELLO] * 6)
        self._write_raw(hello)
        response = self.serial_read(6)
        self.serial_flush_input()

        match = _HELLO_RESPONSES.get(response)
        if match is not None:
            sub_rev, width, height = match
            self.sub_revision = sub_rev
            self.display_width = width
            self.display_height = height
        else:
            # Los Turing 3.5" oficiales no responden a HELLO
            self.sub_revision = SubRevision.TURING_3_5
            self.display_width = 320
            self.display_height = 480

        logger.debug(
            "HW sub-revision: %s (%dx%d)",
            self.sub_revision,
            self.display_width,
            self.display_height,
        )

    def initialize_comm(self) -> None:
        """Inicializa la comunicación y realiza el HELLO handshake."""
        self._hello()

    # ------------------------------------------------------------------ #
    # Comandos públicos
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """Reinicia la pantalla (puede tardar hasta 5 s y renumerar el puerto)."""
        logger.info("Display reset (COM port may change)")
        self._send_command(Command.RESET, bypass_queue=True)
        self.close_serial()
        time.sleep(5)
        self.open_serial()
        self.initialize_comm()

    def clear(self) -> None:
        """Limpia la pantalla a blanco."""
        # Bug conocido: orientation debe ser PORTRAIT antes del CLEAR
        self.set_orientation(Orientation.PORTRAIT)
        self._send_command(Command.CLEAR)
        self.set_orientation(self.orientation)

    def screen_off(self) -> None:
        """Apaga la pantalla."""
        self._send_command(Command.SCREEN_OFF)

    def screen_on(self) -> None:
        """Enciende la pantalla."""
        self._send_command(Command.SCREEN_ON)

    def set_brightness(self, level: int) -> None:
        """Ajusta el brillo (0..100, 0=brillo máximo, 100=mínimo).

        El protocolo Rev A usa una escala invertida: 0 = más brillante,
        255 = más oscuro.
        """
        if not 0 <= level <= 100:
            raise ValueError(f"Brightness must be in [0..100], got {level}")
        absolute = int(255 - (level / 100) * 255)
        self._send_command(Command.SET_BRIGHTNESS, absolute)

    def set_orientation(self, orientation: Optional[Orientation] = None) -> None:
        """Cambia la orientación enviando el comando ``SET_ORIENTATION``.

        El paquete tiene 11 bytes: 5 de coordenadas + cmd + valor + dimensiones.
        """
        if orientation is None:
            orientation = self.orientation
        self.orientation = orientation

        width = self.get_width()
        height = self.get_height()

        buf = bytearray(11)
        # Header de coordenadas (todo 0)
        buf[5] = Command.SET_ORIENTATION
        buf[6] = (int(orientation) + 100) & 0xFF
        buf[7] = (width >> 8) & 0xFF
        buf[8] = width & 0xFF
        buf[9] = (height >> 8) & 0xFF
        buf[10] = height & 0xFF

        if self.lcd_serial is not None:
            self.lcd_serial.write(bytes(buf))

    def display_pil_image(self, image: Image.Image) -> None:
        """Envía una imagen PIL al LCD completo.

        La imagen debe tener exactamente las dimensiones nativas
        (``display_width × display_height``).
        """
        width = self.get_width()
        height = self.get_height()

        # Asegurar RGB y dimensiones correctas
        if image.mode != "RGB":
            image = image.convert("RGB")
        if image.size != (width, height):
            image = image.crop((0, 0, width, height))

        x1 = width - 1
        y1 = height - 1

        rgb565 = image_to_rgb565(image, endianness="little")

        # Header del bitmap + ráfaga de datos
        self._send_command(Command.DISPLAY_BITMAP, 0, 0, x1, y1)

        if self.update_queue is None:
            for chunk in chunked(rgb565, width * 8):
                self._write_raw(chunk)
        else:
            with self.update_queue_mutex:
                for chunk in chunked(rgb565, width * 8):
                    self.update_queue.put((self._write_raw, [chunk]))

    def __del__(self) -> None:
        """Cierra el puerto serie al destruir la instancia."""
        try:
            self.close_serial()
        except Exception:  # noqa: BLE001 - el destructor no debe lanzar
            pass
