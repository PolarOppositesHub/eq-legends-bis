#!/usr/bin/env python3
"""Regenerate EQ_Legends_BiS.xlsx from decoded data via build_planner.py.

Usage (from /workspace/eq-legends-app):
  .venv/bin/python scripts/export_xlsx.py

Or:
  .venv/bin/python /workspace/eq-legends/build_planner.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EQ_ROOT = Path("/workspace/eq-legends")
SCRIPT = EQ_ROOT / "build_planner.py"
APP_ROOT = Path(__file__).resolve().parents[1]
VENV_PY = APP_ROOT / ".venv" / "bin" / "python"


def main() -> int:
    py = str(VENV_PY if VENV_PY.exists() else sys.executable)
    if not SCRIPT.exists():
        print("Missing", SCRIPT, file=sys.stderr)
        return 1
    print("Running", SCRIPT, "with", py)
    proc = subprocess.run([py, str(SCRIPT)], cwd=str(EQ_ROOT))
    if proc.returncode == 0:
        print("Wrote:", EQ_ROOT / "EQ_Legends_BiS.xlsx")
        print("Wrote:", EQ_ROOT / "EQ_Legends_BiS_fixed.xlsx")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
