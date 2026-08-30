"""Script de empaquetado multiplataforma (Windows + Linux)."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPEC = ROOT / "scripts" / "build.spec"


def build() -> None:
    """Ejecuta PyInstaller para producir un binario único."""
    if shutil.which("pyinstaller") is None:
        print("Error: pyinstaller no está instalado en el venv activo", file=sys.stderr)
        sys.exit(1)

    if not SPEC.exists():
        print(f"Error: spec no encontrado en {SPEC}", file=sys.stderr)
        sys.exit(1)

    cmd = [str(shutil.which("pyinstaller")), "--noconfirm", "--clean", str(SPEC)]
    print(f">>> Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if result.returncode != 0:
        print(f"Error: PyInstaller devolvió {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    if platform.system() == "Windows":
        exe = ROOT / "dist" / "turing-display-controller" / "turing-display-controller.exe"
    else:
        exe = ROOT / "dist" / "turing-display-controller" / "turing-display-controller"

    print(f"\n✅ Binario generado en: {exe}")
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"   Tamaño: {size_mb:.1f} MB")


if __name__ == "__main__":
    build()
