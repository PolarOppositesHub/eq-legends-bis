# PACKAGING — EQ Legends BiS Windows distributable

## Goal
Double-click Windows app: portable exe + NSIS installer. Bundles UI + API + decoded JSON.
No terminal / no npm for end users.

## Architecture
- desktop/ Electron main spawns FastAPI sidecar, opens BrowserWindow to 127.0.0.1
- backend/packaging/api_entry.py (+ eq-api.spec) -> PyInstaller eq-api.exe (Windows)
- FastAPI serves API + static frontend/dist when EQ_PACKAGED=1
- paths.py resolves data next to frozen binary / Electron resources

## Build on Windows (Joshs_Notebook)
1. Install Node LTS + Python 3.11+
2. Open PowerShell in eq-legends-app
3. Run: `powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1`
   Or: `scripts\build-windows.bat`
4. Find artifacts in dist-desktop/

What the script does:
- npm run build in frontend/
- scripts/bundle_desktop_resources.py -> desktop/resources/ (JSON, UI, helpers, backend)
- PyInstaller backend/packaging/eq-api.spec -> dist/eq-api/ then copy to resources/eq-api/
- desktop: npm run dist:win (nsis + portable)

## Linux prep (this box)
- Backend path fixes + desktop project + scripts already in tree
- npm run build in frontend; python3 scripts/bundle_desktop_resources.py
- Full Windows exe needs the notebook (PyInstaller win)

## Sharing
Zip EQ-Legends-BiS-*-portable.exe and send. Brother double-clicks.

## Updater
desktop/package.json build.publish is a generic placeholder (example.com).
desktop/main.js loads electron-updater but skips checks until URL is real.
When ready: set github owner/repo or generic url, rebuild, upload release + latest.yml.
Env aliases: EQ_UPDATE_OWNER, EQ_UPDATE_REPO, EQ_UPDATE_URL.

## Env vars (sidecar)
EQ_PACKAGED, EQ_APP_ROOT, EQ_DATA_ROOT (alias EQ_LEGENDS_DATA), EQ_FRONTEND_DIST,
EQ_LEGENDS_ROOT, EQ_XLSX_DIR, EQ_API_PORT
