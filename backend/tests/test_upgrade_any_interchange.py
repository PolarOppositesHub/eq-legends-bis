"""Any↔real-slot upgrade interchange — non-weapons only; never invents stats."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import inventory as inv  # noqa: E402


def _row(slot: str, name: str, *, is_weapon: bool = False, **extra) -> dict:
    out = {
        "slot": slot,
        "name": name,
        "why": f"{slot} pick",
        "is_weapon": is_weapon,
        "stats_at_upgrade": extra.pop("stats_at_upgrade", {}),
        "alts": extra.pop("alts", []),
        "url": extra.pop("url", ""),
        "zone": extra.pop("zone", ""),
    }
    out.update(extra)
    return out


class InterchangeHelperTests(unittest.TestCase):
    def test_swaps_any_when_non_weapon_already_on_real_slot(self):
        slots = [
            _row("CHEST", "Better Chestplate", url="chest-url"),
            _row("ANY2", "Valorium Chestplate", url="val-url", planner_slots=["CHEST"]),
        ]
        inv.interchange_any_real_slot_recommendations(
            slots, {"CHEST": "Valorium Chestplate"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["ANY2"]["name"], "Better Chestplate")
        self.assertEqual(by_slot["CHEST"]["name"], "Valorium Chestplate")
        self.assertEqual(by_slot["ANY2"]["url"], "chest-url")
        self.assertEqual(by_slot["CHEST"]["url"], "val-url")
        self.assertEqual(by_slot["ANY2"]["_interchange"]["from_slot"], "CHEST")
        self.assertEqual(by_slot["ANY2"]["_interchange"]["equipped"], "Valorium Chestplate")

    def test_clears_any_when_same_item_is_already_real_slot_bis(self):
        slots = [
            _row("CHEST", "Valorium Chestplate", planner_slots=["CHEST"]),
            _row("ANY2", "Valorium Chestplate", planner_slots=["CHEST"]),
        ]
        inv.interchange_any_real_slot_recommendations(
            slots, {"CHEST": "Valorium Chestplate"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["CHEST"]["name"], "Valorium Chestplate")
        self.assertEqual(by_slot["ANY2"]["name"], "")

    def test_does_not_interchange_weapons(self):
        slots = [
            _row("PRIMARY", "Better Blade", is_weapon=True),
            _row("ANY2", "Worn Blade", is_weapon=True),
        ]
        inv.interchange_any_real_slot_recommendations(
            slots, {"PRIMARY": "Worn Blade"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["ANY2"]["name"], "Worn Blade")
        self.assertEqual(by_slot["PRIMARY"]["name"], "Better Blade")
        self.assertNotIn("_interchange", by_slot["ANY2"])

    def test_weapon_slot_location_blocks_interchange_even_if_flag_missing(self):
        slots = [
            _row("PRIMARY", "Better Blade", is_weapon=True),
            _row("ANY1", "Worn Blade"),  # no is_weapon key
        ]
        del slots[1]["is_weapon"]
        slots[1]["planner_slots"] = ["PRIMARY"]
        inv.interchange_any_real_slot_recommendations(
            slots, {"PRIMARY": "Worn Blade"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["ANY1"]["name"], "Worn Blade")
        self.assertEqual(by_slot["PRIMARY"]["name"], "Better Blade")

    def test_no_swap_when_item_not_equipped_on_real_slot(self):
        slots = [
            _row("CHEST", "Better Chestplate"),
            _row("ANY2", "Valorium Chestplate"),
        ]
        inv.interchange_any_real_slot_recommendations(
            slots, {"CHEST": "Other Plate", "ANY2": "Trinket"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["ANY2"]["name"], "Valorium Chestplate")
        self.assertEqual(by_slot["CHEST"]["name"], "Better Chestplate")

    def test_name_match_is_case_insensitive(self):
        slots = [
            _row("LEGS", "Better Leggings"),
            _row("ANY1", "valorium greaves", planner_slots=["LEGS"]),
        ]
        inv.interchange_any_real_slot_recommendations(
            slots, {"LEGS": "Valorium Greaves"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["ANY1"]["name"], "Better Leggings")
        self.assertEqual(by_slot["LEGS"]["name"], "valorium greaves")

    def test_requires_items_real_slot_not_an_unrelated_slot(self):
        slots = [
            _row("CHEST", "Better Chestplate"),
            _row("ANY2", "Stalwart Shield", planner_slots=["SECONDARY"]),
        ]
        inv.interchange_any_real_slot_recommendations(
            slots, {"CHEST": "Stalwart Shield"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["ANY2"]["name"], "Stalwart Shield")
        self.assertEqual(by_slot["CHEST"]["name"], "Better Chestplate")

    def test_two_any_slots_swap_independently(self):
        slots = [
            _row("CHEST", "Better Chestplate"),
            _row("HEAD", "Better Helm"),
            _row("ANY1", "Worn Helm", planner_slots=["HEAD"]),
            _row("ANY2", "Worn Chest", planner_slots=["CHEST"]),
        ]
        inv.interchange_any_real_slot_recommendations(
            slots, {"CHEST": "Worn Chest", "HEAD": "Worn Helm"}
        )
        by_slot = {r["slot"]: r for r in slots}
        self.assertEqual(by_slot["ANY2"]["name"], "Better Chestplate")
        self.assertEqual(by_slot["ANY1"]["name"], "Better Helm")
        self.assertEqual(by_slot["CHEST"]["name"], "Worn Chest")
        self.assertEqual(by_slot["HEAD"]["name"], "Worn Helm")


class SuggestUpgradesInterchangeTests(unittest.TestCase):
    def test_suggest_upgrades_applies_non_weapon_swap(self):
        bis = {
            "slots": [
                _row("CHEST", "Better Chestplate", why="chest bis"),
                _row("ANY2", "Valorium Chestplate", why="any leftover", planner_slots=["CHEST"]),
                _row("PRIMARY", "Best Sword", is_weapon=True, why="weapon"),
            ],
            "classes": ["Warrior"],
            "mode": "AI Choice",
            "upgrade": 10,
            "character_level": 50,
            "pool_size": 3,
        }
        with (
            patch.object(inv.engine, "recommend_bis", return_value=bis),
            patch.object(inv.engine, "items_for_slot", return_value=[]),
            patch.object(inv, "_enrich_obtain", return_value={"how": "unknown"}),
            patch.object(inv, "_catalog_has_name", return_value=True),
            patch.object(inv.item_catalog_mod, "get_item_by_name", return_value=None),
        ):
            out = inv.suggest_upgrades(
                ["Warrior"],
                {"CHEST": "Valorium Chestplate"},
                fetch_quest_guides=False,
            )
        by_slot = {s["slot"]: s for s in out["suggestions"]}
        self.assertIn("ANY2", by_slot)
        self.assertEqual(by_slot["ANY2"]["suggested"], "Better Chestplate")
        self.assertNotIn("CHEST", by_slot)
        self.assertIn("Any↔CHEST interchange", by_slot["ANY2"]["reason"])
        self.assertEqual(by_slot["PRIMARY"]["suggested"], "Best Sword")

    def test_suggest_upgrades_leaves_weapon_any_pick_alone(self):
        bis = {
            "slots": [
                _row("PRIMARY", "Better Blade", is_weapon=True, why="primary bis"),
                _row("ANY2", "Worn Blade", is_weapon=True, why="any leftover"),
            ],
            "classes": ["Warrior"],
            "mode": "AI Choice",
            "upgrade": 10,
            "character_level": 50,
            "pool_size": 2,
        }
        with (
            patch.object(inv.engine, "recommend_bis", return_value=bis),
            patch.object(inv.engine, "items_for_slot", return_value=[]),
            patch.object(inv, "_enrich_obtain", return_value={"how": "unknown"}),
            patch.object(inv, "_catalog_has_name", return_value=True),
            patch.object(inv.item_catalog_mod, "get_item_by_name", return_value=None),
        ):
            out = inv.suggest_upgrades(
                ["Warrior"],
                {"PRIMARY": "Worn Blade"},
                fetch_quest_guides=False,
            )
        by_slot = {s["slot"]: s for s in out["suggestions"]}
        self.assertEqual(by_slot["ANY2"]["suggested"], "Worn Blade")
        self.assertEqual(by_slot["PRIMARY"]["suggested"], "Better Blade")
        self.assertIsNone(by_slot["ANY2"].get("interchange"))


if __name__ == "__main__":
    unittest.main()
