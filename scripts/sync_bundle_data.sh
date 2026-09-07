#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${EQ_LEGENDS_SRC:-/workspace/eq-legends/decoded}"
DEST="$ROOT/resources/data/decoded"
mkdir -p "$DEST"
if [[ ! -d "$SRC" ]]; then
  echo "Missing decoded data at $SRC" >&2
  exit 1
fi
rsync -a --delete "$SRC/" "$DEST/" 2>/dev/null || {
  rm -rf "$DEST"
  mkdir -p "$DEST"
  cp -a "$SRC/." "$DEST/"
}
mkdir -p "$ROOT/data"
ln -sfn "$SRC" "$ROOT/data/decoded"
echo "Synced decoded JSON -> $DEST"
ls "$DEST" | wc -l
