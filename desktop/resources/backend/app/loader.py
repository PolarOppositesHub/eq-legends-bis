"""Load decoded BiS/flat JSON from data/decoded (symlink to eq-legends/decoded)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .scoring import prepare_item

from .paths import APP_ROOT as ROOT, decoded_dir, legends_root

DATA = decoded_dir()
LEGENDS = legends_root()

ALL_CLASSES = (
    "Bard", "Beastlord", "Berserker", "Cleric", "Druid", "Enchanter",
    "Magician", "Monk", "Necromancer", "Paladin", "Ranger", "Rogue",
    "Shadow Knight", "Shaman", "Warrior", "Wizard",
)
DEFAULT_TRIO = ("Paladin", "Monk", "Wizard")


def _flat_path(cls: str) -> Path:
    # Shadow Knight may be stored with underscore
    candidates = [
        DATA / f"flat_{cls}.json",
        DATA / f"flat_{cls.replace(' ', '_')}.json",
        LEGENDS / "decoded" / f"flat_{cls}.json",
        LEGENDS / "decoded" / f"flat_{cls.replace(' ', '_')}.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"Missing flat JSON for class {cls}")


@lru_cache(maxsize=1)
def load_summary() -> dict:
    for p in (DATA / "summary.json", LEGENDS / "decoded" / "summary.json"):
        if p.exists():
            return json.loads(p.read_text())
    return {"classes": list(ALL_CLASSES), "default_planner_trio": list(DEFAULT_TRIO)}


@lru_cache(maxsize=32)
def load_flat_class(cls: str) -> list[dict]:
    return json.loads(_flat_path(cls).read_text())


def normalize_classes(classes: list[str] | None) -> list[str]:
    if not classes:
        return list(DEFAULT_TRIO)
    cleaned = []
    for c in classes:
        c = (c or "").strip()
        if not c:
            continue
        match = next((a for a in ALL_CLASSES if a.lower() == c.lower()), None)
        if match and match not in cleaned:
            cleaned.append(match)
    if not cleaned:
        return list(DEFAULT_TRIO)
    return cleaned[:3]


def build_pool(classes: list[str]) -> list[dict]:
    """Union of flat items usable by ANY selected class (intersection optional via filter)."""
    selected = set(classes)
    by_name: dict[str, dict] = {}
    for cls in classes:
        for raw in load_flat_class(cls):
            item = prepare_item(raw, selected)
            if not item:
                continue
            name = item["name"]
            existing = by_name.get(name)
            if not existing:
                by_name[name] = item
                continue
            # prefer richer stats / higher tri overlap
            if item.get("tri_classes", 0) > existing.get("tri_classes", 0):
                by_name[name] = item
            elif item.get("bis_overlap", 0) > existing.get("bis_overlap", 0):
                by_name[name] = item
    return list(by_name.values())


def items_usable_by_all(pool: list[dict], classes: list[str]) -> list[dict]:
    """Items usable by ALL selected classes (shared BiS pool)."""
    selected = set(classes)
    out = []
    for item in pool:
        cl = {str(c) for c in (item.get("classes") or [])}
        if "ALL" in cl or selected.issubset(cl):
            out.append(item)
    return out


def find_item_by_name(pool: list[dict], name: str) -> dict | None:
    key = (name or "").strip().lower()
    for item in pool:
        if item.get("name", "").lower() == key:
            return item
    return None
