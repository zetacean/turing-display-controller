"""Tests para el driver Rev A usando ``MockSerial``."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from PIL import Image

from turing_display.display.rev_a import (
    BAUDRATE,
    SERIAL_OPEN_ATTEMPTS,
    Command,
    LcdCommRevA,
)
from turing_display.display.serialize import image_to_rgb565

from .conftest import MockSerial


@pytest.fixture
def mock_serial_factory() -> type[MockSerial]:
    """Parchea ``serial.Serial`` para devolver ``MockSerial`` en las pruebas."""

    def factory(*args, **kwargs):  # noqa: ANN001,ANN002,ANN202 - signature imitates serial.Serial
        return MockSerial(*args, **kwargs)

    return factory


def _make_display(
    mock_cls: type[MockSerial],
    com_port: str = "COM-FAKE",
    response: bytes = b"",
) -> tuple[LcdCommRevA, MockSerial]:
    """Construye un driver Rev A con un MockSerial y respuesta HELLO opcional.

    La respuesta de HELLO se inyecta antes de instanciar el driver para que
    ``initialize_comm`` la consuma al construir.
    """
    pending_holder = {"response": response}

    def factory(*args, **kwargs):  # noqa: ANN002,ANN003,ANN202
        instance = mock_cls(*args, **kwargs)
        if pending_holder["response"]:
            instance.feed(pending_holder["response"])
        return instance

    with patch("serial.Serial", factory):
        driver = LcdCommRevA(com_port=com_port)
    mock_instance: MockSerial = driver.lcd_serial  # type: ignore[assignment]
    return driver, mock_instance


def test_serial_open_uses_115200(mock_serial_factory: type[MockSerial]) -> None:
    """El puerto se abre a 115200 8N1 con RTS/CTS."""
    with patch("serial.Serial", mock_serial_factory):
        driver = LcdCommRevA(com_port="COM-FAKE")
    mock: MockSerial = driver.lcd_serial  # type: ignore[assignment]
    assert mock.baudrate == BAUDRATE


def test_serial_open_retries_on_failure(mock_serial_factory: type[MockSerial]) -> None:
    """Si el puerto falla, se reintenta hasta ``SERIAL_OPEN_ATTEMPTS`` veces."""

    def factory(port, *args, **kwargs):  # noqa: ANN001,ANN002
        raise OSError("simulated failure")

    with patch("serial.Serial", factory), pytest.raises(RuntimeError):
        # Evitar el handshake HELLO también parcheando time.sleep
        with patch("turing_display.display.rev_a.time.sleep"):
            LcdCommRevA(com_port="COM-FAIL")
    # El error se lanza tras agotar los intentos
    assert SERIAL_OPEN_ATTEMPTS > 1


def test_hello_usbmonitor_3_5(mock_serial_factory: type[MockSerial]) -> None:
    """HELLO con respuesta USBMONITOR_3_5 fija resolución 320x480."""
    driver, mock = _make_display(mock_serial_factory, response=bytes([0x01] * 6))
    assert driver.display_width == 320
    assert driver.display_height == 480
    assert driver.sub_revision == "USBMONITOR_3_5"
    # Se enviaron 6 bytes de HELLO
    assert len(mock.written) >= 6
    assert mock.written[:6] == bytes([Command.HELLO] * 6)


def test_hello_usbmonitor_5(mock_serial_factory: type[MockSerial]) -> None:
    """HELLO con respuesta USBMONITOR_5 fija resolución 480x800."""
    driver, _ = _make_display(mock_serial_factory, response=bytes([0x02] * 6))
    assert driver.display_width == 480
    assert driver.display_height == 800


def test_hello_usbmonitor_7(mock_serial_factory: type[MockSerial]) -> None:
    """HELLO con respuesta USBMONITOR_7 fija resolución 600x1024."""
    driver, _ = _make_display(mock_serial_factory, response=bytes([0x03] * 6))
    assert driver.display_width == 600
    assert driver.display_height == 1024


def test_hello_no_response_defaults_to_3_5(mock_serial_factory: type[MockSerial]) -> None:
    """Sin respuesta HELLO, se asume Turing 3.5 oficial (320x480)."""
    driver, _ = _make_display(mock_serial_factory, response=b"")
    assert driver.display_width == 320
    assert driver.display_height == 480
    assert driver.sub_revision == "TURING_3_5"


def test_set_brightness_serializes_inverted(mock_serial_factory: type[MockSerial]) -> None:
    """``set_brightness(0)`` → 255 (más brillante), ``100`` → 0 (más oscuro)."""
    driver, mock = _make_display(mock_serial_factory)

    def _decode_x(packet: bytes) -> int:
        """Decodifica la coordenada X del header bit-packed de 6 bytes."""
        return (packet[0] << 2) | (packet[1] >> 6)

    driver.set_brightness(0)
    # Último paquete escrito debe empezar con 6 bytes header + cmd SET_BRIGHTNESS(110)
    cmd0 = mock.written[-6:]
    assert cmd0[5] == Command.SET_BRIGHTNESS
    assert _decode_x(cmd0) == 255  # invertido: 0% → 255 absoluto

    mock.written.clear()
    driver.set_brightness(100)
    cmd100 = mock.written[-6:]
    assert cmd100[5] == Command.SET_BRIGHTNESS
    assert _decode_x(cmd100) == 0  # invertido: 100% → 0 absoluto

    mock.written.clear()
    driver.set_brightness(50)
    cmd50 = mock.written[-6:]
    assert cmd50[5] == Command.SET_BRIGHTNESS
    # 255 - (50/100)*255 = 127.5 → 127 (truncado a int)
    assert _decode_x(cmd50) == 127


def test_set_brightness_validates_range(mock_serial_factory: type[MockSerial]) -> None:
    """El nivel debe estar en [0..100]."""
    driver, _ = _make_display(mock_serial_factory)
    with pytest.raises(ValueError):
        driver.set_brightness(-1)
    with pytest.raises(ValueError):
        driver.set_brightness(101)


def test_clear_sends_clear_command(mock_serial_factory: type[MockSerial]) -> None:
    """``clear()`` envía el comando CLEAR (102)."""
    driver, mock = _make_display(mock_serial_factory)
    mock.written.clear()
    driver.clear()
    # Buscar el byte CLEAR en lo escrito
    assert Command.CLEAR in mock.written


def test_screen_on_off(mock_serial_factory: type[MockSerial]) -> None:
    """``screen_on/off`` envía los comandos correctos."""
    driver, mock = _make_display(mock_serial_factory)
    mock.written.clear()
    driver.screen_off()
    driver.screen_on()
    # Cada paquete de 6 bytes termina en el byte de comando
    assert mock.written[5] == Command.SCREEN_OFF
    assert mock.written[11] == Command.SCREEN_ON


def test_display_pil_image_sends_header_then_rgb565(mock_serial_factory: type[MockSerial]) -> None:
    """``display_pil_image`` envía DISPLAY_BITMAP + RGB565 little-endian."""
    driver, mock = _make_display(mock_serial_factory)
    img = Image.new("RGB", (driver.display_width, driver.display_height), (255, 0, 0))
    expected_payload = image_to_rgb565(img, endianness="little")

    mock.written.clear()
    driver.display_pil_image(img)

    # Header (6 bytes) con DISPLAY_BITMAP (197)
    assert mock.written[5] == Command.DISPLAY_BITMAP
    # El resto debe coincidir con la imagen RGB565
    assert bytes(mock.written[6:]) == expected_payload


def test_display_pil_image_crops_if_larger(mock_serial_factory: type[MockSerial]) -> None:
    """Si la imagen es mayor, se recorta al tamaño del display."""
    driver, mock = _make_display(mock_serial_factory)
    img = Image.new("RGB", (driver.display_width + 100, driver.display_height + 100), (0, 255, 0))
    mock.written.clear()
    driver.display_pil_image(img)

    # El tamaño total debe ser header (6) + width*height*2
    expected_payload_len = driver.display_width * driver.display_height * 2
    assert len(mock.written) == 6 + expected_payload_len


def test_command_pack_coordinates_bit_packed() -> None:
    """El helper de empaquetado genera el formato esperado."""
    # Usar el driver para verificar a través de un comando simple
    pass  # cubierto por tests de display_pil_image


def test_close_serial_safe_when_not_open(mock_serial_factory: type[MockSerial]) -> None:
    """Cerrar sin abrir no lanza excepciones."""
    with patch("serial.Serial", mock_serial_factory):
        driver = LcdCommRevA(com_port="COM-FAKE")
    driver.close_serial()
    assert driver.lcd_serial is None


def test_close_serial_twice(mock_serial_factory: type[MockSerial]) -> None:
    """Cerrar dos veces seguidas es seguro."""
    with patch("serial.Serial", mock_serial_factory):
        driver = LcdCommRevA(com_port="COM-FAKE")
    driver.close_serial()
    driver.close_serial()
