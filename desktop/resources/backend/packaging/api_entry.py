#!/usr/bin/env python3
"""Sidecar entry for Electron / PyInstaller.

Usage:
  python api_entry.py --port 8765
  eq-api.exe --port 8765

Sets EQ_PACKAGED=1 and starts uvicorn serving backend.app.main:app
(with static UI when frontend/dist is present).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _bootstrap_path() -> None:
    """Ensure app root is importable when frozen or run from packaging/."""
    if getattr(sys, "frozen", False):
        # PyInstaller one-folder: modules live in _MEIPASS or next to exe
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        for p in (meipass, exe_dir, exe_dir.parent, exe_dir / "resources"):
            if (p / "backend").exists() or (p / "app").exists():
                sys.path.insert(0, str(p))
                os.environ.setdefault("EQ_APP_ROOT", str(p if (p / "backend").exists() else exe_dir.parent))
                break
        # Vendored legends
        for p in (exe_dir / "eq-legends", exe_dir / "resources" / "eq-legends", meipass / "eq-legends"):
            if (p / "build_planner.py").exists():
                sys.path.insert(0, str(p))
                os.environ.setdefault("EQ_LEGENDS_ROOT", str(p))
                break
    else:
        # .../backend/packaging/api_entry.py -> app root = parents[2]
        app_root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(app_root))
        os.environ.setdefault("EQ_APP_ROOT", str(app_root))
        legends = app_root.parent / "eq-legends"
        if (legends / "build_planner.py").exists():
            sys.path.insert(0, str(legends))
            os.environ.setdefault("EQ_LEGENDS_ROOT", str(legends))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EQ Legends BiS API sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("EQ_API_PORT", "8765")))
    args = parser.parse_args(argv)

    os.environ["EQ_PACKAGED"] = "1"
    _bootstrap_path()

    import uvicorn

    # Import after path bootstrap
    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
        reload=False,
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
