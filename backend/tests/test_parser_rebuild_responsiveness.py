"""A rebuild must not make the rest of the app look dead (1.1.2).

1.1.1 first launch, 2026-09-26: the 1.1.0 -> 1.1.1 rebuild held ``db.lock``
for the whole replay and stopped advancing at about 15%. Every Parser read
(fights, roster, fight detail) waited on that lock, each one holding one of
Chromium's six connections to the sidecar. The SSE stream held another, and
fight events published during the replay kept adding refetches. Config polls
and every Best in Slot icon then queued inside the browser, so the whole app
looked frozen until a restart.

These tests pin the fix: reads answer 503 at once during a replay, a replay
publishes no per-fight events, and a stalled rebuild is flagged with a stack
dump on disk.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.parser import api as parser_api  # noqa: E402
from app.parser.service import ParserService  # noqa: E402
from app.parser.store import SCHEMA_VERSION  # noqa: E402


def _fight_lines(count: int) -> list[str]:
    """``count`` separate fights, ten minutes apart, so each closes on idle."""
    lines = []
    for index in range(count):
        minute = 10 * index
        hour = 20 + minute // 60
        minute %= 60
        for second in range(1, 4):
            lines.append(
                f"[Tue Aug 04 {hour:02d}:{minute:02d}:{second:02d} 2026] "
                f"You slash a goblin for {50 + index} points of damage."
            )
    return lines


class _Recorder:
    """Stands in for an SSE subscriber queue."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def put_nowait(self, event: dict) -> None:
        self.events.append(event)


