"""Saved fight history: restart, retention, per-character clear, and drill-down.

History lives in the existing parser database. Raw log lines are not stored.
Drill-down re-reads the fight's byte range from the log file.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.service import ParserService, read_log_range  # noqa: E402
from app.parser.store import RETENTION_DAYS_KEY, SCHEMA_VERSION  # noqa: E402

NOW = datetime(2026, 9, 26, 12, 0, 0)

ZASARIZ_LOG = "\n".join([
    "[Thu Jan 01 12:00:00 2026] You slash a goblin for 10 points of damage.",
    "[Thu Jan 01 12:00:01 2026] You have slain a goblin!",
    "[Sun Sep 20 12:00:00 2026] You slash a wolf for 20 points of damage.",
    "[Sun Sep 20 12:00:01 2026] You have slain a wolf!",
]) + "\n"

AMOP_LOG = "\n".join([
    "[Thu Jan 01 13:00:00 2026] You crush a skeleton for 7 points of damage.",
    "[Thu Jan 01 13:00:01 2026] You have slain a skeleton!",
]) + "\n"

OPEN_LOG = "[Thu Jan 01 12:00:00 2026] You slash a goblin for 10 points of damage.\n"


class FightHistoryTests(unittest.TestCase):
    def _root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _service(self, root: Path, clock=None) -> ParserService:
        service = ParserService(
            user_data=root / "user",
            db_path=root / "parser.db",
            clock=clock or (lambda: NOW),
        )
        self.addCleanup(service.close)
        return service

    def _write(self, root: Path) -> tuple[Path, Path]:
        zas = root / "eqlog_Zasariz_qeynos.txt"
        amop = root / "eqlog_Amop_qeynos.txt"
        zas.write_text(ZASARIZ_LOG, encoding="utf-8")
        amop.write_text(AMOP_LOG, encoding="utf-8")
        return zas, amop

    def _targets(self, fights: list[dict]) -> set[str]:
        names = set()
        for fight in fights:
            names.update(fight["targets"])
        return names

    def test_history_survives_restart(self):
        root = self._root()
        zas, _amop = self._write(root)
        first = self._service(root)
        replayed = first.replay(zas)
        self.assertGreater(replayed["events_inserted"], 0)
        before = first.list_fights("Zasariz")["fights"]
        self.assertEqual(len(before), 2)
        first.close()

        second = self._service(root)
        after = second.list_fights("Zasariz")["fights"]
        self.assertEqual([row["id"] for row in after], [row["id"] for row in before])
        self.assertEqual(self._targets(after), self._targets(before))
        self.assertEqual(
            sorted(row["your_damage"] for row in after),
            sorted(row["your_damage"] for row in before),
        )
        detail = second.fight_detail(after[0]["id"], merge_pets=False)
        self.assertIsNotNone(detail)
        self.assertGreater(detail["totals"]["damage"], 0)

    def test_default_retention_keeps_every_fight(self):
        root = self._root()
        zas, _amop = self._write(root)
        service = self._service(root, clock=lambda: datetime(2030, 1, 1))
        service.replay(zas)
        self.assertEqual(service.db.retention_days(), 0)
        self.assertEqual(service.config()["fight_retention_days"], 0)
        self.assertIsNone(service.db.get_setting(RETENTION_DAYS_KEY))
        self.assertEqual(service.list_fights("Zasariz")["count"], 2)

    def test_retention_prunes_old_fights_and_keeps_recent_and_open(self):
        root = self._root()
        zas, amop = self._write(root)
        open_log = root / "eqlog_Open_qeynos.txt"
        open_log.write_text(OPEN_LOG, encoding="utf-8")
        service = self._service(root)
        service.replay(zas)
        service.replay(amop)
        service.replay(open_log, finalize=False)
        self.assertEqual(service.list_fights("Zasariz")["count"], 2)
        self.assertEqual(service.list_fights("Amop")["count"], 1)
        open_rows = service.list_fights("Open")["fights"]
        self.assertEqual(len(open_rows), 1)
        self.assertTrue(open_rows[0]["open"])

        january = next(
            row for row in service.list_fights("Zasariz")["fights"]
            if any("goblin" in name for name in row["targets"])
        )
        with service.db.lock:
            fight = service.db.get_fight_row(january["id"])
            old_offset = fight["start_offset"]
            file_id = fight["file_id"]

        service.set_retention_days(30)
        self.assertEqual(service.config()["fight_retention_days"], 30)
        self.assertEqual(service.db.get_setting(RETENTION_DAYS_KEY), "30")

        kept = service.list_fights("Zasariz")["fights"]
        self.assertEqual(self._targets(kept), {"a wolf"})
        self.assertEqual(kept[0]["your_damage"], 20)
        # Amop's only fight is from January, so the window removes it.
        self.assertEqual(service.list_fights("Amop")["count"], 0)
        # The still-open January fight is current history, not expired history.
        still_open = service.list_fights("Open")["fights"]
        self.assertEqual(len(still_open), 1)
        self.assertTrue(still_open[0]["open"])

        with service.db.lock:
            gone = service.db.conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE file_id=? AND offset=?",
                (file_id, old_offset),
            ).fetchone()
        self.assertEqual(int(gone["n"]), 0)

    def test_clear_affects_one_character_only(self):
        root = self._root()
        zas, amop = self._write(root)
        service = self._service(root)
        service.replay(zas)
        service.replay(amop)
        service.set_pet_owner("Zasariz", "Zasariz`s warder", "Amop")
        service.db.set_setting("custom_note", "keep-me")
        with service.db.lock:
            zrow = service.db.conn.execute(
                "SELECT id, generation FROM log_files WHERE character=?",
                ("Zasariz",),
            ).fetchone()
            service.db.conn.execute(
                """
                INSERT INTO loot_events(
                    file_id, generation, offset, ts, character, item, qty, is_mote, is_wind_rune
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 0, 0)
                """,
                (zrow["id"], zrow["generation"], 9_000_000, "2026-09-20T12:00:00", "Zasariz", "Kept Loot", 1),
            )
            service.db.commit()

        cleared = service.clear_character_history("Zasariz")
        self.assertTrue(cleared["ok"])
        self.assertGreaterEqual(cleared["fights_removed"], 1)
        self.assertEqual(service.list_fights("Zasariz")["count"], 0)
        self.assertEqual(service.list_fights("Amop")["count"], 1)
        self.assertEqual(self._targets(service.list_fights("Amop")["fights"]), {"a skeleton"})
        self.assertEqual(service.db.get_setting("custom_note"), "keep-me")
        self.assertEqual(service.db.get_setting(RETENTION_DAYS_KEY), None)
        pets = service.list_pets("Zasariz")
        self.assertEqual(pets[0]["pet"], "Zasariz`s warder")
        self.assertEqual(pets[0]["owner"], "Amop")
        self.assertEqual(service.list_economy("Zasariz")["loot"][0]["item"], "Kept Loot")
        with service.db.lock:
            z_events = service.db.conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE file_id=?",
                (zrow["id"],),
            ).fetchone()
            a_events = service.db.conn.execute(
                """
                SELECT COUNT(*) AS n FROM events
                WHERE file_id=(SELECT id FROM log_files WHERE character=?)
                """,
                ("Amop",),
            ).fetchone()
        self.assertEqual(int(z_events["n"]), 0)
        self.assertGreater(int(a_events["n"]), 0)

        service.close()
        restarted = self._service(root)
        self.assertEqual(restarted.list_fights("Zasariz")["count"], 0)
        self.assertEqual(restarted.list_fights("Amop")["count"], 1)
        self.assertEqual(restarted.db.get_setting("custom_note"), "keep-me")

    def test_database_is_separate_from_session_and_settings(self):
        root = self._root()
        user = root / "user"
        user.mkdir()
        settings = user / "settings.json"
        session = user / "workspace-session.json"
        settings.write_text(json.dumps({"eqInstallFolder": str(root)}), encoding="utf-8")
        session.write_text(json.dumps({"v": 1, "tab": "parser", "parserFightId": 4}), encoding="utf-8")
        settings_bytes = settings.read_bytes()
        session_bytes = session.read_bytes()

        zas, amop = self._write(root)
        service = self._service(root)
        service.replay(zas)
        service.replay(amop)
        service.set_retention_days(30)
        service.clear_character_history("Zasariz")

        self.assertEqual(service.db.path.name, "parser.db")
        self.assertNotEqual(service.db.path.resolve(), settings.resolve())
        self.assertNotEqual(service.db.path.resolve(), session.resolve())
        self.assertTrue(service.db.path.is_file())
        self.assertEqual(settings.read_bytes(), settings_bytes)
        self.assertEqual(session.read_bytes(), session_bytes)
        # January fights fall outside the 30-day window that ends 2026-09-26.
        self.assertEqual(service.list_fights("Amop")["count"], 0)

    def test_drilldown_rereads_log_byte_range(self):
        root = self._root()
        zas, _amop = self._write(root)
        service = self._service(root)
        service.replay(zas)
        fight = next(
            row for row in service.list_fights("Zasariz")["fights"]
            if any("wolf" in name for name in row["targets"])
        )
        detail = service.fight_lines(fight["id"])
        self.assertIsNotNone(detail)
        self.assertTrue(detail["available"])
        self.assertGreaterEqual(detail["end_offset"], detail["start_offset"])
        manual = read_log_range(zas, detail["start_offset"], detail["end_offset"])
        self.assertEqual(detail["lines"], manual)
        self.assertTrue(any("points of damage" in row["text"] for row in detail["lines"]))
        self.assertTrue(any("slain a wolf" in row["text"] for row in detail["lines"]))
        self.assertFalse(any("goblin" in row["text"] for row in detail["lines"]))

        blob = service.db.path.read_bytes()
        wal = Path(str(service.db.path) + "-wal")
        stored = blob + (wal.read_bytes() if wal.is_file() else b"")
        self.assertNotIn(b"points of damage", stored)

        text = zas.read_bytes()
        idx = text.find(b"points", detail["start_offset"])
        self.assertGreaterEqual(idx, detail["start_offset"])
        self.assertLess(idx, detail["end_offset"])
        zas.write_bytes(text[:idx] + b"ZZDRIL" + text[idx + 6:])
        reread = service.fight_lines(fight["id"])
        self.assertTrue(any("ZZDRIL" in row["text"] for row in reread["lines"]))
        stored = service.db.path.read_bytes()
        if wal.is_file():
            stored += wal.read_bytes()
        self.assertNotIn(b"ZZDRIL", stored)
        abilities = service.fight_detail(fight["id"], merge_pets=False)["abilities"]
        self.assertTrue(any(row["ability"] == "slash" and row["damage"] == 20 for row in abilities))

        zas.unlink()
        missing = service.fight_lines(fight["id"])
        self.assertFalse(missing["available"])
        self.assertEqual(missing["lines"], [])
        self.assertIn("missing", missing["reason"])

    def test_rebuild_keeps_retention_and_settings(self):
        root = self._root()
        user = root / "user"
        user.mkdir()
        settings = user / "settings.json"
        session = user / "workspace-session.json"
        settings.write_text(json.dumps({"eqInstallFolder": "C:\\Games\\EverQuest Legends"}), encoding="utf-8")
        session.write_text(json.dumps({"v": 1, "tab": "bis"}), encoding="utf-8")
        settings_bytes = settings.read_bytes()
        session_bytes = session.read_bytes()

        zas, _amop = self._write(root)
        service = self._service(root)
        service.replay(zas)
        self.assertEqual(service.list_fights("Zasariz")["count"], 2)
        service.set_idle(45)
        service.db.set_setting("custom_note", "keep-me")
        service.set_pet_owner("Zasariz", "Zasariz`s warder", "Amop")
        with service.db.lock:
            service.db.conn.execute("DELETE FROM settings WHERE key='schema_version'")
            service.db.conn.execute("DELETE FROM fight_breakdown")
            service.db.commit()
        service.set_retention_days(30)
        self.assertEqual(self._targets(service.list_fights("Zasariz")["fights"]), {"a wolf"})
        service.close()

        upgraded = self._service(root)
        self.assertTrue(upgraded.wait_for_upgrade(30))
        self.assertFalse(upgraded.config()["upgrading"])
        self.assertIsNone(upgraded.config()["upgrade_error"])
        self.assertEqual(upgraded.db.stored_schema_version(), SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 2)
        self.assertEqual(upgraded.db.get_setting(RETENTION_DAYS_KEY), "30")
        self.assertEqual(upgraded.config()["fight_retention_days"], 30)
        self.assertEqual(upgraded.idle, 45.0)
        self.assertEqual(upgraded.db.get_setting("custom_note"), "keep-me")
        self.assertEqual(upgraded.db.get_setting("idle_seconds"), "45.0")
        # The replay during upgrade restores both fights, then retention drops January.
        self.assertEqual(self._targets(upgraded.list_fights("Zasariz")["fights"]), {"a wolf"})
        pets = upgraded.list_pets("Zasariz")
        self.assertEqual(len(pets), 1)
        self.assertTrue(pets[0]["manual"])
        self.assertEqual(pets[0]["owner"], "Amop")
        self.assertEqual(settings.read_bytes(), settings_bytes)
        self.assertEqual(session.read_bytes(), session_bytes)
        wolf = upgraded.fight_detail(upgraded.list_fights("Zasariz")["fights"][0]["id"])
        self.assertTrue(any(row["ability"] == "slash" and row["damage"] == 20 for row in wolf["abilities"]))

    def test_rebuild_with_keep_everything_restores_both_fights(self):
        root = self._root()
        zas, _amop = self._write(root)
        service = self._service(root)
        service.replay(zas)
        service.db.set_setting("custom_note", "keep-me")
        with service.db.lock:
            service.db.conn.execute("DELETE FROM settings WHERE key='schema_version'")
            service.db.conn.execute("DELETE FROM fight_breakdown")
            service.db.commit()
        service.close()

        upgraded = self._service(root)
        self.assertTrue(upgraded.wait_for_upgrade(30))
        self.assertEqual(upgraded.db.retention_days(), 0)
        self.assertEqual(self._targets(upgraded.list_fights("Zasariz")["fights"]), {"a goblin", "a wolf"})
        self.assertEqual(upgraded.db.get_setting("custom_note"), "keep-me")
        self.assertEqual(upgraded.db.stored_schema_version(), SCHEMA_VERSION)

    def test_api_retention_clear_and_lines(self):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.parser.api import reset_service

        root = self._root()
        zas, _amop = self._write(root)
        service = self._service(root)
        service.replay(zas)
        fight = next(
            row for row in service.list_fights("Zasariz")["fights"]
            if any("wolf" in name for name in row["targets"])
        )
        reset_service(service)
        self.addCleanup(reset_service, None)
        client = TestClient(app)

        lines = client.get(f"/api/parser/fights/{fight['id']}/lines")
        self.assertEqual(lines.status_code, 200)
        self.assertTrue(lines.json()["available"])
        self.assertTrue(any("wolf" in row["text"] for row in lines.json()["lines"]))

        saved = client.post("/api/parser/config", json={"fight_retention_days": 30})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["fight_retention_days"], 30)
        listed = client.get("/api/parser/fights", params={"character": "Zasariz"})
        self.assertEqual({name for row in listed.json()["fights"] for name in row["targets"]}, {"a wolf"})

        cleared = client.post("/api/parser/history/clear", json={"character": "Zasariz"})
        self.assertEqual(cleared.status_code, 200)
        self.assertGreaterEqual(cleared.json()["fights_removed"], 1)
        self.assertEqual(client.get("/api/parser/fights", params={"character": "Zasariz"}).json()["count"], 0)
        blank = client.post("/api/parser/history/clear", json={"character": "  "})
        self.assertEqual(blank.status_code, 400)

    def test_packaging_mirror_includes_history_changes(self):
        mirror = ROOT / "desktop" / "resources" / "backend" / "app" / "parser"
        store = (mirror / "store.py").read_text(encoding="utf-8")
        service = (mirror / "service.py").read_text(encoding="utf-8")
        api = (mirror / "api.py").read_text(encoding="utf-8")
        self.assertIn("fight_retention_days", store)
        self.assertIn("def clear_character_fights", store)
        self.assertIn("def read_log_range", service)
        self.assertIn("def fight_lines", service)
        self.assertIn("/history/clear", api)
        self.assertIn("/fights/{fight_id}/lines", api)


if __name__ == "__main__":
    unittest.main()
