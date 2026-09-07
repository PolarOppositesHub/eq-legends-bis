#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r backend/requirements.txt
mkdir -p data
ln -sfn /workspace/eq-legends/decoded data/decoded
export PYTHONPATH="$ROOT/backend:${PYTHONPATH:-}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
echo "Starting API on :$API_PORT ..."
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$API_PORT" &
API_PID=$!
cleanup() { kill "$API_PID" 2>/dev/null || true; [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true; }
trap cleanup EXIT
if [[ -f frontend/package.json ]]; then
  if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm install); fi
  echo "Starting Vite on :$WEB_PORT ..."
  (cd frontend && npm run dev -- --host 0.0.0.0 --port "$WEB_PORT") &
  WEB_PID=$!
fi
echo "API:  http://127.0.0.1:$API_PORT/api/health"
echo "UI:   http://127.0.0.1:$WEB_PORT/"
wait
