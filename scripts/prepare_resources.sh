#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
N='npm'

echo "[1/4] Sync decoded data"
bash scripts/sync_bundle_data.sh

echo "[2/4] Vendor Python modules"
mkdir -p resources/vendor
cp -a backend/vendor/*.py resources/vendor/
mkdir -p resources/data
cp -a data/races.json resources/data/races.json 2>/dev/null || true

echo "[3/4] Build React UI"
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && "$N" install)
fi
(cd frontend && "$N" run build)
rm -rf resources/ui
mkdir -p resources/ui
cp -a frontend/dist/. resources/ui/

echo "[4/4] API sidecar placeholder"
mkdir -p resources/api
if [[ ! -f resources/api/eq-api.exe && ! -f resources/api/eq-api ]]; then
  cat > resources/api/README.txt <<EOF
Place Windows PyInstaller output here:
  eq-api.exe (+ _internal/ folder if one-folder build)

Build on Windows with:
  scripts/build_api_sidecar.ps1

Without the sidecar, Electron falls back to system Python + uvicorn.
For a shareable .exe, build the sidecar on Windows, then: npm run dist:win
EOF
fi

echo "Resources ready under $ROOT/resources"
find resources -maxdepth 3 -type d | head -40
