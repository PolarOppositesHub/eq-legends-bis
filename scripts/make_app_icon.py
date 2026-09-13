#!/usr/bin/env python3
"""Build Electron/Windows icon assets from Josh's chosen source PNG only.

Does not invent art. Crops the dragon-eye seal from
packaging/icons/eq-legends-bis-icon-chosen.png (16:9 canvas) and writes
multi-size .ico + square PNG copies electron-builder expects.
"""
from __future__ import annotations

import hashlib
import shutil
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packaging" / "icons" / "eq-legends-bis-icon-chosen.png"
OUT_DIR = ROOT / "packaging" / "icons"
DESKTOP_BUILD = ROOT / "desktop" / "build"

# Windows / electron-builder recommended sizes (256 is the Vista+ large slot).
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIZE = 512
HIGHLIGHT_SUM = 150  # gold rim / bright pixels vs dark teal canvas
PAD_PX = 16


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def find_seal_bbox(im: Image.Image) -> tuple[int, int, int, int]:
    """Tight box around the gold-rimmed seal (not the 16:9 letterbox)."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    col_hi = []
    for x in range(w):
        m = 0
        for y in range(h):
            s = sum(px[x, y])
            if s > m:
                m = s
        col_hi.append(m)
    row_hi = []
    for y in range(h):
        m = 0
        for x in range(w):
            s = sum(px[x, y])
            if s > m:
                m = s
        row_hi.append(m)
    xs = [x for x, m in enumerate(col_hi) if m > HIGHLIGHT_SUM]
    ys = [y for y, m in enumerate(row_hi) if m > HIGHLIGHT_SUM]
    if not xs or not ys:
        raise SystemExit("Could not find the seal in the source PNG (no highlight pixels).")
    return xs[0], ys[0], xs[-1], ys[-1]


def square_crop(im: Image.Image) -> Image.Image:
    left, top, right, bottom = find_seal_bbox(im)
    left = max(0, left - PAD_PX)
    top = max(0, top - PAD_PX)
    right = min(im.width - 1, right + PAD_PX)
    bottom = min(im.height - 1, bottom + PAD_PX)
    bw = right - left + 1
    bh = bottom - top + 1
    side = max(bw, bh)
    cx = left + bw // 2
    cy = top + bh // 2
    sl = max(0, cx - side // 2)
    st = max(0, cy - side // 2)
    if sl + side > im.width:
        sl = im.width - side
    if st + side > im.height:
        st = im.height - side
    sl = max(0, sl)
    st = max(0, st)
    box = (sl, st, sl + side, st + side)
    print(f"  source {im.size} crop {box} ({side}x{side})")
    return im.crop(box)


def write_ico(square: Image.Image, dest: Path) -> None:
    """Write a multi-size ICO using PNG-encoded images (valid on Vista+)."""
    frames: list[bytes] = []
    for s in ICO_SIZES:
        frame = square.resize((s, s), Image.Resampling.LANCZOS)
        if frame.mode != "RGBA":
            frame = frame.convert("RGBA")
        buf = Path("/tmp") / f"_eq_icon_{s}.png"
        frame.save(buf, format="PNG")
        frames.append(buf.read_bytes())
        buf.unlink(missing_ok=True)

    count = len(frames)
    # ICONDIR + ICONDIRENTRY*count + image payloads
    offset = 6 + 16 * count
    entries = bytearray()
    payload = bytearray()
    for size, data in zip(ICO_SIZES, frames):
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    dest.write_bytes(struct.pack("<HHH", 0, 1, count) + entries + payload)
    print(f"  ico {dest} ({dest.stat().st_size} bytes, sizes {list(ICO_SIZES)})")


def main() -> int:
    if not SOURCE.is_file():
        print("ERROR: missing source", SOURCE, file=sys.stderr)
        return 1
    print("==> App icon from", SOURCE, f"sha256={sha256(SOURCE)[:12]}…")
    src = Image.open(SOURCE)
    square = square_crop(src)
    if square.mode != "RGBA":
        square = square.convert("RGBA")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DESKTOP_BUILD.mkdir(parents=True, exist_ok=True)

    square_png = OUT_DIR / "eq-legends-bis.png"
    square.save(square_png, format="PNG")
    print(f"  square {square_png} {square.size}")

    png_512 = square.resize((PNG_SIZE, PNG_SIZE), Image.Resampling.LANCZOS)
    ico_path = OUT_DIR / "eq-legends-bis.ico"
    write_ico(square, ico_path)

    # electron-builder default names under desktop/build (buildResources).
    build_png = DESKTOP_BUILD / "icon.png"
    build_ico = DESKTOP_BUILD / "icon.ico"
    png_512.save(build_png, format="PNG")
    png_512.save(OUT_DIR / "eq-legends-bis-512.png", format="PNG")
    shutil.copy2(ico_path, build_ico)

    print(f"  electron-builder {build_ico} + {build_png} ({PNG_SIZE}x{PNG_SIZE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
