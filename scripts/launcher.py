"""Launcher shim para PyInstaller.

Cuando PyInstaller ejecuta un entry que es ``__main__.py`` de un paquete,
los imports relativos (``from .api import ...``) fallan porque PyInstaller
no inyecta ``__package__`` en el namespace. Este shim hace lo correcto:
ejecuta ``turing_display.__main__.main()`` desde el módulo importado, lo
que preserva ``__package__`` y los relative imports funcionan.

NO se usa ``python -m turing_display`` porque en el binario PyInstaller no
hay ``runpy`` que respete eso, y porque ``__main__.py`` ya hace lo suyo.
"""

from __future__ import annotations

import runpy


def _run() -> None:
    """Ejecuta ``turing_display.__main__`` preservando ``__package__``."""
    runpy.run_module(
        "turing_display.__main__",
        run_name="__main__",
        alter_sys=True,
    )


if __name__ == "__main__":
    _run()
