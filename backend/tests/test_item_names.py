"""Owned-name folding and the Slime Blood of Cazic-Thule spelling."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.inventory import parse_inventory_tsv  # noqa: E402
from app.item_catalog import catalog_match, get_item_by_name
from app.item_names import canonical_item_name, names_match, owned_name_key

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "slime_blood_hands_inventory.txt"
GAME = "Slime Blood of Cazic-Thule"
OLD = "Slime Blood of Cazic Thule"


class ItemNameTests(unittest.TestCase):
    def test_owned_key_folds_case_hyphen_apostrophe_and_space(self):
        self.assertEqual(
            owned_name_key("  Slime Blood of Cazic-Thule +5"),
            owned_name_key("slime  blood of cazic thule"),
        )
        self.assertTrue(names_match("Crushbone Cadet`s Grimoire", "Crushbone Cadet's Grimoire"))
        self.assertTrue(names_match("Crushbone Cadet’s Grimoire", "Crushbone Cadets Grimoire"))
        self.assertTrue(names_match("Packmaster's Lash", "Packmasters Lash"))
        self.assertFalse(names_match("Synthetic Stone", "Synthetic Stone (Exaltation)"))

    def test_old_slime_blood_spelling_is_an_alias(self):
        self.assertEqual(canonical_item_name(OLD), GAME)
        self.assertEqual(canonical_item_name(f"{GAME} +5"), GAME)
        self.assertEqual(canonical_item_name("Cloak of Leaves"), "Cloak of Leaves")

    def test_catalog_resolves_both_slime_blood_spellings_without_inventing_an_id(self):
        for spelling in (GAME, OLD, f"{GAME} +5"):
            match = catalog_match(spelling, item_id="20655")
            self.assertTrue(match["matched"], spelling)
            self.assertEqual(match["name"], GAME)
            self.assertEqual(match["source"], "tools")
            self.assertIn("HANDS", match["slots"])
            self.assertTrue(match["has_stats"])
            self.assertIsNone(match["itemID"])
        self.assertFalse(catalog_match("Nope", item_id="20655")["matched"])
        item = get_item_by_name(OLD, enrich=False)
        self.assertIsNotNone(item)
        self.assertEqual(item["name"], GAME)
        self.assertTrue(item.get("stats_plus0") or item.get("stats_plus10"))

    def test_apostrophe_export_matches_catalog_without_a_rename(self):
        match = catalog_match("Crushbone Cadet`s Grimoire")
        self.assertTrue(match["matched"])
        self.assertEqual(match["name"], "Crushbone Cadet's Grimoire")
        self.assertTrue(match["has_stats"])

    def test_packmasters_lash_prefers_the_stats_row(self):
        match = catalog_match("Packmasters Lash")
        self.assertTrue(match["matched"])
        self.assertEqual(match["name"], "Packmaster's Lash")
        self.assertTrue(match["has_stats"])

    def test_inventory_fixture_equips_game_spelling_and_both_wrists(self):
        parsed = parse_inventory_tsv(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(parsed["equipment"].get("HANDS"), GAME)
        self.assertEqual(parsed["equipment"].get("WRIST1"), "Valorium Bracers")
        self.assertEqual(parsed["equipment"].get("WRIST2"), "Lustrous Russet Bracer")
        hands = next(row for row in parsed["worn"] if row.get("planner_slot") == "HANDS")
        self.assertTrue(hands["in_catalog"])
        self.assertEqual(hands["id"], "20655")


if __name__ == "__main__":
    unittest.main()
