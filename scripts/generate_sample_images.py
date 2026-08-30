"""Genera imágenes de ejemplo para probar el slideshow."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path("images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Colores y textos para 4 imágenes de ejemplo
SAMPLES = [
    {
        "name": "01_gradient.png",
        "size": (1920, 1080),
        "type": "gradient",
        "label": "HORIZONTAL 16:9",
    },
    {
        "name": "02_solid.png",
        "size": (640, 480),
        "type": "solid",
        "color": (200, 80, 60),
        "label": "ROJO 4:3",
    },
    {
        "name": "03_vertical.png",
        "size": (1080, 1920),
        "type": "solid",
        "color": (60, 120, 200),
        "label": "VERTICAL 9:16",
    },
    {
        "name": "04_pattern.png",
        "size": (1280, 720),
        "type": "pattern",
        "label": "PATRON 16:9",
    },
]


def make_gradient(width: int, height: int) -> Image.Image:
    """Gradiente diagonal RGB → útil para detectar orientación."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            arr[y, x] = (
                int(255 * x / width),
                int(255 * y / height),
                int(255 * (x + y) / (width + height)),
            )
    img = Image.fromarray(arr)
    return _add_label(img, "GRADIENTE")


def make_solid(width: int, height: int, color: tuple[int, int, int], label: str) -> Image.Image:
    """Imagen sólida con etiqueta."""
    img = Image.new("RGB", (width, height), color)
    return _add_label(img, label)


def make_pattern(width: int, height: int) -> Image.Image:
    """Patrón de cuadrícula."""
    img = Image.new("RGB", (width, height), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    # Líneas verticales cada 80 px
    for x in range(0, width, 80):
        draw.line([(x, 0), (x, height)], fill=(80, 80, 80), width=2)
    for y in range(0, height, 80):
        draw.line([(0, y), (width, y)], fill=(80, 80, 80), width=2)
    # Diagonal para distinguir orientación
    draw.line([(0, 0), (width, height)], fill=(200, 30, 30), width=4)
    return _add_label(img, "PATRON")


def _add_label(img: Image.Image, text: str) -> Image.Image:
    """Añade una etiqueta centrada arriba."""
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", max(28, img.size[0] // 30))
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # Fondo semitransparente simulado
    pad = 16
    x0 = (img.size[0] - tw) // 2 - pad
    y0 = 20
    draw.rectangle((x0, y0, x0 + tw + 2 * pad, y0 + th + 2 * pad), fill=(0, 0, 0))
    draw.text(((img.size[0] - tw) // 2, y0 + pad), text, font=font, fill=(255, 255, 255))
    return img


def main() -> int:
    """Genera las imágenes de muestra."""
    for sample in SAMPLES:
        path = OUTPUT_DIR / sample["name"]
        w, h = sample["size"]
        if sample["type"] == "gradient":
            img = make_gradient(w, h)
        elif sample["type"] == "solid":
            img = make_solid(w, h, sample["color"], sample["label"])
        elif sample["type"] == "pattern":
            img = make_pattern(w, h)
        else:
            raise ValueError(f"Tipo desconocido: {sample['type']}")
        img.save(path, "PNG")
        print(f"[sample] {path} ({w}x{h})")
    print(f"\n[sample] {len(SAMPLES)} imágenes generadas en {OUTPUT_DIR.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
