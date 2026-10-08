"""Two wrist slots, and lore on wrist / finger / ear pairs."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.scoring import PLANNER_SLOTS, default_score_opts, pick_loadout  # noqa: E402


def _gear(name, ac, flags="", owned_count=None, slots=None):
    row = {
        "name": name,
        "stats_plus0": {"AC": ac},
        "stats_plus10": {"AC": ac},
        "planner_slots": list(slots or ["WRIST1", "WRIST2"]),
        "slots": ["WRIST"],
        "classes": ["ALL"],
        "classes_str": "ALL",
        "is_weapon": False,
        "bis_overlap": 0,
        "tri_classes": 1,
        "flags": flags,
        "zone": "",
        "url": "",
    }
    if owned_count is not None:
        row["owned_count"] = owned_count
    return row


def _wrists(pool):
    loadout = pick_loadout(pool, "max", None, default_score_opts())
    return loadout["WRIST1"]["name"], loadout["WRIST2"]["name"]


class PairedSlotTests(unittest.TestCase):
    def test_planner_has_two_wrist_slots(self):
        self.assertIn("WRIST1", PLANNER_SLOTS)
        self.assertIn("WRIST2", PLANNER_SLOTS)
        self.assertNotIn("WRIST", PLANNER_SLOTS)
        self.assertLess(PLANNER_SLOTS.index("WRIST1"), PLANNER_SLOTS.index("WRIST2"))

    def test_lore_top_item_takes_a_different_second_pick(self):
        pool = [
            _gear("Hero Bracers", 40, "MAGIC ITEM · LORE ITEM"),
            _gear("Granite Bracer", 10, "MAGIC ITEM"),
        ]
        self.assertEqual(_wrists(pool), ("Hero Bracers", "Granite Bracer"))

    def test_non_lore_fills_both_wrist_slots(self):
        pool = [
            _gear("Granite Bracer", 40, "MAGIC ITEM"),
            _gear("Lesser Bracer", 5, "MAGIC ITEM"),
        ]
        self.assertEqual(_wrists(pool), ("Granite Bracer", "Granite Bracer"))

    def test_owned_non_lore_needs_count_two_and_lore_stays_once(self):
        one = [
            _gear("Granite Bracer", 40, "MAGIC ITEM", owned_count=1),
            _gear("Lesser Bracer", 5, "MAGIC ITEM", owned_count=1),
        ]
        self.assertEqual(_wrists(one), ("Granite Bracer", "Lesser Bracer"))
        two = [
            _gear("Granite Bracer", 40, "MAGIC ITEM", owned_count=2),
            _gear("Lesser Bracer", 5, "MAGIC ITEM", owned_count=1),
        ]
        self.assertEqual(_wrists(two), ("Granite Bracer", "Granite Bracer"))
        lore = [
            _gear("Hero Bracers", 40, "LORE Equipped", owned_count=2),
            _gear("Granite Bracer", 5, "MAGIC ITEM", owned_count=2),
        ]
        self.assertEqual(_wrists(lore), ("Hero Bracers", "Granite Bracer"))

    def test_blank_flags_are_not_lore(self):
        pool = [
            _gear("Plain Bracer", 30, ""),
            _gear("Other Bracer", 4, None if False else ""),
        ]
        self.assertEqual(_wrists(pool), ("Plain Bracer", "Plain Bracer"))


if __name__ == "__main__":
    unittest.main()
