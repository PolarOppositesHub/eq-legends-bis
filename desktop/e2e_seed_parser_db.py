"""Build a temp userData whose parser database still needs a schema rebuild.

The Electron test launches against this directory with the rebuild paused.
Item icons for the Wizard Best in Slot list are written into the userData
cache so the test does not depend on eqlwiki.

Usage: python e2e_seed_parser_db.py <userData> <eqRoot>
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

# Decoded catalogs live in the desktop resources tree in this repo.
import os

os.environ.setdefault("EQ_APP_ROOT", str(ROOT))
os.environ.setdefault("EQ_DATA_ROOT", str(ROOT / "desktop" / "resources" / "data" / "decoded"))

from app.engine import recommend_bis  # noqa: E402
from app.item_catalog import _slug  # noqa: E402
from app.parser.service import ParserService  # noqa: E402

# 1x1 PNG. Enough for naturalWidth > 0 without a wiki fetch.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _fight_lines(count: int) -> list[str]:
    lines = []
    for index in range(count):
        minute = 10 * index
        hour = 20 + minute // 60
        minute %= 60
        for second in range(1, 4):
            lines.append(
                f"[Tue Aug 04 {hour:02d}:{minute:02d}:{second:02d} 2026] "
                f"You slash a goblin for {50 + index} points of damage."
            )
    return lines


def _icon_names() -> list[str]:
    body = recommend_bis(
        ["Wizard"],
        mode="priority",
        priority_stat="INT",
        alts=5,
        upgrade=10,
        prefer_ranged_damage=True,
        character_level=50,
        primary_stats=[],
        secondary_stats=[],
        tertiary_stats=[],
        maximize_hp_regen=False,
    )
    names: list[str] = []
    for slot in body.get("slots") or []:
        if slot.get("name"):
            names.append(slot["name"])
        for alt in slot.get("alts") or []:
            if alt.get("name"):
                names.append(alt["name"])
    return names


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: e2e_seed_parser_db.py <userData> <eqRoot>", file=sys.stderr)
        return 2
    user_data = Path(argv[1]).resolve()
    eq_root = Path(argv[2]).resolve()
    logs = eq_root / "Logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / "eqlog_Zasariz_qeynos.txt"
    log_path.write_text("\n".join(_fight_lines(6)) + "\n", encoding="utf-8")

    user_data.mkdir(parents=True, exist_ok=True)
    service = ParserService(user_data=user_data, db_path=user_data / "parser.db", idle_seconds=30)
    try:
        service.set_eq_folder(str(eq_root))
        service.replay(log_path)
        if service.list_fights("Zasariz")["count"] < 5:
            print("seed log did not produce fights", file=sys.stderr)
            return 1
        with service.db.lock:
            service.db.conn.execute("DELETE FROM settings WHERE key='schema_version'")
            service.db.commit()
    finally:
        service.close()

    images = user_data / "item-images"
    images.mkdir(parents=True, exist_ok=True)
    names = _icon_names()
    for name in names:
        dest = images / f"{_slug(name)}.png"
        if not dest.is_file():
            dest.write_bytes(_PNG)

    session = {
        "v": 1,
        "tab": "parser",
        "classes": ["Wizard"],
        "mode": "priority",
        "upgrade": 10,
        "preferRanged": True,
        "characterLevel": 50,
        "race": "Human",
        "whatsNewSeen": "1.1.2",
        "primaryStats": ["", "", ""],
        "secondaryStats": ["", "", ""],
        "tertiaryStats": ["", "", ""],
    }
    (user_data / "workspace-session.json").write_text(json.dumps(session), encoding="utf-8")
    print(json.dumps({"log": str(log_path), "icons": len(names), "userData": str(user_data)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
