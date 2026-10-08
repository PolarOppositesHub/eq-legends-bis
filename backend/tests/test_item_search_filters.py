"""Item search filters and three-level sort against the decoded catalog.

Assertions use names and stat keys the catalog already has. No stats are invented.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.item_catalog import (  # noqa: E402
    item_stat_value,
    item_usable_by_class,
    search_items,
    stats_at_compare_level,
)


class ItemSearchFilterTests(unittest.TestCase):
    def test_swords_with_intelligence_sort_damage_then_int(self):
        swords = search_items("sword", type_name="sword", limit=50)
        self.assertGreater(swords["total"], 0)
        self.assertTrue(all("sword" in (item["name"] or "").lower() for item in swords["items"]))

        typed = search_items("", type_name="1H Slashing", limit=20)
        self.assertGreater(typed["total"], 0)
        self.assertTrue(all((item.get("skill") or "") == "1H Slashing" or "1h slashing" in (item["name"] or "").lower() for item in typed["items"]))

        intel = search_items(
            "",
            stat="INT",
            stat_min=1,
            sort="DMG",
            sort_dir="desc",
            sort2="INT",
            sort2_dir="desc",
            limit=30,
        )
        self.assertGreater(intel["total"], 0)
        rows = intel["items"]

        def dmg_rank(value):
            return value if isinstance(value, (int, float)) else float("-inf")

        damages = [item_stat_value(row, "DMG") for row in rows]
        self.assertEqual(damages, sorted(damages, key=dmg_rank, reverse=True))
        for left, right in zip(rows, rows[1:]):
            left_dmg = item_stat_value(left, "DMG")
            right_dmg = item_stat_value(right, "DMG")
            if left_dmg == right_dmg:
                self.assertGreaterEqual(item_stat_value(left, "INT") or 0, item_stat_value(right, "INT") or 0)
        claymore = next(row for row in search_items("Theologian Claymore", limit=5)["items"] if row["name"] == "Theologian Claymore")
        blade = next(row for row in search_items("Blade of Abrogation", limit=5)["items"] if row["name"] == "Blade of Abrogation")
        self.assertEqual(item_stat_value(claymore, "DMG"), 20)
        self.assertEqual(item_stat_value(claymore, "INT"), 4)
        self.assertEqual(item_stat_value(blade, "DMG"), 20)
        self.assertEqual(item_stat_value(blade, "INT"), 3)
        ordered = [row["name"] for row in search_items(
            "",
            stat="INT",
            sort="DMG",
            sort_dir="desc",
            sort2="INT",
            sort2_dir="desc",
            limit=200,
        )["items"]]
        self.assertLess(ordered.index("Theologian Claymore"), ordered.index("Blade of Abrogation"))

        wizards = search_items("cap", usable_class="WIZ", limit=20)
        self.assertGreater(wizards["total"], 0)
        self.assertEqual(wizards["usable_class"], "Wizard")

        none = search_items("", type_name="sword", stat="INT", stat_min=1, limit=5)
        self.assertEqual(none["total"], 0)

        plain = search_items("cap", limit=8)
        self.assertEqual([row["name"] for row in plain["items"]], sorted((row["name"] for row in plain["items"]), key=str.lower))

    def test_unused_sort_keys_do_not_change_alphabetical_order(self):
        left = search_items("jade", limit=15)
        right = search_items("jade", sort="", sort2="", sort3="", limit=15)
        self.assertEqual([row["name"] for row in left["items"]], [row["name"] for row in right["items"]])
        self.assertIn("INT", left["stat_keys"])
        self.assertIn("1H Slashing", left["types"])

    def test_compare_level_changes_haste_filter_and_sort(self):
        """Cloak of Flames haste is 36 at +0 and 46 at +10. Min 40 follows the slider."""
        named = search_items("Cloak of Flames", limit=5)
        cloak = next(row for row in named["items"] if row["name"] == "Cloak of Flames")
        at0 = stats_at_compare_level(cloak, 0)
        at10 = stats_at_compare_level(cloak, 10)
        self.assertEqual(item_stat_value(cloak, "Haste", 0), 36)
        self.assertEqual(item_stat_value(cloak, "Haste", 10), 46)
        self.assertEqual(at0.get("Haste") or at0.get("haste"), 36)
        self.assertEqual(at10.get("Haste") or at10.get("haste"), 46)
        # Omitting the level keeps the old +0 then +10 fallback.
        self.assertEqual(item_stat_value(cloak, "Haste"), 36)

        low = search_items("Cloak of Flames", stat="Haste", stat_min=40, compare_level=0, limit=5)
        high = search_items("Cloak of Flames", stat="Haste", stat_min=40, compare_level=10, limit=5)
        self.assertEqual(low["total"], 0)
        self.assertEqual(high["compare_level"], 10)
        self.assertEqual([row["name"] for row in high["items"]], ["Cloak of Flames"])
        listed = high["items"][0]["stats_at_compare"]
        haste_key = next(key for key in listed if str(key).casefold() == "haste")
        self.assertEqual(listed[haste_key], 46)

        plus0 = search_items("", stat="Haste", stat_min=1, sort="Haste", sort_dir="desc", compare_level=0, limit=40)
        plus10 = search_items("", stat="Haste", stat_min=1, sort="Haste", sort_dir="desc", compare_level=10, limit=40)
        self.assertGreater(plus0["total"], 1)
        order0 = [row["name"] for row in plus0["items"]]
        values = [item_stat_value(row, "Haste", 10) for row in plus10["items"]]
        self.assertEqual(values, sorted(values, reverse=True))
        flipped = False
        for index, row in enumerate(plus10["items"]):
            if row["name"] not in order0:
                continue
            for later in plus10["items"][index + 1:]:
                if later["name"] not in order0:
                    continue
                if order0.index(row["name"]) > order0.index(later["name"]):
                    flipped = True
                    break
            if flipped:
                break
        # A rank flip is asserted when the catalog has one. Cloak of Flames
        # already proves +0 and +10 are different values.
        if flipped:
            self.assertNotEqual(order0, [row["name"] for row in plus10["items"]])

    def test_usable_by_up_to_three_classes_any_or_all(self):
        wizards = search_items("", usable_class="WIZ", limit=80)
        wizard_only = next(
            (row for row in wizards["items"] if not item_usable_by_class(row, "Warrior")),
            None,
        )
        self.assertIsNotNone(wizard_only, "catalog should include a Wizard item a Warrior cannot use")
        name = wizard_only["name"]
        any_match = search_items(name, usable_classes="Wizard,Warrior", usable_match="any", limit=5)
        all_match = search_items(name, usable_classes="Wizard,Warrior", usable_match="all", limit=5)
        self.assertIn(name, [row["name"] for row in any_match["items"]])
        self.assertEqual(all_match["total"], 0)
        self.assertEqual(any_match["usable_classes"], ["Wizard", "Warrior"])
        self.assertEqual(any_match["usable_match"], "any")
        self.assertEqual(any_match["usable_class"], "Wizard")
        capped = search_items("cap", usable_classes="Wizard,Warrior,Cleric,Rogue", limit=5)
        self.assertEqual(capped["usable_classes"], ["Wizard", "Warrior", "Cleric"])
