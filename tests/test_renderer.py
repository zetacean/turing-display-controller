"""Tests para el renderer PIL (fit_letterbox)."""

from __future__ import annotations

from PIL import Image

from turing_display.display.renderer import fit_letterbox


def test_horizontal_image_covers_full_screen() -> None:
    """Imagen horizontal (16:9) cubre toda la pantalla sin bandas."""
    img = Image.new("RGB", (1920, 1080), (255, 0, 0))
    out = fit_letterbox(img, 320, 480)
    assert out.size == (320, 480)
    # No debe haber bandas negras porque la imagen es horizontal
    px = out.load()
    assert px[0, 0] == (255, 0, 0) or px[0, 0][0] > 0


def test_vertical_image_gets_letterbox() -> None:
    """Imagen vertical (9:16) se ajusta con bandas (gradiente feliz por defecto)."""
    img = Image.new("RGB", (1080, 1920), (0, 255, 0))
    out = fit_letterbox(img, 320, 480)
    assert out.size == (320, 480)
    px = out.load()
    # La imagen rota 90deg (1920x1080 -> 1080x1920), se escala al ancho 320
    # -> queda (320, 569). PIL pega al frame (320, 480) recortando vertical.
    # Asi que el frame NO es todo verde: hay pixeles del degradado (bandas).
    green_only = sum(1 for x in range(320) for y in range(480) if px[x, y] == (0, 255, 0))
    assert green_only < 320 * 480, "no deberia ser todo verde, hay bandas de degradado"


def test_custom_padding_color() -> None:
    """El color de las bandas es configurable (vertical -> bandas arriba/abajo)."""
    img = Image.new("RGB", (1080, 1920), (255, 255, 255))
    out = fit_letterbox(img, 320, 480, padding_color=(255, 0, 0))
    assert out.size == (320, 480)
    px = out.load()
    # Debe haber pixeles rojos (bandas)
    red_pixels = sum(1 for x in range(320) for y in range(480) if px[x, y] == (255, 0, 0))
    assert red_pixels > 0, "deberia haber bandas rojas"


def test_rgba_image_converted() -> None:
    """Imágenes RGBA se convierten a RGB."""
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
    out = fit_letterbox(img, 320, 480)
    assert out.mode == "RGB"
    assert out.size == (320, 480)


def test_grayscale_image_converted() -> None:
    """Imágenes en modo L se convierten a RGB."""
    img = Image.new("L", (100, 100), 128)
    out = fit_letterbox(img, 320, 480)
    assert out.mode == "RGB"


def test_exact_aspect_ratio() -> None:
    """Imagen con aspect ratio exacto no añade bandas extra."""
    img = Image.new("RGB", (320, 480), (0, 0, 255))
    out = fit_letterbox(img, 320, 480)
    assert out.size == (320, 480)
    px = out.load()
    assert px[160, 240] == (0, 0, 255)
