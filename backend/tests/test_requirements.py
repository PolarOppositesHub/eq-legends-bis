"""Upgrade math and Plane of Sky progress. SPEC §9.

Mote item XP comes from the ledger table. The achievements fixture is a
short tree in the verified I/C shape. Reward names are copied from
data/pos_class_tests.json. Nothing here is a new formula or a new test name.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.achievements import achievement_test_status, parse_achievements  # noqa: E402
from app.requirements import build_upgrade_plan, parse_offer_line, plane_of_sky  # noqa: E402
from app.upgrade_path import (  # noqa: E402
    cheapest_motes,
    cumulative_xp,
    duplicate_xp,
    plan_upgrades,
    tier_step_xp,
    xp_still_needed,
)


def _counts(rows):
    return {row["name"]: row["count"] for row in rows}


class UpgradeMathTests(unittest.TestCase):
    def test_tier_xp_and_duplicate_plus_3(self):
        self.assertEqual(tier_step_xp(0), 1)
        self.assertEqual(tier_step_xp(3), 8)
        self.assertEqual(duplicate_xp(3), 8)
        self.assertEqual(cumulative_xp(4), 15)
        self.assertEqual(cumulative_xp(10), 1023)
        self.assertEqual(xp_still_needed(9, 10, 0), 512)
        self.assertEqual(xp_still_needed(3, 4, 0) - 8, 0)

    def test_seven_mote_path_to_plus_4(self):
        rows = cheapest_motes(0, 0, 4)
        self.assertEqual(_counts(rows), {
            "Mote of Infinitesimal Potential": 1,
            "Mote of Minor Potential": 2,
            "Mote of Lesser Potential": 2,
            "Mote of Potential": 2,
        })
        self.assertEqual(sum(row["count"] for row in rows), 7)

    def test_plus_9_to_10_is_infinite_or_void_touched(self):
        rows = cheapest_motes(9, 0, 10)
        self.assertEqual(_counts(rows), {"Mote of Infinite Potential": 52})
        self.assertEqual(sum(row["total_item_xp"] for row in rows), 520)
        plan = plan_upgrades(
            [{"id": "a", "name": "Example", "current_tier": 9, "target_tier": 10,
              "copy_info": {"owned": True, "tier_known": True, "current_tier": 9,
                            "duplicates": [], "duplicate_xp": 0, "unknown_tier_copies": 0}}],
            {},
            1,
        )
        item = plan["items"][0]
        self.assertEqual(item["xp_needed"], 512)
        self.assertEqual(len(item["void_touched"]), 1)
        self.assertEqual(item["void_touched"][0]["tier"], 9)
        self.assertEqual(item["missing"], [])
        self.assertTrue(item["high_tier_note"])

    def test_void_touched_goes_to_the_highest_tier_first(self):
        owned = {
            "owned": True, "tier_known": True, "duplicates": [],
            "duplicate_xp": 0, "unknown_tier_copies": 0,
        }
        plan = plan_upgrades(
            [
                {"id": "low", "name": "Low", "current_tier": 0, "target_tier": 4,
                 "copy_info": {**owned, "current_tier": 0}},
                {"id": "high", "name": "High", "current_tier": 9, "target_tier": 10,
                 "copy_info": {**owned, "current_tier": 9}},
            ],
            {},
            1,
        )
        by_id = {row["id"]: row for row in plan["items"]}
        self.assertEqual(len(by_id["high"]["void_touched_planned"]), 1)
        self.assertEqual(by_id["low"]["void_touched_planned"], [])

    def test_held_motes_and_shortfall_share_one_pool(self):
        owned = {
            "owned": True, "tier_known": True, "duplicates": [],
            "duplicate_xp": 0, "unknown_tier_copies": 0, "current_tier": 0,
        }
        plan = plan_upgrades(
            [
                {"id": "a", "name": "A", "current_tier": 0, "target_tier": 1, "copy_info": owned},
                {"id": "b", "name": "B", "current_tier": 0, "target_tier": 1, "copy_info": dict(owned)},
            ],
            {"Mote of Infinitesimal Potential": 1},
            0,
        )
        by_id = {row["id"]: row for row in plan["items"]}
        self.assertEqual(_counts(by_id["a"]["held_motes"]), {"Mote of Infinitesimal Potential": 1})
        self.assertEqual(by_id["a"]["missing"], [])
        self.assertEqual(_counts(by_id["b"]["missing"]), {"Mote of Infinitesimal Potential": 1})
        self.assertIn("Farm", by_id["b"]["missing"][0]["hint"])

    def test_unknown_tier_is_not_treated_as_plus_0(self):
        plan = build_upgrade_plan(
            [{"name": "Cloak of Flames", "target_tier": 4}],
            [{"name": "Cloak of Flames", "tier": None, "count": 1}],
            holdings={},
            void_touched=0,
        )
        item = plan["items"][0]
        self.assertEqual(item["tier_source"], "unknown")
        self.assertEqual(item["motes"], [])
        self.assertEqual(item["missing"], [])
        self.assertIn("not counted as +0", item["tier_note"])

    def test_duplicate_plus_3_reduces_the_gap(self):
        plan = build_upgrade_plan(
            [{"name": "Cloak of Flames", "target_tier": 4, "current_tier": 0}],
            [
                {"name": "Cloak of Flames +0", "count": 1},
                {"name": "Cloak of Flames +3", "count": 1},
            ],
            holdings={},
            void_touched=0,
        )
        item = plan["items"][0]
        self.assertEqual(item["duplicate_xp"], 8)
        self.assertEqual(item["xp_needed"], 15)
        self.assertEqual(item["xp_after_duplicates"], 7)


ACHIEVEMENTS = (
    "Untapped Potential: Classes\r\n"
    "I\tPrimary Class Unlock - Bard\r\n"
    "C\t\tObtain Mask of Song.\r\n"
    "I\t\tObtain Mantle of the Songweaver.\r\n"
    "I\t\tObtain Windhowl and Spirit Render\r\n"
    "X\t\tObtain Amulet of the Fae.\r\n"
    "I\t\tThis achievement will autocomplete if you chose to confirm your Primary Class as a Bard.\r\n"
    "I\t\tThis achievement can be bypassed using a Primary Class Unlock Token.\r\n"
    "C\tPrimary Class Unlock - Paladin\r\n"
    "C\t\tObtain Girdle of Faith.\r\n"
    "C\t\tThis achievement will autocomplete if you chose to confirm your Primary Class as a Paladin.\r\n"
    "I\t\tThis achievement can be bypassed using a Primary Class Unlock Token.\r\n"
    "C\tPrimary Class Unlock - Shadowknight\r\n"
    "C\t\tObtain Pegasus-Hide Belt.\r\n"
    "I\t\tThis achievement will autocomplete if you chose to confirm your Primary Class as a Shadowknight.\r\n"
    "C\t\tThis achievement can be bypassed using a Primary Class Unlock Token.\r\n"
    "I\t\tThe playable races.\t1293/10000\r\n"
)


class PlaneOfSkyTests(unittest.TestCase):
    def test_achievement_tree_grants_and_unmatched(self):
        tree = parse_achievements(ACHIEVEMENTS)
        self.assertEqual(tree["categories"][0]["name"], "Untapped Potential: Classes")
        progress = achievement_test_status(ACHIEVEMENTS)
        self.assertEqual(progress["done"].get("Bard Test of Tone"), "achievement")
        self.assertNotIn("Bard Test of Voice", progress["done"])
        self.assertNotIn("Paladin Test of Spirit", progress["done"])
        granted = {row["class"]: row for row in progress["classes"]}
        self.assertTrue(granted["Paladin"]["granted"])
        self.assertEqual(granted["Paladin"]["granted_reason"], "autocomplete")
        self.assertFalse(granted["Paladin"]["token_unverified"])
        self.assertTrue(granted["Shadowknight"]["granted"])
        self.assertTrue(granted["Shadowknight"]["token_unverified"])
        reasons = " ".join(row["reason"] for row in progress["unmatched"])
        self.assertIn("does not match", reasons)
        self.assertIn("UNVERIFIED", reasons)
        component = tree["categories"][0]["achievements"][-1]["components"][-1]
        self.assertEqual(component["progress"], "1293/10000")
        self.assertEqual(component["kind"], "other")

    def test_granted_obtain_rows_are_not_turn_ins(self):
        view = plane_of_sky(achievements_text=ACHIEVEMENTS, goal_classes=["Bard"])
        by_quest = {row["quest"]: row for row in view["tests"]}
        self.assertTrue(by_quest["Bard Test of Tone"]["done"])
        self.assertEqual(by_quest["Bard Test of Tone"]["source"], "achievement")
        self.assertFalse(by_quest["Paladin Test of Spirit"]["done"])
        self.assertTrue(by_quest["Paladin Test of Spirit"]["granted_class"])
        classes = {row["class"]: row for row in view["classes"]}
        self.assertEqual(classes["Bard"]["done"], 1)
        self.assertGreater(classes["Bard"]["remaining"], 0)
        self.assertTrue(classes["Bard"]["goal"])
        self.assertEqual(view["classes"][0]["remaining"], min(row["remaining"] for row in view["classes"]))
        self.assertIn("UNVERIFIED", view["granted_note"])

    def test_log_offer_completes_a_test_and_manual_overrides(self):
        offer = parse_offer_line(
            "[Sun Sep 06 19:43:25 2026] You offered 1 Wind Rune Meda to Cilin Spellsinger."
        )
        self.assertEqual(offer["item"], "Wind Rune Meda")
        self.assertEqual(offer["npc"], "Cilin Spellsinger")
        self.assertIsNone(parse_offer_line("You say, 'hello'"))
        view = plane_of_sky(
            offers=[
                {"item": "Wind Rune Meda", "qty": 1, "npc": "Cilin Spellsinger"},
                {"item": "Light Woolen Mask", "qty": 1, "npc": "Cilin Spellsinger"},
            ],
            owned=[{"name": "Light Woolen Mask", "count": 1}],
            wind_runes={"Wind Rune Meda": 1},
        )
        tone = next(row for row in view["tests"] if row["quest"] == "Bard Test of Tone")
        self.assertTrue(tone["done"])
        self.assertEqual(tone["source"], "log")
        self.assertTrue(tone["runes"][0]["met"])
        self.assertTrue(tone["items"][0]["met"])
        overridden = plane_of_sky(
            achievements_text=ACHIEVEMENTS,
            manual={"Bard Test of Tone": "not_done"},
            ignored=["Bard Test of Voice"],
        )
        tone = next(row for row in overridden["tests"] if row["quest"] == "Bard Test of Tone")
        self.assertFalse(tone["done"])
        self.assertEqual(tone["source"], "manual")
        bard = next(row for row in overridden["classes"] if row["class"] == "Bard")
        self.assertGreaterEqual(bard["ignored"], 1)
        self.assertNotIn("Bard Test of Voice", [
            row["quest"] for row in overridden["tests"] if row["ignored"] is False and row["class"] == "Bard" and row["quest"] == "nope"
        ])


class ItemSearchRatioTests(unittest.TestCase):
    def test_ratio_ranking_nonweapons_last_and_plus_10(self):
        from app.item_catalog import damage_delay_ratio, search_items, sort_search_items

        fast = {"name": "Fast", "stats_plus0": {"DMG": 20, "DLY": 20}}
        slow = {"name": "Slow", "stats_plus0": {"DMG": 10, "DLY": 30}}
        cloth = {"name": "Cloth Cap", "stats_plus0": {"AC": 4}}
        none_delay = {"name": "No Delay", "stats_plus0": {"DMG": 10}}
        at0 = sort_search_items(
            [cloth, slow, none_delay, fast],
            [("damage_delay_ratio", "desc")],
            0,
        )
        self.assertEqual([row["name"] for row in at0], ["Fast", "Slow", "Cloth Cap", "No Delay"])
        at0_asc = sort_search_items(
            [cloth, fast, slow],
            [("damage_delay_ratio", "asc")],
            0,
        )
        self.assertEqual(at0_asc[-1]["name"], "Cloth Cap")
        self.assertEqual(damage_delay_ratio(fast, 0)["ratio"], 1.0)
        self.assertEqual(damage_delay_ratio(fast, 10)["ratio"], 2.0)
        self.assertGreater(
            damage_delay_ratio(fast, 10)["ratio"],
            damage_delay_ratio(fast, 0)["ratio"],
        )
        self.assertTrue(damage_delay_ratio(fast, 10)["scales"])
        flat = {"name": "Flat", "stats_plus0": {"DMG": 0, "DLY": 10}}
        self.assertFalse(damage_delay_ratio(flat, 10)["scales"])
        self.assertIn("base values", damage_delay_ratio(flat, 10)["note"] or "")

        found = search_items("Theologian Claymore", limit=5, compare_level=0)
        claymore = next(row for row in found["items"] if row["name"] == "Theologian Claymore")
        low = claymore["damage_delay_ratio"]
        high = search_items("Theologian Claymore", limit=5, compare_level=10)["items"]
        high_row = next(row for row in high if row["name"] == "Theologian Claymore")
        self.assertIsNotNone(low)
        self.assertIsNotNone(high_row["damage_delay_ratio"])
        self.assertGreater(high_row["damage_delay_ratio"], low)
        self.assertEqual(round(low, 2), low)
        self.assertEqual(round(high_row["damage_delay_ratio"], 2), high_row["damage_delay_ratio"])


if __name__ == "__main__":
    unittest.main()
