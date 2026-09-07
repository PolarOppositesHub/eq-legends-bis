"""Resolve app / data / frontend paths for dev and packaged (PyInstaller / Electron) modes.

Env overrides:
  EQ_PACKAGED=1          Force packaged mode (serve static UI)
  EQ_APP_ROOT            App root (contains backend/, frontend/, data/)
  EQ_LEGENDS_ROOT        Tree with build_planner.py / item-urls.txt / decoded/
  EQ_DATA_ROOT           Decoded JSON directory
  EQ_FRONTEND_DIST       Built SPA directory (index.html + assets/)
  EQ_XLSX_DIR            Where to write/read EQ_Legends_BiS.xlsx
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _env_path(name: str) -> Path | None:
    v = (os.environ.get(name) or "").strip()
    return Path(v).expanduser().resolve() if v else None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def meipass() -> Path | None:
    p = getattr(sys, "_MEIPASS", None)
    return Path(p) if p else None


def app_root() -> Path:
    override = _env_path("EQ_APP_ROOT")
    if override:
        return override
    if is_frozen():
        exe = Path(sys.executable).resolve().parent
        for cand in (exe / "resources", exe.parent / "resources", exe):
            if (cand / "data" / "decoded").exists() or (cand / "frontend" / "dist").exists():
                return cand
        mp = meipass()
        if mp:
            return mp
        return exe
    # backend/app/paths.py -> parents[2] = app root
    return Path(__file__).resolve().parents[2]


# Eager constant for modules that import APP_ROOT at load time
APP_ROOT = app_root()


def legends_root() -> Path:
    override = _env_path("EQ_LEGENDS_ROOT")
    if override:
        return override
    root = app_root()
    # Prefer a tree that has both planner modules AND decoded/ (or item-urls).
    # In packaged builds, backend/vendor + EQ_DATA_ROOT is used.
    candidates = [
        root.parent / "eq-legends",
        Path("/workspace/eq-legends"),
        root / "resources" / "eq-legends",
        root / "eq-legends",
        root / "vendor" / "eq-legends",
        root / "backend" / "vendor",
    ]
    for cand in candidates:
        if (cand / "build_planner.py").exists() and (
            (cand / "decoded").exists() or (cand / "item-urls.txt").exists()
        ):
            return cand.resolve()
    for cand in candidates:
        if (cand / "build_planner.py").exists() or (cand / "decoded").exists():
            return cand.resolve()
    return Path("/workspace/eq-legends")


def decoded_dir() -> Path:
    override = _env_path("EQ_DATA_ROOT") or _env_path("EQ_LEGENDS_DATA")
    if override:
        return override
    root = app_root()
    for cand in (
        root / "data" / "decoded",
        root / "resources" / "data" / "decoded",
        root / "desktop" / "resources" / "data" / "decoded",
        root / "decoded",
        legends_root() / "decoded",
    ):
        if cand.exists():
            return cand.resolve()
    return (root / "data" / "decoded").resolve()


def frontend_dist() -> Path:
    override = _env_path("EQ_FRONTEND_DIST")
    if override:
        return override
    root = app_root()
    for cand in (
        root / "frontend" / "dist",
        root / "resources" / "frontend" / "dist",
        root / "ui",
        meipass() / "frontend" / "dist" if meipass() else None,
    ):
        if cand and cand.exists():
            return cand.resolve()
    return (root / "frontend" / "dist").resolve()


def xlsx_dir() -> Path:
    override = _env_path("EQ_XLSX_DIR")
    if override:
        return override
    if is_frozen() or os.environ.get("EQ_PACKAGED") == "1":
        for cand in (legends_root(), app_root(), Path.cwd()):
            if cand.exists():
                return cand.resolve()
    return legends_root()


def packaged_mode() -> bool:
    if os.environ.get("EQ_PACKAGED") == "1":
        return True
    if is_frozen():
        return True
    return frontend_dist().exists()


def apply_legends_roots() -> None:
    """Patch imported eq-legends modules so hardcoded ROOT/OUT point at resolved paths."""
    root = legends_root()
    out = decoded_dir()
    xdir = xlsx_dir()
    for mod_name in ("build_xlsx", "build_planner", "decode_local"):
        mod = sys.modules.get(mod_name)
        if not mod:
            continue
        if hasattr(mod, "ROOT"):
            mod.ROOT = root
        if hasattr(mod, "OUT"):
            mod.OUT = out
        if hasattr(mod, "XLSX"):
            mod.XLSX = xdir / "EQ_Legends_BiS.xlsx"
        if hasattr(mod, "XLSX_FIXED"):
            mod.XLSX_FIXED = xdir / "EQ_Legends_BiS_fixed.xlsx"
        if hasattr(mod, "VERIFY"):
            mod.VERIFY = xdir / "planner_verify.json"


def ensure_sys_path() -> Path:
    """Put legends root on sys.path so build_planner / build_xlsx import."""
    root = legends_root()
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)
    return root


def ensure_vendor_on_path() -> Path:
    """Alias used by engine.py — also prefer a vendored copy under app/vendor."""
    root = app_root()
    for cand in (
        root / "backend" / "vendor",
        root / "vendor" / "eq-legends",
        root / "resources" / "eq-legends",
        root / "eq-legends",
    ):
        if (cand / "build_planner.py").exists():
            s = str(cand.resolve())
            if s not in sys.path:
                sys.path.insert(0, s)
            os.environ.setdefault("EQ_LEGENDS_ROOT", s)
            return cand.resolve()
    return ensure_sys_path()
