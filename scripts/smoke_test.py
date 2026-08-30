"""Script de smoke test: HELLO + frame real contra la pantalla conectada."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from turing_display.display.rev_a import LcdCommRevA


def main() -> int:
    """Ejecuta el smoke test contra la pantalla."""
    com_port = "COM5"
    print(f"[smoke] Conectando a {com_port}...")

    try:
        driver = LcdCommRevA(com_port=com_port)
    except Exception as e:  # noqa: BLE001
        print(f"[smoke] ERROR al crear driver: {e}")
        return 1

    print(f"[smoke] Driver creado. sub_revision={driver.sub_revision}")
    print(f"[smoke] Resolución: {driver.display_width}x{driver.display_height}")

    # Ajustar brillo a 70%
    driver.set_brightness(70)
    print("[smoke] Brillo ajustado a 70%")

    # Generar un frame de prueba con un gradiente RGB
    w, h = driver.display_width, driver.display_height
    img = Image.new("RGB", (w, h))
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            arr[y, x] = (
                int(255 * x / w),  # R: rojo horizontal
                int(255 * y / h),  # G: verde vertical
                128,  # B constante
            )
    img = Image.fromarray(arr)

    print(f"[smoke] Enviando frame de prueba {w}x{h}...")
    driver.display_pil_image(img)
    print("[smoke] Frame enviado ✓")

    # Limpiar
    time.sleep(1)
    driver.screen_off()
    print("[smoke] Pantalla apagada")
    driver.close_serial()
    print("[smoke] Puerto cerrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
