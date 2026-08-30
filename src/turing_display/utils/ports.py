"""Utilidades multiplataforma para puertos serie."""

from __future__ import annotations

import logging
import platform
from typing import Iterator

logger = logging.getLogger(__name__)


def iter_serial_ports() -> Iterator[str]:
    """Itera sobre los nombres de puertos serie disponibles en el sistema.

    Yields
    ------
    str
        Nombre del puerto (``"COM3"``, ``"/dev/ttyUSB0"``...).
    """
    try:
        from serial.tools.list_ports import comports
    except ImportError:
        logger.error("pyserial is required for port enumeration")
        return

    for port in comports():
        yield port.device


def get_os_name() -> str:
    """Devuelve el nombre del sistema operativo (``"Linux"``, ``"Windows"``...)."""
    return platform.system()
