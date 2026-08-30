"""Fábrica de drivers de pantalla."""

from __future__ import annotations

import logging
from typing import Optional

from .base import LcdComm
from .rev_a import LcdCommRevA

logger = logging.getLogger(__name__)


def create_display(com_port: str = "AUTO") -> LcdComm:
    """Crea una instancia del driver apropiado para la pantalla conectada.

    En esta versión solo se soporta Revisión A. La función aplica el orden:
        1. Usar el puerto indicado si no es ``"AUTO"``.
        2. Auto-detectar si es ``"AUTO"``.

    Parameters
    ----------
    com_port : str
        Nombre del puerto (``"COM3"``, ``"/dev/ttyUSB0"``) o ``"AUTO"``.

    Returns
    -------
    LcdComm
        Instancia del driver listo para usar.

    Raises
    ------
    RuntimeError
        Si no se puede detectar ni abrir ningún puerto.
    """
    logger.info("Creating display driver (revision: A)")
    display: LcdComm = LcdCommRevA(com_port=com_port)
    logger.info(
        "Display initialized: %dx%d, sub-revision: %s",
        display.display_width,
        display.display_height,
        getattr(display, "sub_revision", "?"),
    )
    return display


def detect_port() -> Optional[str]:
    """Atajo para detectar el puerto sin crear un driver."""
    return LcdCommRevA.auto_detect_com_port()
