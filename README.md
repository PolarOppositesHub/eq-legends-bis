# EQ Legends BiS + Build Sim

Local app for Josh Monroe and his brother.

Item stats come only from decoded JSON. See .build_owner. Keep STATUS.md updated.

## Dev start (Linux)

    cd /workspace/eq-legends-app && ./start.sh

API: http://127.0.0.1:8000/api/health  
UI:  http://127.0.0.1:5173/

Manual API: `.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload`  
Manual UI: `cd frontend && npm install && npm run dev`

Excel: scripts/export_xlsx.py ; scripts/run_planner_export.py ; POST /api/export/xlsx  
Data: data/decoded symlink to eq-legends/decoded

## Windows .exe (install, run, share with brother)

Electron + FastAPI (PyInstaller sidecar) under **desktop/**. Brother gets a double-click .exe — no terminal, no npm.

### Build on Josh's Windows PC (Joshs_Notebook)

Needs Windows for a real `eq-api.exe` (PyInstaller) plus electron-builder NSIS/portable:

    cd eq-legends-app
    powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1

Or: `scripts\build-windows.bat`

What that does:

1. Builds the React UI (`frontend`)
2. Bundles decoded JSON + UI + planner helpers into `desktop/resources/`
3. PyInstaller -> `eq-api.exe` into `desktop/resources/eq-api/`
4. `desktop`: `npm run dist:win` -> NSIS + portable

### Artifacts (`dist-desktop/`)

- **EQ-Legends-BiS-*-portable.exe** — zip and send to brother; double-click to run
- **EQ-Legends-BiS-*-win-x64.exe** — NSIS installer (Start Menu + desktop shortcut)

### Install / run / share

1. Build on Windows as above
2. Smoke-test: 1–3 classes, Priority/Max All, haste warn, race+slot sim, XLSX export
3. Zip the portable `.exe` (or the NSIS installer) and send via Drive/USB
4. Brother unzips and double-clicks — offline data is included

### Linux prep (this box)

    cd frontend && npm run build
    python3 scripts/bundle_desktop_resources.py
    npm run dist:linux:dir   # optional smoke unpackaged dir
    # Full Windows .exe needs the notebook (or Wine); see PACKAGING.md

Root helpers: `npm run prepare:resources`, `npm run dist:win` (delegates to desktop/).

## Updates (how to enable)

electron-updater is wired in `desktop/main.js`. Until a real release host exists it **skips quietly**.

To enable:

1. Edit `desktop/package.json` -> `build.publish`:
   - GitHub: `{ "provider": "github", "owner": "YOUR_OWNER", "repo": "YOUR_REPO" }`
   - Or generic HTTPS feed URL hosting `latest.yml` + artifacts
   - Optional env: `EQ_UPDATE_OWNER` / `EQ_UPDATE_REPO` / `EQ_UPDATE_URL`
2. Rebuild and upload release artifacts + `latest.yml` (electron-builder `--publish`)
3. Packaged apps will then check for updates on launch

Details: PACKAGING.md

## Features

16 classes, 1–3 BiS, Priority/Max All, ratio weapons, single worn haste warn, race/slot sim, XLSX export.

## Paths

backend/app (paths.py), frontend/, desktop/, scripts/, dist-desktop/, backend/vendor/
