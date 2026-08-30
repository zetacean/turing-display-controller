# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para empaquetar turing-display-controller."""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Resolver paths relativos a la raíz del proyecto (no al cwd ni al dir del .spec).
# Si PyInstaller se invoca desde otra carpeta (p. ej. usuario corre el comando
# dentro de ~/Downloads/...), se evita el bug:
#     "ERROR: script '.../scripts/src/turing_display/__main__.py' not found"
#
# PyInstaller inyecta SPECPATH (ruta absoluta del .spec) en el namespace
# antes de hacer exec() — es la única referencia fiable. NO usar __file__
# (no existe en el namespace del spec) ni sys.argv[0] (es el entry de la app).
PROJECT_ROOT = Path(SPECPATH).resolve().parent  # scripts/build.spec → scripts/ → parent = root

# Entry point: scripts/launcher.py (un shim que importa y ejecuta
# turing_display.__main__ preservando __package__, necesario para que
# los relative imports como ``from .api import ...`` funcionen).
ENTRY = str(PROJECT_ROOT / "scripts" / "launcher.py")
PATHEX = [
    str(PROJECT_ROOT / "src"),
    str(PROJECT_ROOT),  # para que `import scripts.launcher` también funcione si hace falta
]

# Recolectar todos los assets web (templates + static)
datas = []
datas += collect_data_files("turing_display.web.templates", includes=["*.html"])
datas += collect_data_files("turing_display.web.static", includes=["*.js"])

a = Analysis(
    [ENTRY],
    pathex=PATHEX,
    binaries=[],
    datas=datas,
    hiddenimports=[
        "turing_display",
        "turing_display.__main__",
        "turing_display.api",
        "turing_display.api.routes",
        "turing_display.api.ws",
        "turing_display.api.server",
        "turing_display.api.spotify_auth",
        "turing_display.controller",
        "turing_display.config",
        "turing_display.modes",
        "turing_display.modes.base",
        "turing_display.modes.slideshow",
        "turing_display.modes.spotify",
        "turing_display.modes.mix",
        "turing_display.display",
        "turing_display.display.factory",
        "turing_display.display.rev_a",
        "turing_display.display.renderer",
        "turing_display.display.gradients",
        "turing_display.notifications",
        "turing_display.notifications.overlay",
        "turing_display.phrases",
        "turing_display.phrases.repo",
        "turing_display.phrases.db",
        "turing_display.spotify_integration",
        "turing_display.spotify_integration.client",
        "turing_display.spotify_integration.poller",
        "turing_display.spotify_integration.pkce",
        "turing_display.spotify_integration.tokens",
        "turing_display.utils",
        "turing_display.utils.images_watcher",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="turing-display-controller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="turing-display-controller",
)
