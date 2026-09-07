#!/usr/bin/env python3
"""Refresh /workspace/eq-legends/EQ_Legends_BiS.xlsx via build_planner.py."""
from __future__ import annotations
import sys
from pathlib import Path
LEGENDS = Path('/workspace/eq-legends')
sys.path.insert(0, str(LEGENDS))
import build_xlsx as bx
import build_planner as bp

def main(argv):
    classes = [c for c in argv[1:] if c.strip()]
    cleaned = []
    for c in classes:
        match = next((a for a in bx.ALL_CLASSES if a.lower() == c.lower()), None)
        if match and match not in cleaned:
            cleaned.append(match)
    if not cleaned:
        cleaned = list(bx.DEFAULT_TRIO)
    cleaned = cleaned[:3]
    trio = tuple(cleaned)
    bx.DEFAULT_TRIO = trio
    bx.TARGET_CLASSES = trio
    bp.set_planner_target(cleaned)
    print('Exporting planner XLSX for trio:', ', '.join(cleaned))
    bp.main()
    print('Wrote', bp.XLSX)
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
