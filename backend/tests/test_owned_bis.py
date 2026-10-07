"""Owned-only BiS re-ranks from owned names and their recorded +N.

Item names and the +N behavior below were checked against the decoded catalog.
Missing +N uses the planner upgrade. It is not treated as +0.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine import recommend_bis  # noqa: E402


def _slot(result: dict, slot: str) -> dict:
    return next(row for row in result["slots"] if row["slot"] == slot)


class OwnedBisTests(unittest.TestCase):
    def test_recorded_upgrade_beats_a_lower_owned_copy(self):
        owned = recommend_bis(
            ["Wizard"],
            mode="max",
            upgrade=10,
            character_level=50,
            prefer_ranged_damage=False,
            owned_items=[
                {"name": "Cloak of Leaves", "upgrade": 10},
                {"name": "Cloak of Shadows", "upgrade": 0},
            ],
        )
        self.assertTrue(owned["owned_only"])
        back = _slot(owned, "BACK")
        self.assertEqual(back["name"], "Cloak of Leaves")
        self.assertEqual(back["upgrade"], 10)
        self.assertEqual((back["stats_at_upgrade"] or {}).get("AC"), 15)

        missing = recommend_bis(
            ["Wizard"],
            mode="max",
            upgrade=10,
            character_level=50,
            prefer_ranged_damage=False,
            owned_items=[
                {"name": "Cloak of Leaves", "upgrade": None},
                {"name": "Cloak of Shadows", "upgrade": None},
            ],
        )
        self.assertEqual(_slot(missing, "BACK")["name"], "Cloak of Shadows")
        self.assertEqual((_slot(missing, "BACK")["stats_at_upgrade"] or {}).get("AC"), 24)

    def test_owned_haste_level_and_single_haste_still_apply(self):
        result = recommend_bis(
            ["Wizard"],
            mode="max",
            upgrade=10,
            character_level=50,
            prefer_ranged_damage=False,
            owned_items=[
                {"name": "Cloak of Flames", "upgrade": 5},
                {"name": "Flowing Black Silk Sash", "upgrade": 10},
            ],
        )
        back = _slot(result, "BACK")
        self.assertEqual(back["name"], "Cloak of Flames")
        self.assertEqual(back["upgrade"], 5)
        self.assertEqual(back["haste"], 41)
        self.assertEqual((back["stats_at_upgrade"] or {}).get("AC"), 15)
        self.assertEqual(len(result["haste_in_loadout"]), 1)
        self.assertEqual(result["haste_in_loadout"][0]["name"], "Cloak of Flames")
        self.assertEqual(_slot(result, "WAIST")["name"], "")
        self.assertEqual(_slot(result, "PRIMARY")["name"], "")

    def test_normal_bis_omits_the_owned_only_pool(self):
        result = recommend_bis(
            ["Wizard"],
            mode="max",
            upgrade=10,
            character_level=50,
            prefer_ranged_damage=False,
        )
        self.assertFalse(result["owned_only"])
        self.assertNotEqual(_slot(result, "BACK")["name"], "")
