"""1.1.18 packaging, catalog update, boot health, and event filter."""
from __future__ import annotations

import asyncio
import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog_update import map_stat_key, merge_item_update  # noqa: E402
from app.item_catalog import _all_flat_items, search_items  # noqa: E402
from app.parser.service import EventHub  # noqa: E402
from app.version import __version__  # noqa: E402
from app.zone_pack import install_packaged_zones  # noqa: E402
from app.zones import load_zones_index, zone_research_dir  # noqa: E402

ZONE = ROOT / "desktop" / "resources" / "data" / "zone-research"
INDEX = ZONE / "zones_index.json"


class Release118Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "1.1.18")

    def test_packaged_zone_index_is_a_tracked_file(self):
        self.assertTrue(INDEX.is_file())
        self.assertFalse(INDEX.is_symlink())
        rel = "desktop/resources/data/zone-research/zones_index.json"
        listed = subprocess.check_output(["git", "ls-files", rel], cwd=ROOT, text=True).strip()
        self.assertEqual(listed, rel)
        for path in ZONE.rglob("*"):
            if path.suffix in {".py", ".sh"}:
                self.fail(f"zone package includes a script: {path}")

    def test_nektropos_zones_and_crysta_level(self):
        load_zones_index.cache_clear()
        found = zone_research_dir()
        self.assertEqual(found, ZONE.resolve())
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        slugs = [row.get("slug") for row in index.get("zones") or []]
        self.assertEqual(slugs, ["nektropos-castle", "lake-nerius"])
        self.assertEqual(index.get("zone_file_count"), 2)
        with (ZONE / "mobs.csv").open(encoding="utf-8", newline="") as handle:
            mobs = list(csv.DictReader(handle))
        self.assertEqual(len(mobs), 28)
        crysta = next(row for row in mobs if row["mob"] == "Crysta Everling")
        self.assertEqual(crysta["level"], "60")
        self.assertIn("CONFLICT:", crysta["spawn_notes"])

    def test_install_fails_when_the_index_is_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "zone-research"
            with self.assertRaises(RuntimeError):
                install_packaged_zones(dest, None, None)

    def test_warsword_ratio_and_checkmate_conflict(self):
        _all_flat_items.cache_clear()
        sword = search_items("Ancient Warsword", limit=5)
        row = next(item for item in sword["items"] if item["name"] == "Ancient Warsword")
        self.assertEqual(row["stats_plus0"]["DMG"], 12)
        self.assertEqual(row["stats_plus0"]["DLY"], 19)
        self.assertEqual(row["damage_delay_ratio"], row["ratio_plus0"])
        self.assertAlmostEqual(row["damage_delay_ratio"], 0.6316, places=4)
        self.assertNotEqual(round(row["damage_delay_ratio"], 2), row["damage_delay_ratio"])
        self.assertNotIn("DMG_BONUS", row["stats_plus0"])
        self.assertEqual(row["ratio_plus10"], 1.2632)
        check = search_items("Checkmate", limit=5)
        item = next(hit for hit in check["items"] if hit["name"] == "Checkmate")
        self.assertEqual(item["stats_plus0"]["WIS"], 5)
        self.assertEqual(item["stats_plus0"]["MANA"], 5)
        self.assertTrue(any("CONFLICT:" in line and "WIS" in line for line in item["source_conflicts"]))
        self.assertIsNone(map_stat_key("Dmg Bonus"))
        self.assertEqual(map_stat_key("Mana Regen"), "MANA_REGEN")

    def test_item_merge_is_idempotent(self):
        added = merge_item_update(
            ROOT / "desktop" / "resources" / "data" / "decoded" / "aggregate.json",
            ROOT / "packaging" / "item-updates" / "2026-10-nektropos" / "items.json",
        )
        self.assertEqual(added, 0)

    def test_boot_health_answers(self):
        from app.boot import app

        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(app({
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/health",
            "raw_path": b"/api/health",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 123),
            "server": ("127.0.0.1", 8765),
        }, receive, send))
        raw = b"".join(message.get("body") or b"" for message in sent if message.get("type") == "http.response.body")
        body = json.loads(raw)
        self.assertEqual(sent[0]["status"], 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["version"], "1.1.18")

    def test_overlay_subscriber_skips_progress(self):
        hub = EventHub()

        async def run():
            alert_q = hub.subscribe(["alert"])
            all_q = hub.subscribe(None)
            progress = {
                "type": "progress",
                "lines": 50000,
                "classified": 1,
                "unclassified": 0,
                "offset": 10,
                "size": 20,
                "path": "C:/EQ/Logs/eqlog_Example_qeynos.txt",
            }
            hub.publish(progress)
            hub.publish({"type": "alert", "alerts": [{"name": "example"}]})
            await asyncio.sleep(0)
            self.assertTrue(all_q.get_nowait()["type"] == "progress")
            self.assertEqual(alert_q.get_nowait()["type"], "alert")
            self.assertTrue(alert_q.empty())
            return len(json.dumps(progress))

        size = asyncio.run(run())
        self.assertGreater(size, 80)
