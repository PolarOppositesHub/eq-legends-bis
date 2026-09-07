#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/data"
ln -sfn /workspace/eq-legends/decoded "$ROOT/data/decoded"
echo "Linked $ROOT/data/decoded -> /workspace/eq-legends/decoded"
