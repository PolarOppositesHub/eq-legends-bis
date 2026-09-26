"""Item Search order and +0…+10 slider scaling on v1.0.23.

Cloak of Flames haste is the tooltip base plus the upgrade level:
36 at +0, 41 at +5, 46 at +10. Absolute catalog paths are not snapshotted.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.engine import apply_worn_haste, scale_stats_to_level  # noqa: E402
from app.item_catalog import get_item_by_name, search_items  # noqa: E402
from golden_support import assert_golden  # noqa: E402


QUERIES = [
    {"q": "cloak of flames", "limit": 10},
    {"q": "flowing black", "limit": 20},
    {"q": "sash", "slot": "WAIST", "limit": 10},
    {"q": "", "slot": "BACK", "limit": 8},
]

SLIDER_ITEMS = [
    "Cloak of Flames",
    "Flowing Black Silk Sash",
    "Blued Two-Handed Hammer",
]


def _search_view(query: dict) -> dict:
    result = search_items(
        query.get("q", ""),
        slot=query.get("slot"),
        limit=query.get("limit", 50),
        offset=query.get("offset", 0),
    )
    return {
        "query": result.get("query"),
        "slot": result.get("slot"),
        "total": result.get("total"),
        "offset": result.get("offset"),
        "limit": result.get("limit"),
        "names": [item.get("name") for item in result.get("items") or []],
    }


def _scaled(name: str) -> dict:
    item = get_item_by_name(name, enrich=False)
    if not item:
        raise AssertionError(f"catalog item missing: {name}")
    stats0 = dict(item.get("stats_plus0") or {})
    stats10 = dict(item.get("stats_plus10") or {})
    levels = {}
    for level in (0, 5, 10):
        stats = scale_stats_to_level(stats0, level)
        apply_worn_haste(stats, stats0, level, stats10)
        levels[str(level)] = stats
    return {
        "name": item.get("name"),
        "slot": item.get("slot"),
        "stats_plus0": stats0,
        "stats_plus10_haste": stats10.get("Haste") if "Haste" in stats10 else stats10.get("haste"),
        "scaled": levels,
    }


class ItemSearchGoldenTests(unittest.TestCase):
    def test_search_names_and_order(self):
        snapshot = {"queries": [_search_view(query) for query in QUERIES]}
        cloak = next(row for row in snapshot["queries"] if row["query"] == "cloak of flames")
        self.assertEqual(cloak["names"], ["Cloak of Flames"])
        assert_golden(self, "item_search_names", snapshot)

    def test_slider_scales_haste_as_base_plus_level(self):
        rows = [_scaled(name) for name in SLIDER_ITEMS]
        cloak = next(row for row in rows if row["name"] == "Cloak of Flames")
        self.assertEqual(cloak["scaled"]["0"]["Haste"], 36)
        self.assertEqual(cloak["scaled"]["5"]["Haste"], 41)
        self.assertEqual(cloak["scaled"]["10"]["Haste"], 46)
        # AC follows the stat curve, not the haste +level rule. +10 of AC 10 is 20.
        self.assertEqual(cloak["scaled"]["0"]["AC"], 10)
        self.assertEqual(cloak["scaled"]["10"]["AC"], 20)
        assert_golden(self, "item_slider_stats", {"items": rows})


if __name__ == "__main__":
    unittest.main()
