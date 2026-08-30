"""Generadores de fondos degradados "felices" para el panel Turing 3.5".

Colores cálidos y vivos (naranja, rosa, amarillo, turquesa) sin negro,
pensados para que la pantalla muestre energía cuando no hay contenido
(fondos de frases, bandas laterales de fotos verticales, etc.).
"""

from __future__ import annotations

from PIL import Image

# Paletas "felices" — RGB
PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    # sunset
    "sunset": ((255, 94, 77), (255, 195, 0)),
    # pink lemonade
    "pink": ((255, 64, 129), (255, 193, 7)),
    # tropical
    "tropical": ((0, 200, 150), (255, 209, 102)),
    # sky
    "sky": ((100, 181, 246), (255, 241, 118)),
    # candy
    "candy": ((171, 71, 188), (255, 167, 38)),
    # ocean
    "ocean": ((38, 198, 218), (102, 187, 106)),
}


def _lerp(a: int, b: int, t: float) -> int:
    """Interpolación lineal entre dos enteros."""
    return int(a + (b - a) * t)


def _blend(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Mezcla dos colores RGB en ``t`` ∈ [0, 1]."""
    return (_lerp(c1[0], c2[0], t), _lerp(c1[1], c2[1], t), _lerp(c1[2], c2[2], t))


def vertical_gradient(
    width: int,
    height: int,
    top_rgb: tuple[int, int, int],
    bottom_rgb: tuple[int, int, int],
) -> Image.Image:
    """Genera una imagen ``width × height`` con degradado vertical.

    Parameters
    ----------
    width, height : int
        Dimensiones de la imagen destino.
    top_rgb : tuple[int, int, int]
        Color RGB en la fila 0.
    bottom_rgb : tuple[int, int, int]
        Color RGB en la fila ``height - 1``.

    Returns
    -------
    PIL.Image.Image
        Imagen en modo ``RGB`` con el degradado.
    """
    if height <= 0 or width <= 0:
        return Image.new("RGB", (max(width, 1), max(height, 1)), top_rgb)

    rows = [
        _blend(top_rgb, bottom_rgb, y / (height - 1) if height > 1 else 0.0) for y in range(height)
    ]
    img = Image.new("RGB", (width, height))
    px = img.load()
    assert px is not None
    for y, color in enumerate(rows):
        for x in range(width):
            px[x, y] = color
    return img


def happy_background(width: int, height: int, seed: int = 0) -> Image.Image:
    """Devuelve un fondo degradado de la paleta feliz.

    La paleta se elige de forma determinista a partir de ``seed`` (útil
    cuando se quiere que dos fondos de la misma "familia" combinen, p.
    ej. foto vertical + frase del mismo mix).
    """
    keys = list(PALETTES.keys())
    palette = PALETTES[keys[seed % len(keys)]]
    return vertical_gradient(width, height, palette[0], palette[1])
