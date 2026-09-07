# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Windows eq-api.exe (run on Windows via build-windows.ps1)
# Usage (from app root, on Windows):
#   pyinstaller backend/packaging/eq-api.spec

import sys
from pathlib import Path

SPECDIR = Path(SPEC).resolve().parent
APP_ROOT = SPECDIR.parent.parent
LEGENDS = APP_ROOT.parent / "eq-legends"
if not (LEGENDS / "build_planner.py").exists():
    LEGENDS = APP_ROOT / "resources" / "eq-legends"

block_cipher = None

hidden = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "pydantic",
    "openpyxl",
    "PIL",
    "PIL.Image",
    "backend",
    "backend.app",
    "backend.app.main",
    "backend.app.engine",
    "backend.app.paths",
    "backend.app.races",
    "build_planner",
    "build_xlsx",
    "decode_local",
]

datas = []
# Bundle backend package sources
datas.append((str(APP_ROOT / "backend"), "backend"))
# Vendored legends python modules + item-urls (JSON data copied separately into Electron resources)
if LEGENDS.exists():
    for name in ("build_planner.py", "build_xlsx.py", "decode_local.py", "item-urls.txt"):
        p = LEGENDS / name
        if p.exists():
            datas.append((str(p), "."))

a = Analysis(
    [str(SPECDIR / "api_entry.py")],
    pathex=[str(APP_ROOT), str(LEGENDS)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
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
    name="eq-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no terminal flash for end users
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    name="eq-api",
)
