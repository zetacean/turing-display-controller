"""Tests para serialización de imágenes."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from turing_display.display.serialize import chunked, image_to_rgb565


def test_chunked_exact_multiple() -> None:
    """Chunks de tamaño exacto."""
    data = b"0123456789"
    assert list(chunked(data, 5)) == [b"01234", b"56789"]


def test_chunked_remainder() -> None:
    """El último chunk es más pequeño si no es múltiplo exacto."""
    data = b"0123456"
    assert list(chunked(data, 3)) == [b"012", b"345", b"6"]


def test_chunked_empty() -> None:
    """Datos vacíos no producen chunks."""
    assert list(chunked(b"", 4)) == []


def test_image_to_rgb565_converts_rgba() -> None:
    """Imágenes RGBA se convierten a RGB."""
    img = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    out = image_to_rgb565(img, endianness="little")
    assert len(out) == 2 * 2 * 2  # width * height * 2 bytes/pixel


def test_image_to_rgb565_converts_p_mode() -> None:
    """Imágenes en modo P se convierten a RGB."""
    img = Image.new("P", (2, 2), 0)
    out = image_to_rgb565(img)
    assert len(out) == 8


def test_image_to_rgb565_little_endian_format() -> None:
    """Verifica que el formato little-endian sea correcto."""
    # Pixel rojo puro (255, 0, 0) → R=31, G=0, B=0 → 0xF800 → little-endian: 0x00 0xF8
    img = Image.new("RGB", (1, 1), (255, 0, 0))
    out = image_to_rgb565(img, endianness="little")
    assert out == b"\x00\xf8"


def test_image_to_rgb565_big_endian_format() -> None:
    """Verifica que el formato big-endian sea correcto."""
    img = Image.new("RGB", (1, 1), (255, 0, 0))
    out = image_to_rgb565(img, endianness="big")
    assert out == b"\xf8\x00"


def test_image_to_rgb565_green_pixel() -> None:
    """Verifica el pixel verde puro."""
    # (0, 255, 0) → R=0, G=63, B=0 → 0x07E0
    img = Image.new("RGB", (1, 1), (0, 255, 0))
    out = image_to_rgb565(img, endianness="little")
    assert out == b"\xe0\x07"


def test_image_to_rgb565_blue_pixel() -> None:
    """Verifica el pixel azul puro."""
    # (0, 0, 255) → R=0, G=0, B=31 → 0x001F
    img = Image.new("RGB", (1, 1), (0, 0, 255))
    out = image_to_rgb565(img, endianness="little")
    assert out == b"\x1f\x00"


def test_image_to_rgb565_dimensions() -> None:
    """El tamaño de salida es width*height*2."""
    img = Image.new("RGB", (10, 5), (0, 0, 0))
    out = image_to_rgb565(img)
    assert len(out) == 100


@pytest.mark.parametrize("endianness", ["little", "big"])
def test_image_to_rgb565_round_trip(endianness: str) -> None:
    """Re-decodificar el RGB565 da aproximadamente el mismo RGB."""
    img = Image.new("RGB", (4, 4), (123, 45, 200))
    raw = image_to_rgb565(img, endianness=endianness)  # type: ignore[arg-type]

    dtype = "<u2" if endianness == "little" else ">u2"
    arr = np.frombuffer(raw, dtype=dtype).reshape((4, 4))

    r = ((arr >> 11) & 0x1F) << 3
    g = ((arr >> 5) & 0x3F) << 2
    b = (arr & 0x1F) << 3
    recovered = np.stack([r, g, b], axis=-1)

    # Tolerancia ±8 por canal por la pérdida de bits LSB
    diff = np.abs(recovered.astype(int) - np.full((4, 4, 3), [123, 45, 200]))
    assert (diff <= 8).all()
