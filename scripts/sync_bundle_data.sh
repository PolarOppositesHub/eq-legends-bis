#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${EQ_LEGENDS_SRC:-/workspace/eq-legends/decoded}"
DEST="$ROOT/resources/data/decoded"
# Prefer desktop bundle path used by the packaged app when present.
if [[ -d "$ROOT/desktop/resources/data/decoded" ]]; then
  DEST="$ROOT/desktop/resources/data/decoded"
fi
mkdir -p "$DEST"
if [[ ! -d "$SRC" ]]; then
  echo "Missing decoded data at $SRC" >&2
  exit 1
fi
# Preserve wiki indexes that live only in the app bundle (not in eq-legends decode).
KEEP_TMP="$(mktemp -d)"
for keep in eqlwiki_mob_names.json eqlwiki_item_names.json; do
  if [[ -f "$DEST/$keep" ]]; then
    cp -a "$DEST/$keep" "$KEEP_TMP/$keep"
  fi
done
rsync -a --delete "$SRC/" "$DEST/" 2>/dev/null || {
  rm -rf "$DEST"
  mkdir -p "$DEST"
  cp -a "$SRC/." "$DEST/"
}
for keep in eqlwiki_mob_names.json eqlwiki_item_names.json; do
  if [[ -f "$KEEP_TMP/$keep" ]]; then
    cp -a "$KEEP_TMP/$keep" "$DEST/$keep"
  fi
done
rm -rf "$KEEP_TMP"
# Also copy preserved indexes into desktop resources if that path differs.
DESKTOP_DEST="$ROOT/desktop/resources/data/decoded"
if [[ -d "$DESKTOP_DEST" && "$DESKTOP_DEST" != "$DEST" ]]; then
  for keep in eqlwiki_mob_names.json eqlwiki_item_names.json; do
    if [[ -f "$DEST/$keep" ]]; then
      cp -a "$DEST/$keep" "$DESKTOP_DEST/$keep"
    fi
  done
fi
mkdir -p "$ROOT/data"
ln -sfn "$DEST" "$ROOT/data/decoded"
echo "Synced decoded JSON -> $DEST (preserved eqlwiki_* indexes)"
ls "$DEST" | wc -l
