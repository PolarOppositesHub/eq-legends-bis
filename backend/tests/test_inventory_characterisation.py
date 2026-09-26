"""Characterisation snapshot of today's parse_inventory_tsv.

The fixture is synthetic. It mirrors the Inventory.txt shape (two TSV
tables, +N names, nested -Slot rows, bags) and uses a few names that
already exist in this repo's catalog. It is not a copy of a third-party
dump.

Quirks frozen here, so a later parser change shows up as a golden diff:
- The header is recognised only in the first 20 lines.
- The Table 2 header row is ingested as an item named "Name".
- Equipment / Activated / SharedBank / Personal-Depot rows are "unknown location".
- Nested *-SlotN rows and bags/bank are skipped for planner slots but kept.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.inventory import parse_inventory_tsv  # noqa: E402
from golden_support import assert_golden  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_inventory.txt"


def _project(parsed: dict) -> dict:
    coverage = dict(parsed.get("catalog_coverage") or {})
    index = coverage.get("index_path") or ""
    coverage["index_path"] = Path(str(index)).name if index else ""
    projected = dict(parsed)
    projected["catalog_coverage"] = coverage
    return projected


class InventoryCharacterisationTests(unittest.TestCase):
    def test_synthetic_inventory_snapshot(self):
        text = FIXTURE.read_text(encoding="utf-8")
        parsed = parse_inventory_tsv(text)
        crlf = parse_inventory_tsv(text.replace("\n", "\r\n"))
        self.assertEqual(parsed["equipment"], crlf["equipment"])
        self.assertEqual(parsed["upgrade_hints"], crlf["upgrade_hints"])
        names = [row["name"] for row in parsed["all_items"]]
        self.assertIn("Name", names)
        assert_golden(self, "inventory_synthetic", _project(parsed))

    def test_header_past_line_20_is_not_recognised(self):
        body = "\n".join(["preamble"] * 20 + [
            "Location\tName\tID\tCount\tSlots",
            "Head\tCloak of Flames\t1\t1\t10",
        ])
        parsed = parse_inventory_tsv(body)
        header_rows = [row for row in parsed["all_items"] if row.get("name") == "Name"]
        self.assertTrue(header_rows)
        self.assertEqual(header_rows[0]["location"], "Location")
        self.assertEqual(parsed["equipment"].get("HEAD"), "Cloak of Flames")
        assert_golden(self, "inventory_header_past_20", _project(parsed))

    def test_binary_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_inventory_tsv("MZ\x00this is not Inventory.txt")


if __name__ == "__main__":
    unittest.main()
