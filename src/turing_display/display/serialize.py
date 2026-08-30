"""Conversión de imágenes y utilidades de serialización para el protocolo USB-Serial."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

import numpy as np
from PIL import Image

Endianness = Literal["big", "little"]


def chunked(data: bytes, chunk_size: int) -> Iterator[bytes]:
    """Divide ``data`` en fragmentos de ``chunk_size`` bytes.

    Parameters
    ----------
    data : bytes
        Búfer a fragmentar.
    chunk_size : int
        Tamaño máximo de cada fragmento (bytes).

    Yields
    ------
    bytes
        Fragmento de datos. El último puede ser más pequeño.
    """
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]


def image_to_rgb565(image: Image.Image, endianness: Endianness = "little") -> bytes:
    """Convierte una imagen PIL a bytes RGB565.

    La conversión descarta el canal alfa si está presente y reduce la
    profundidad a 5-6-5 bits por canal. Utiliza NumPy para un rendimiento
    significativamente mayor que la conversión en Python puro.

    Parameters
    ----------
    image : PIL.Image.Image
        Imagen fuente. Se convierte automáticamente a ``RGB`` si es necesario.
    endianness : {"little", "big"}
        Orden de bytes del ``uint16`` resultante. La Revisión A del protocolo
        Turing usa ``little``.

    Returns
    -------
    bytes
        Flujo de píxeles empaquetados en RGB565.
    """
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    arr = np.asarray(image)
    # Aplanar alto × ancho en una secuencia de píxeles RGB
    arr = arr.reshape((image.size[1] * image.size[0], -1))

    r = arr[:, 0].astype(np.uint16) >> 3
    g = arr[:, 1].astype(np.uint16) >> 2
    b = arr[:, 2].astype(np.uint16) >> 3

    rgb565 = (r << 11) | (g << 5) | b
    dtype = "<u2" if endianness == "little" else ">u2"
    return rgb565.astype(dtype).tobytes()
