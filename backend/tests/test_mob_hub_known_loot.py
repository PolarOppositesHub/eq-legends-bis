"""Known Loot parse + catalog/wiki union — sourced names only, never invented."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import mob_hub as mh  # noqa: E402


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "innoruuk_god_loot.html"

WIKI_INNORUUK = [
    "Bloodstar Pendant",
    "Brewer's Mesh Cloak",
    "Cloak of Scales",
    "Darkbrood Mask",
    "Earring of Bashing",
    "Engineer's Ring",
    "Eye of Innoruuk",
    "Hotof's Bracer",
    "Icebelt",
    "Leatherfoot Sandals",
    "Pauldrons of Power",
    "Ring of Pureblood",
    "Shattered Emerald of Corruption",
    "Skinner's Belt",
    "Triumphant Mask",
]


class KnownLootParseTests(unittest.TestCase):
    def test_parse_known_loot_from_fixture(self):
        html = FIXTURE.read_text(encoding="utf-8")
        parsed = mh._parse_namedmobpage(html)
        names = [row["item"] for row in parsed.get("known_loot") or []]
        self.assertEqual(names, WIKI_INNORUUK)
        self.assertEqual(parsed.get("fields", {}).get("level"), "60")
        self.assertEqual(parsed.get("fields", {}).get("zone"), "Plane of Hate")
        self.assertIn("Velious", parsed.get("description") or "")

    def test_stat_block_spells_are_not_loot(self):
        html = """
        <h2 id="Stat_Block">Stat Block</h2>
        <ul><li><a href="/Gravity_Flux" title="Gravity Flux">Gravity Flux</a></li></ul>
        <h2 id="Known_Loot">Known Loot</h2>
        <ul><li><a href="/Icebelt" title="Icebelt">Icebelt</a></li></ul>
        <h2 id="Description">Description</h2>
        """
        names = [r["item"] for r in mh._parse_known_loot(html)]
        self.assertEqual(names, ["Icebelt"])

    def test_unique_and_common_loot_ids(self):
        html = """
        <h2 id="Known_Loot">Unique Loot</h2>
        <ul><li><a href="/Blue_Crystal_Staff" title="Blue Crystal Staff">Blue Crystal Staff</a></li></ul>
        <h2 id="Common_Loot">Common Loot</h2>
        <ul><li><a href="/Classic_Raid_Tier_Treasures" title="Classic Raid Tier Treasures">Classic Raid Tier Treasures</a></li></ul>
        """
        names = [r["item"] for r in mh._parse_known_loot(html)]
        self.assertEqual(names, ["Blue Crystal Staff", "Classic Raid Tier Treasures"])


class CatalogKeyAndUnionTests(unittest.TestCase):
    def test_title_parens_god_bidirectional(self):
        keys = mh._catalog_lookup_keys(
            "Innoruuk (God)",
            ["innoruuk", "innoruuk (god)", "a champion of innoruuk"],
        )
        self.assertIn("innoruuk (god)", keys)
        self.assertIn("innoruuk", keys)
        self.assertNotIn("a champion of innoruuk", keys)

        reverse = mh._catalog_lookup_keys(
            "Innoruuk",
            ["innoruuk", "innoruuk (god)", "a champion of innoruuk"],
        )
        self.assertIn("innoruuk", reverse)
        self.assertIn("innoruuk (god)", reverse)
        self.assertNotIn("a champion of innoruuk", reverse)

    def test_zone_parens_not_merged(self):
        keys = mh._catalog_lookup_keys(
            "a reanimated hand (lower guk)",
            ["a reanimated hand", "a reanimated hand (lower guk)", "a reanimated hand (unrest)"],
        )
        self.assertEqual(keys, ["a reanimated hand (lower guk)"])

    def test_union_dedupes_and_tags_sources(self):
        wiki = [{"item": "Icebelt"}, {"item": "Eye of Innoruuk"}]
        catalog = [
            {"item": "Icebelt", "zone": "Plane of Hate", "source": ["catalog"]},
            {"item": "Truesight Hammer", "zone": "Plane of Hate", "source": ["catalog"]},
        ]
        union = mh._union_drops(wiki, catalog, default_zone="Plane of Hate")
        by_name = {r["item"]: r for r in union}
        self.assertEqual(set(by_name), {"Eye of Innoruuk", "Icebelt", "Truesight Hammer"})
        self.assertEqual(by_name["Icebelt"]["source"], ["eqlwiki", "catalog"])
        self.assertEqual(by_name["Eye of Innoruuk"]["source"], ["eqlwiki"])
        self.assertEqual(by_name["Truesight Hammer"]["source"], ["catalog"])


if __name__ == "__main__":
    unittest.main()