class RebuildResponsivenessTest(unittest.TestCase):
    def _service(self, root: Path) -> ParserService:
        service = ParserService(user_data=root / "user", db_path=root / "parser.db", idle_seconds=30)
        self.addCleanup(service.close)
        return service

    def _legacy_database(self, fights: int = 6) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text("\n".join(_fight_lines(fights)) + "\n", encoding="utf-8")
        service = ParserService(user_data=root / "user", db_path=root / "parser.db", idle_seconds=30)
        service.replay(path)
        self.assertGreaterEqual(service.list_fights("Zasariz")["count"], fights - 1)
        with service.db.lock:
            service.db.conn.execute("DELETE FROM settings WHERE key='schema_version'")
            service.db.commit()
        service.close()
        return root

    def _gated_rebuild(self, root: Path, *, hold_db_lock: bool):
        """Start a rebuild that stops inside the replay until released."""
        started = threading.Event()
        release = threading.Event()
        original = ParserService._consume

        def gated(svc, log_path, finalize=True):
            if hold_db_lock:
                with svc.db.lock:
                    started.set()
                    release.wait(20)
            else:
                started.set()
                release.wait(20)
            return original(svc, log_path, finalize=finalize)

        patcher = patch.object(ParserService, "_consume", gated)
        patcher.start()
        self.addCleanup(patcher.stop)
        service = self._service(root)
        self.addCleanup(release.set)
        self.assertTrue(started.wait(5), "rebuild never reached the replay")
        return service, release

    def test_parser_reads_answer_503_at_once_while_a_rebuild_holds_the_db(self):
        root = self._legacy_database()
        service, release = self._gated_rebuild(root, hold_db_lock=True)
        parser_api.reset_service(service)
        self.addCleanup(parser_api.reset_service, None)
        client = TestClient(app)

        began = time.perf_counter()
        cfg = client.get("/api/parser/config")
        self.assertLess(time.perf_counter() - began, 0.5)
        self.assertEqual(cfg.status_code, 200)
        self.assertTrue(cfg.json()["upgrading"])
        self.assertTrue(cfg.json()["rebuilding"])

        for url in (
            "/api/parser/fights?character=Zasariz&limit=2000",
            "/api/parser/fights?character=Zasariz&limit=200",
            "/api/parser/roster?character=Zasariz",
            "/api/parser/fights/1?merge_pets=true",
            "/api/parser/fights/1/timeline",
            "/api/parser/loot?character=Zasariz&limit=2000",
            "/api/parser/pets?character=Zasariz",
        ):
            began = time.perf_counter()
            res = client.get(url)
            waited = time.perf_counter() - began
            self.assertEqual(res.status_code, 503, url)
            self.assertTrue(res.json()["rebuilding"], url)
            self.assertEqual(res.headers.get("retry-after"), "2", url)
            # Before 1.1.2 each of these waited for the whole replay.
            self.assertLess(waited, 0.5, url)

        release.set()
        self.assertTrue(service.wait_for_upgrade(30))
        self.assertEqual(service.db.stored_schema_version(), SCHEMA_VERSION)
        after = client.get("/api/parser/fights?character=Zasariz&limit=200")
        self.assertEqual(after.status_code, 200)
        self.assertGreaterEqual(after.json()["count"], 5)

    def test_reads_give_up_on_a_long_lock_hold_even_outside_a_replay(self):
        root = self._legacy_database()
        service = self._service(root)
        self.assertTrue(service.wait_for_upgrade(30))
        parser_api.reset_service(service)
        self.addCleanup(parser_api.reset_service, None)
        held = threading.Event()
        release = threading.Event()

        def hog():
            with service.db.lock:
                held.set()
                release.wait(20)

        worker = threading.Thread(target=hog, daemon=True)
        worker.start()
        self.addCleanup(release.set)
        self.assertTrue(held.wait(5))
        began = time.perf_counter()
        res = TestClient(app).get("/api/parser/fights?character=Zasariz")
        waited = time.perf_counter() - began
        self.assertEqual(res.status_code, 503)
        self.assertLess(waited, 3.0)
        release.set()
        worker.join(5)

    def test_rebuild_publishes_progress_but_no_per_fight_events(self):
        root = self._legacy_database(fights=8)
        service, release = self._gated_rebuild(root, hold_db_lock=False)
        recorder = _Recorder()
        with service.hub._lock:
            service.hub._subs.append(recorder)
        release.set()
        self.assertTrue(service.wait_for_upgrade(30))
        kinds = [event.get("type") for event in recorder.events]
        self.assertIn("upgrade", kinds)
        self.assertIn("progress", kinds)
        self.assertNotIn("fight", kinds, "each fight event made the tab refetch into the rebuild's lock")
        done = [e for e in recorder.events if e.get("type") == "upgrade" and e.get("done")]
        self.assertEqual(len(done), 1)
        self.assertIsNone(done[0]["error"])
        self.assertGreaterEqual(service.list_fights("Zasariz")["count"], 7)

    def test_stalled_rebuild_is_flagged_and_leaves_thread_stacks(self):
        root = self._legacy_database()
        service, release = self._gated_rebuild(root, hold_db_lock=True)
        self.assertFalse(service.config()["upgrade_stalled"])
        recorder = _Recorder()
        with service.hub._lock:
            service.hub._subs.append(recorder)
        watcher = threading.Thread(
            target=service._watch_upgrade,
            kwargs={"poll": 0.05, "stall_seconds": 0.3},
            daemon=True,
        )
        watcher.start()
        deadline = time.monotonic() + 5
        while not service.config()["upgrade_stalled"] and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(service.config()["upgrade_stalled"])
        # The stall flag is set before the stack dump. The event is published after it.
        event_deadline = time.monotonic() + 5
        while not any(e.get("stalled") is True for e in recorder.events) and time.monotonic() < event_deadline:
            time.sleep(0.05)
        self.assertTrue(any(e.get("stalled") is True for e in recorder.events))
        log = root / "user" / "logs" / "parser-stall.log"
        self.assertTrue(log.is_file())
        text = log.read_text(encoding="utf-8")
        self.assertIn("parser rebuild made no progress", text)
        self.assertIn("gated", text, "the dump should show where the rebuild thread is stuck")
        release.set()
        self.assertTrue(service.wait_for_upgrade(30))
        watcher.join(5)
        self.assertFalse(watcher.is_alive())
        self.assertEqual(service.db.stored_schema_version(), SCHEMA_VERSION)

    def test_rebuild_gate_holds_until_the_file_says_release(self):
        root = self._legacy_database()
        gate = root / "rebuild.gate"
        gate.write_text("hold\n", encoding="utf-8")
        with patch.dict(os.environ, {"EQ_PARSER_REBUILD_GATE": str(gate)}):
            service = self._service(root)
            # close() joins the upgrade thread. Release the gate first if the test fails.
            self.addCleanup(gate.write_text, "release\n", encoding="utf-8")
            self.assertTrue(service.config()["upgrading"])
            time.sleep(0.4)
            # Do not read the database here. The gate holds db.lock, and a read would wait out the pause.
            self.assertTrue(service.config()["upgrading"], "gate must keep the rebuild paused")
            self.assertTrue(service.config()["rebuilding"])
            gate.write_text("release\n", encoding="utf-8")
            self.assertTrue(service.wait_for_upgrade(30))
        self.assertEqual(service.db.stored_schema_version(), SCHEMA_VERSION)
        self.assertGreaterEqual(service.list_fights("Zasariz")["count"], 5)


if __name__ == "__main__":
    unittest.main()
