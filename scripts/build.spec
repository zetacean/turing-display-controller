# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para empaquetar turing-display-controller."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Recolectar todos los assets web (templates + static)
datas = []
web_dir = Path("src/turing_display/web")
datas += collect_data_files("turing_display.web.templates", includes=["*.html"])
datas += collect_data_files("turing_display.web.static", includes=["*.js"])

a = Analysis(
    ["src/turing_display/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "turing_display.api.routes",
        "turing_display.api.ws",
        "turing_display.api.server",
        "turing_display.api.spotify_auth",
        "turing_display.controller",
        "turing_display.modes.slideshow",
        "turing_display.modes.spotify",
        "turing_display.modes.mix",
        "turing_display.display.rev_a",
        "turing_display.notifications.overlay",
        "turing_display.phrases.repo",
        "turing_display.phrases.db",
        "turing_display.spotify_integration.client",
        "turing_display.spotify_integration.poller",
        "turing_display.spotify_integration.pkce",
        "turing_display.spotify_integration.tokens",
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
