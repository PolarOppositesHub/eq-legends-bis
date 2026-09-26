"""Concurrent first calls to get_service() must share one ParserService.

FastAPI runs sync endpoints on a thread pool. The Parser tab's first requests
arrive together, so a racy singleton builds several services and several
schema rebuilds against one SQLite file.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser import api  # noqa: E402


class GetServiceRaceTests(unittest.TestCase):
    def test_concurrent_get_service_creates_one_instance(self):
        created: list[object] = []
        created_lock = threading.Lock()
        original = api.ParserService
        previous = api._service

        class SlowParserService:
            def __init__(self, db_path=None):
                # Hold the constructor open so every thread is inside get_service
                # before the first assignment. Without the lock this creates one
                # service per thread.
                time.sleep(0.2)
                with created_lock:
                    created.append(self)
                self.db_path = db_path

        api.reset_service(None)
        api.ParserService = SlowParserService
        threads = 12
        barrier = threading.Barrier(threads)
        results: list[object | None] = [None] * threads
        errors: list[BaseException] = []

        def worker(index: int) -> None:
            try:
                barrier.wait(timeout=5)
                results[index] = api.get_service()
            except BaseException as exc:  # noqa: BLE001 - report every worker failure
                errors.append(exc)

        try:
            workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
            for thread in workers:
                thread.start()
            for thread in workers:
                thread.join(timeout=10)
            for thread in workers:
                self.assertFalse(thread.is_alive(), "worker did not finish")
            self.assertEqual(errors, [])
            self.assertEqual(len(created), 1, f"created {len(created)} ParserService instances")
            self.assertIsNotNone(results[0])
            self.assertTrue(all(result is results[0] for result in results))
            self.assertIs(results[0], created[0])
        finally:
            api.ParserService = original
            api.reset_service(previous)
