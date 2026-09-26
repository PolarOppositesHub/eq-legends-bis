"""Smoke test of the sidecar routes that exist on v1.0.23.

Each call must return 200 and include the top-level keys the UI reads.
Item detail image lookup is stubbed so the suite does not call eqlwiki.
The XLSX route is expected to answer even when the external planner tree
it shells out to is absent; this test checks the contract, not ok=true.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.engine import apply_worn_haste, scale_stats_to_level  # noqa: E402
from app.main import app  # noqa: E402


INVENTORY = (
    "Location\tName\tID\tCount\tSlots\n"
    "Back\tCloak of Flames\t1\t1\t10\n"
    "Waist\tFlowing Black Silk Sash +10\t2\t1\t10\n"
)


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def _expect(self, response, keys):
        self.assertEqual(response.status_code, 200, response.text[:500])
        body = response.json()
        self.assertIsInstance(body, dict)
        missing = [key for key in keys if key not in body]
        self.assertFalse(missing, f"missing keys {missing} in {sorted(body)}")
        return body

    def test_health_meta_classes_races(self):
        health = self._expect(self.client.get("/api/health"), ["ok", "version", "instance"])
        self.assertTrue(health["ok"])
        self.assertEqual(health["version"], "1.0.23")
        self._expect(
            self.client.get("/api/meta"),
            ["classes", "slots", "version", "haste_rule", "modes", "upgrade_levels"],
        )
        classes = self._expect(
            self.client.get("/api/classes"),
            ["classes", "modes", "slots", "priority_stats", "haste_note"],
        )
        self.assertIn("Wizard", classes["classes"])
        self._expect(self.client.get("/api/races"), ["races", "class_stats", "bases_available"])
        self._expect(
            self.client.get("/api/priority-defaults", params={"classes": "Wizard,Cleric"}),
            ["classes", "primary_stats", "secondary_stats", "tertiary_stats"],
        )
        self._expect(self.client.get("/api/help/inventory"), ["markdown", "path"])

    def test_bis_and_simulate(self):
        bis = self._expect(
            self.client.post("/api/bis", json={
                "classes": ["Wizard", "Enchanter"],
                "mode": "priority",
                "priority_stat": "INT",
                "alts": 2,
                "upgrade": 0,
            }),
            ["classes", "slots", "haste_rule", "upgrade", "mode", "pool_size"],
        )
        self.assertEqual(bis["upgrade"], 0)
        self.assertLessEqual(len(bis.get("haste_in_loadout") or []), 1)
        sim = self._expect(
            self.client.post("/api/simulate", json={
                "classes": ["Wizard"],
                "race": "Human",
                "upgrade": 10,
                "equipment": {
                    "BACK": "Cloak of Flames",
                    "WAIST": "Flowing Black Silk Sash",
                },
            }),
            ["totals", "haste", "equipment", "classes", "race", "warnings"],
        )
        totals = sim["totals"]
        for key in ("HP", "MANA", "END", "INT", "Haste"):
            self.assertIn(key, totals)
        self.assertEqual(sim["haste"]["applied_pct"], 46)
        self.assertTrue(sim["haste_warning"])

    def test_item_search_and_detail_slider(self):
        found = self._expect(
            self.client.get("/api/item-search", params={"q": "cloak of flames", "limit": 5}),
            ["total", "items", "query", "offset", "limit"],
        )
        self.assertEqual([item["name"] for item in found["items"]], ["Cloak of Flames"])
        with patch(
            "app.main.item_catalog_mod.ensure_item_image",
            return_value={"name": "Cloak of Flames", "cached": False, "error": "stubbed in test"},
        ):
            detail = self._expect(
                self.client.get("/api/item-detail", params={"name": "Cloak of Flames"}),
                ["name", "stats_plus0", "stats_plus10", "image"],
            )
        self.assertEqual(detail["stats_plus0"]["Haste"], 36)
        scaled = {}
        for level in (0, 5, 10):
            stats = scale_stats_to_level(detail["stats_plus0"], level)
            apply_worn_haste(stats, detail["stats_plus0"], level, detail["stats_plus10"])
            scaled[level] = stats["Haste"]
        self.assertEqual(scaled, {0: 36, 5: 41, 10: 46})

    def test_inventory_routes(self):
        parsed = self._expect(
            self.client.post("/api/inventory/parse", json={"text": INVENTORY}),
            ["equipment", "all_items", "worn", "warnings", "upgrade_hints"],
        )
        self.assertEqual(parsed["equipment"].get("BACK"), "Cloak of Flames")
        imported = self._expect(
            self.client.post("/api/inventory/import", json={"text": INVENTORY}),
            ["ok", "equipment", "all_items", "warnings", "upgrade_hints"],
        )
        self.assertTrue(imported["ok"])
        self.assertEqual(imported["upgrade_hints"].get("WAIST"), 10)
        suggestions = self._expect(
            self.client.post("/api/inventory/upgrade-suggestions", json={
                "classes": ["Wizard"],
                "equipment": {"BACK": "Cloak of Flames"},
                "upgrade": 0,
                "fetch_quest_guides": False,
            }),
            ["suggestions", "equipment", "equipment_compare", "bis_summary"],
        )
        self.assertEqual(suggestions["equipment"].get("BACK"), "Cloak of Flames")

    def test_export_xlsx_contract(self):
        body = self._expect(
            self.client.post("/api/export/xlsx", json={"classes": ["Wizard"]}),
            ["ok", "path", "classes", "returncode", "stdout_tail", "stderr_tail", "outputs"],
        )
        self.assertEqual(body["classes"], ["Wizard"])
        self.assertIn("xlsx", body["outputs"])


if __name__ == "__main__":
    unittest.main()
