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
        rel = "desktop/resources/data/zone-research"
        listed = subprocess.check_output(["git", "ls-files", rel], cwd=ROOT, text=True).splitlines()
        packaged = []
        for path in ZONE.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in {".py", ".sh"}:
                self.fail(f"zone package includes a script: {path}")
            self.assertFalse(path.is_symlink(), path)
            packaged.append(path.relative_to(ROOT).as_posix())
        self.assertIn(f"{rel}/zones_index.json", listed)
        self.assertEqual(sorted(packaged), sorted(listed))
        self.assertGreaterEqual(len([name for name in packaged if name.endswith(".json") and "/zones/" in name]), 56)

    def test_nektropos_zones_and_crysta_level(self):
        load_zones_index.cache_clear()
        found = zone_research_dir()
        self.assertEqual(found, ZONE.resolve())
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        slugs = [row.get("slug") for row in index.get("zones") or []]
        self.assertEqual(len(slugs), 56)
        self.assertEqual(len(set(slugs)), 56)
        self.assertIn("nektropos-castle", slugs)
        self.assertIn("lake-nerius", slugs)
        self.assertIn("befallen", slugs)
        self.assertEqual(index.get("zone_file_count"), 56)
        self.assertEqual(index.get("generated"), "2026-09-06")
        self.assertIn("update_2026-10_nektropos", str(index.get("batches")))
        self.assertEqual(len(list((ZONE / "zones").glob("*.json"))), 56)
        update = ROOT / "packaging" / "zone-updates" / "2026-10-nektropos" / "zones"
        for name in ("nektropos-castle.json", "lake-nerius.json"):
            self.assertEqual((ZONE / "zones" / name).read_bytes(), (update / name).read_bytes())
        with (ZONE / "mobs.csv").open(encoding="utf-8", newline="") as handle:
            mobs = list(csv.DictReader(handle))
        self.assertEqual(len(mobs), 448)
        self.assertEqual(sum(1 for row in mobs if row["zone"] == "Nektropos Castle"), 24)
        self.assertEqual(sum(1 for row in mobs if row["zone"] == "Lake Nerius"), 4)
        crysta = next(row for row in mobs if row["mob"] == "Crysta Everling")
        self.assertEqual(crysta["level"], "60")
        self.assertEqual(crysta["zone"], "Nektropos Castle")
        self.assertIn("CONFLICT:", crysta["spawn_notes"])
        sources = (ZONE / "SOURCES.md").read_text(encoding="utf-8")
        self.assertTrue(sources.startswith("# Sources used (Batch 1 + Batch 2 + Batch 3)"))
        self.assertIn("# Sources — Nektropos update", sources)

    def test_zone_source_note_survives_a_second_merge(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "base"
            update = root / "update"
            dest = root / "out"
            (external / "zones").mkdir(parents=True)
            (update / "zones").mkdir(parents=True)
            (external / "zones" / "befallen.json").write_text("{}\n", encoding="utf-8")
            (update / "zones" / "lake-nerius.json").write_text("{}\n", encoding="utf-8")
            (external / "zones_index.json").write_text(json.dumps({
                "generated": "2026-09-06",
                "batches": "1+2+3+4",
                "zones": [{"slug": "befallen", "zone": "Befallen"}],
            }), encoding="utf-8")
            (update / "zones_index.json").write_text(json.dumps({
                "generated": "2026-10-25",
                "batches": "update_2026-10_nektropos",
                "zones": [{"slug": "lake-nerius", "zone": "Lake Nerius"}],
            }), encoding="utf-8")
            (external / "mobs.csv").write_text("zone,mob,level\nBefallen,a skeleton,5\n", encoding="utf-8")
            (update / "mobs.csv").write_text("zone,mob,level\nLake Nerius,a fish,10\n", encoding="utf-8")
            (external / "SOURCES.md").write_text("# Sources used (Batch 1)\n\n- https://example.test/base\n", encoding="utf-8")
            (update / "SOURCES.md").write_text("# Sources — Nektropos update\n\n- https://example.test/nek\n", encoding="utf-8")
            install_packaged_zones(dest, external, update)
            install_packaged_zones(dest, None, update)
            note = (dest / "SOURCES.md").read_text(encoding="utf-8")
            self.assertIn("# Sources used (Batch 1)", note)
            self.assertIn("# Sources — Nektropos update", note)
            index = json.loads((dest / "zones_index.json").read_text(encoding="utf-8"))
            self.assertEqual([row["slug"] for row in index["zones"]], ["befallen", "lake-nerius"])
            self.assertEqual(index["zone_file_count"], 2)
            self.assertEqual(len(list((dest / "zones").glob("*.json"))), 2)

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
