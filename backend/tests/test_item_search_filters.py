"""Item search filters and three-level sort against the decoded catalog.

Assertions use names and stat keys the catalog already has. No stats are invented.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.item_catalog import item_stat_value, search_items  # noqa: E402


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
