"""Worn enchant vs BiS upgrade level — never substitute +10 for a lower worn level."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import inventory as inv  # noqa: E402


def _row(slot: str, name: str, **extra) -> dict:
    out = {
        "slot": slot,
        "name": name,
        "why": f"{slot} pick",
        "is_weapon": extra.pop("is_weapon", False),
        "stats_plus0": extra.pop("stats_plus0", {"HP": 100, "AC": 10}),
        "stats_plus10": extra.pop("stats_plus10", {"HP": 200, "AC": 20}),
        "stats_at_upgrade": extra.pop("stats_at_upgrade", {"HP": 200, "AC": 20}),
        "alts": extra.pop("alts", []),
        "url": extra.pop("url", ""),
        "zone": extra.pop("zone", ""),
    }
    out.update(extra)
    return out


class StatsAtLevelHelperTests(unittest.TestCase):
    def test_scales_from_plus0_not_plus10_at_worn_zero(self):
        item = {
            "name": "Worn Plate",
            "stats_plus0": {"HP": 50, "AC": 5},
            "stats_plus10": {"HP": 100, "AC": 10},
            "stats_at_upgrade": {},
        }
        stats = inv._stats_at_level(item, 0)
        self.assertEqual(stats.get("HP"), 50)
        self.assertEqual(stats.get("AC"), 5)

    def test_does_not_use_plus10_when_plus0_missing_and_level_below_10(self):
        item = {
            "name": "Mystery",
            "stats_plus0": {},
            "stats_plus10": {"HP": 999},
            "stats_at_upgrade": {"HP": 40},
        }
        stats = inv._stats_at_level(item, 3)
        self.assertEqual(stats.get("HP"), 40)

    def test_plus10_only_when_level_is_10_and_no_plus0(self):
        item = {
            "name": "Mystery",
            "stats_plus0": {},
            "stats_plus10": {"HP": 999},
            "stats_at_upgrade": {},
        }
        stats = inv._stats_at_level(item, 10)
        self.assertEqual(stats.get("HP"), 999)


class SuggestUpgradesWornLevelTests(unittest.TestCase):
    def test_payload_exposes_current_and_suggested_upgrade(self):
        bis = {
            "slots": [
                _row("CHEST", "Better Chestplate", stats_plus0={"HP": 80}, stats_plus10={"HP": 160},
                     stats_at_upgrade={"HP": 160}),
            ],
            "classes": ["Warrior"],
            "mode": "AI Choice",
            "upgrade": 10,
            "character_level": 50,
            "pool_size": 1,
        }
        worn_pool = [{
            "name": "Worn Plate",
            "stats_plus0": {"HP": 40},
            "stats_plus10": {"HP": 80},
            "stats_at_upgrade": {},
        }]
        with (
            patch.object(inv.engine, "recommend_bis", return_value=bis),
            patch.object(inv.engine, "items_for_slot", return_value=worn_pool),
            patch.object(inv, "_enrich_obtain", return_value={"how": "unknown"}),
            patch.object(inv, "_catalog_has_name", return_value=True),
        ):
            out = inv.suggest_upgrades(
                ["Warrior"],
                {"CHEST": "Worn Plate"},
                upgrade=10,
                slot_upgrades={"CHEST": 3},
                fetch_quest_guides=False,
            )
        sug = out["suggestions"][0]
        self.assertEqual(sug["current"], "Worn Plate")
        self.assertEqual(sug["suggested"], "Better Chestplate")
        self.assertEqual(sug["current_upgrade"], 3)
        self.assertEqual(sug["suggested_upgrade"], 10)
        cmp = out["equipment_compare"][0]
        self.assertEqual(cmp["worn"]["upgrade"], 3)
        self.assertEqual(cmp["suggested_upgrade"], 10)
        # Worn HP is scaled from +0 at +3, not the +10 value of 80
        worn_hp = cmp["worn"]["stats"].get("HP")
        self.assertIsNotNone(worn_hp)
        self.assertNotEqual(worn_hp, 80)
        self.assertLess(worn_hp, 80)

    def test_empty_stats_at_upgrade_does_not_fall_back_to_plus10(self):
        bis = {
            "slots": [
                _row(
                    "HEAD",
                    "Better Helm",
                    stats_plus0={"HP": 30},
                    stats_plus10={"HP": 60},
                    stats_at_upgrade={"HP": 60},
                ),
            ],
            "classes": ["Warrior"],
            "mode": "AI Choice",
            "upgrade": 10,
            "character_level": 50,
            "pool_size": 1,
        }
        worn_pool = [{
            "name": "Old Helm",
            "stats_plus0": {"HP": 20},
            "stats_plus10": {"HP": 40},
            "stats_at_upgrade": {},
        }]
        with (
            patch.object(inv.engine, "recommend_bis", return_value=bis),
            patch.object(inv.engine, "items_for_slot", return_value=worn_pool),
            patch.object(inv, "_enrich_obtain", return_value={"how": "unknown"}),
            patch.object(inv, "_catalog_has_name", return_value=True),
        ):
            out = inv.suggest_upgrades(
                ["Warrior"],
                {"HEAD": "Old Helm"},
                upgrade=10,
                slot_upgrades={"HEAD": 0},
                fetch_quest_guides=False,
            )
        cmp = {r["slot"]: r for r in out["equipment_compare"]}["HEAD"]
        self.assertEqual(cmp["worn"]["upgrade"], 0)
        self.assertEqual(cmp["worn"]["stats"].get("HP"), 20)
        sug = {s["slot"]: s for s in out["suggestions"]}["HEAD"]
        self.assertEqual(sug["current_upgrade"], 0)
        self.assertEqual(sug["suggested_upgrade"], 10)


if __name__ == "__main__":
    unittest.main()
