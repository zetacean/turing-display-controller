"""Carga de fuentes TTF multiplataforma.

PIL por defecto usa ``ImageFont.load_default()`` cuando no encuentra la
fuente, que es 8x8 px (ilegible en pantalla). Este modulo busca fuentes
del sistema con una lista de fallback.

Orden de busqueda (Windows / Linux / macOS):
    1. Arial / Liberation Sans / Helvetica      (sans-serif clasica)
    2. DejaVu Sans                              (Linux por defecto)
    3. FreeSans                                 (GNU)
    4. Noto Sans / Ubuntu                       (modernas)
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import ImageFont

logger = logging.getLogger(__name__)


# Lista priorizada de nombres de fuente que probamos en orden.
# ``ImageFont.truetype(name)`` busca en el sistema operativo.
_FONT_CANDIDATES: list[str] = [
    # Linux / Debian (paquete fonts-liberation)
    "LiberationSans-Regular.ttf",
    "LiberationSans-Bold.ttf",
    # Linux (paquete fonts-dejavu-core)
    "DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf",
    # Linux (paquete fonts-freefont-ttf)
    "FreeSans.ttf",
    "FreeSansBold.ttf",
    # Linux (paquete fonts-ubuntu)
    "Ubuntu-R.ttf",
    "Ubuntu-B.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/seguiemj.ttf",
    # Generic family names (Pillow los busca via fontconfig)
    "Arial",
    "Helvetica",
    "DejaVu Sans",
    "Liberation Sans",
]


def load_font(size: int, bold: bool = False) -> ImageFont.BaseImageFont:
    """Carga una fuente TTF del sistema con fallback.

    Parameters
    ----------
    size : int
        Tamano en pixeles.
    bold : bool
        Si True, intenta primero las variantes bold.

    Returns
    -------
    PIL.ImageFont.BaseImageFont
        Fuente cargada. Si ninguna candidata funciona, cae a la fuente
        por defecto de PIL (8x8 px, legible solo como ultimo recurso).
    """
    # Si bold, poner las variantes bold primero
    candidates = list(_FONT_CANDIDATES)
    if bold:
        bold_first = [c for c in candidates if "Bold" in c or "Bold" in Path(c).name]
        rest = [c for c in candidates if c not in bold_first]
        candidates = bold_first + rest

    for name in candidates:
        try:
            font = ImageFont.truetype(name, size)
            return font
        except OSError:
            continue
    # Cobertura del tipo para type checkers
    raise RuntimeError("unreachable")

    # Si no hay ninguna TTF disponible (raro), fallback al default de PIL.
    logger.warning(
        "Ninguna fuente TTF encontrada, usando PIL default (8x8 px). "
        "Instala fonts-dejavu-core o fonts-liberation."
    )
    return ImageFont.load_default()


def get_system_font_path() -> str | None:
    """Devuelve la ruta absoluta de la primera fuente encontrada, o None.

    Util para loggear que fuente se va a usar.
    """
    for name in _FONT_CANDIDATES:
        try:
            ImageFont.truetype(name, 12)
            return name
        except OSError:
            continue
    return None
