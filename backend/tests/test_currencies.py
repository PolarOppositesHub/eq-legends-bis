"""Currency ledger acceptance tests for SPEC §8.3.

Item XP, names, and log lines are the ones already in the catalog and
classifier. Nothing in this file invents a mote id or a condense log line.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.currencies import (  # noqa: E402
    CurrencyBook,
    all_currency_names,
    condense_preview,
    reset_book,
    weekly_reset,
)
from app.inventory import MOTE_GRADES, VOID_TOUCHED_NAME, WIND_RUNE_NAMES  # noqa: E402
from app.main import app  # noqa: E402
from app.parser.service import ParserBusy, ParserService  # noqa: E402

PT = ZoneInfo("America/Los_Angeles")
CT = ZoneInfo("America/Chicago")
CAZA = "Wind Rune Caza"
GEZA = "Wind Rune Geza"
MINOR = "Mote of Minor Potential"
LESSER = "Mote of Lesser Potential"
POTENTIAL = "Mote of Potential"
GRAND = "Mote of Grand Potential"
ASCENDANT = "Mote of Ascendant Potential"
INFINITE = "Mote of Infinite Potential"


def _line(clock: str, msg: str) -> str:
    return f"[Tue Aug 04 {clock} 2026] {msg}"


class CurrencyLedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.book = CurrencyBook(Path(tmp.name) / "currencies.json")
        self.character = "Zasariz"

    def _anchor(self, currency: str, count: int, ts: str = "2026-08-04T22:00:20") -> None:
        self.book.set_anchor(self.character, currency, count, ts)

    def _view(self, **kwargs):
        return self.book.view(self.character, **kwargs)

    def _row(self, name: str, **kwargs):
        view = self._view(**kwargs)
        pool = view["motes"] + [view["void_touched"]] + view["wind_runes"]
        return next(row for row in pool if row["name"] == name)

    def test_catalog_covers_every_currency(self):
        names = all_currency_names()
        self.assertEqual(len(MOTE_GRADES), 10)
        self.assertEqual(len(WIND_RUNE_NAMES), 15)
        self.assertEqual(len(names), 26)
        self.assertIn(VOID_TOUCHED_NAME, names)
        self.assertEqual(names[3], POTENTIAL)
        view = self._view()
        self.assertEqual(len(view["motes"]), 10)
        self.assertEqual(len(view["wind_runes"]), 15)
        self.assertIsNone(view["wind_runes"][0]["need"])
        self.assertEqual(view["rule"], "Bags (from import) + Currency storage = Total.")

    def test_log_lines_anchor_autosold_merge_and_resync(self):
        self._anchor(CAZA, 0)
        self._anchor(GEZA, 3)
        self._anchor(MINOR, 4)
        self.book.sync(self.character, [
            {"key": "loot:1:1:1", "kind": "loot", "ts": "2026-08-04T22:00:05", "item": CAZA, "qty": 1, "mode": "stored_currency"},
            {"key": "loot:1:1:2", "kind": "loot", "ts": "2026-08-04T22:00:23", "item": CAZA, "qty": 1, "mode": "stored_currency"},
            {"key": "give:1:1:3", "kind": "give", "ts": "2026-08-04T22:00:24", "item": GEZA, "qty": 1, "npc": "a sky guardian"},
            {"key": "loot:1:1:4", "kind": "loot", "ts": "2026-08-04T22:00:25", "item": MINOR, "qty": 1, "mode": "autosold"},
            {"key": "merge:1:1:5", "kind": "merge", "ts": "2026-08-04T22:00:26", "item": "Ghoulbane +2", "result_item": "Ghoulbane +2"},
            {"key": "reject:1", "kind": "mote_reject", "ts": "2026-08-04T22:00:27", "item": MINOR},
        ])
        view = self._view()
        self.assertEqual(self._row(CAZA)["storage"], 1)
        self.assertEqual(self._row(GEZA)["storage"], 2)
        minor = self._row(MINOR)
        self.assertEqual(minor["storage"], 4)
        self.assertTrue(minor["autosold"])
        self.assertEqual(minor["autosold_note"], "auto-sold, not kept")
        self.assertEqual(view["pending_merges"], 1)
        self.assertEqual(view["pending_label"], "Pending: 1 merge since last check")
        self.book.sync(self.character, [
            {"key": "loot:1:1:2", "kind": "loot", "ts": "2026-08-04T22:00:23", "item": CAZA, "qty": 1, "mode": "stored_currency"},
            {"key": "give:1:1:3", "kind": "give", "ts": "2026-08-04T22:00:24", "item": GEZA, "qty": 1, "npc": "a sky guardian"},
            {"key": "merge:1:1:5", "kind": "merge", "ts": "2026-08-04T22:00:26", "result_item": "Ghoulbane +2"},
        ])
        again = self._view()
        self.assertEqual(self._row(CAZA)["storage"], 1)
        self.assertEqual(again["pending_merges"], 1)

    def test_reconcile_changes_bags_only_and_undo_restores_them(self):
        self._anchor(CAZA, 5, "2026-08-04T21:00:00")
        self.book.reconcile(self.character, {CAZA: 2}, "2026-08-04T22:00:00")
        first = self._row(CAZA)
        self.assertEqual(first["bags"], 2)
        self.assertEqual(first["storage"], 5)
        self.assertEqual(first["total"], 7)
        self.book.reconcile(self.character, {CAZA: 0}, "2026-08-04T23:00:00")
        dropped = self._row(CAZA)
        self.assertEqual(dropped["bags"], 0)
        self.assertEqual(dropped["storage"], 5)
        entry = next(
            row for row in self._view()["ledger"][CAZA]
            if row["source"] == "inventory_reconcile" and not row["reverted"]
        )
        self.book.undo(self.character, entry["id"])
        restored = self._row(CAZA)
        self.assertEqual(restored["bags"], 2)
        self.assertEqual(restored["storage"], 5)

    def test_condense_xp_and_offered_steps(self):
        minor = condense_preview(2)
        lesser = condense_preview(3)
        first = condense_preview(1)
        grand = condense_preview(8)
        self.assertEqual(minor["item_xp_loss"], 0)
        self.assertTrue(minor["doubles"])
        self.assertEqual(lesser["item_xp_loss"], 0)
        self.assertTrue(lesser["doubles"])
        self.assertGreater(first["item_xp_loss"], 0)
        self.assertIn("Needs Confirmed", grand["note"])
        self.assertIsNone(condense_preview(9))
        self.assertIsNone(condense_preview(10))
        self._anchor(MINOR, 4, "2026-08-04T21:00:00")
        preview = self.book.condense(self.character, MINOR, "2026-08-04T22:00:00")
        self.assertEqual(preview["to"], LESSER)
        self.assertEqual(self._row(MINOR)["storage"], 2)
        self.assertEqual(self._row(LESSER)["storage"], 1)
        with self.assertRaises(ValueError):
            self.book.condense(self.character, ASCENDANT, "2026-08-04T22:00:00")
        with self.assertRaises(ValueError):
            self.book.condense(self.character, INFINITE, "2026-08-04T22:00:00")

    def test_weekly_reset_is_tuesday_8am_pacific_labeled_in_central(self):
        winter = datetime(2026, 3, 3, 7, 59, tzinfo=PT)
        self.assertEqual(winter.weekday(), 1)
        before = weekly_reset(winter)
        self.assertEqual(before["next_reset"].hour, 8)
        self.assertEqual(before["next_reset"].astimezone(CT).hour, 10)
        self.assertIn("10:00 AM CT", before["countdown_label"])
        at = datetime(2026, 3, 3, 8, 0, tzinfo=PT)
        opened = weekly_reset(at)
        self.assertEqual(opened["last_reset"], at)
        summer_at = datetime(2026, 7, 7, 8, 0, tzinfo=PT)
        self.assertEqual(summer_at.weekday(), 1)
        summer = weekly_reset(summer_at)
        self.assertEqual(summer["last_reset"].hour, 8)
        self.assertEqual(summer["last_reset"].astimezone(CT).hour, 10)
        self.assertEqual(summer["last_reset"].utcoffset(), summer_at.utcoffset())
        self.assertNotEqual(at.utcoffset(), summer_at.utcoffset())

    def test_void_touched_earned_this_week_uses_the_pacific_reset(self):
        now = datetime(2026, 7, 8, 12, 0, tzinfo=PT)
        self._anchor(VOID_TOUCHED_NAME, 1, "2026-07-01T00:00:00")
        self.book.sync(self.character, [
            {"key": "early", "kind": "loot", "ts": "2026-07-07T07:00:00", "item": VOID_TOUCHED_NAME, "qty": 1, "mode": "bag"},
            {"key": "week", "kind": "loot", "ts": "2026-07-07T09:00:00", "item": VOID_TOUCHED_NAME, "qty": 1, "mode": "given"},
            {"key": "sold", "kind": "loot", "ts": "2026-07-07T10:00:00", "item": VOID_TOUCHED_NAME, "qty": 1, "mode": "autosold"},
        ])
        row = self._row(VOID_TOUCHED_NAME, now=now, event_zone=PT)
        self.assertEqual(row["held_label"], "3/3")
        self.assertEqual(row["earned_label"], "1/3")
        self.assertEqual(row["earned_this_week"], 1)
        self.assertIn("CT", row["countdown_label"])

    def test_i_used_clears_pending_and_subtracts_storage(self):
        self._anchor(MINOR, 4, "2026-08-04T21:00:00")
        self.book.sync(self.character, [
            {"key": "merge:1", "kind": "merge", "ts": "2026-08-04T22:00:00", "result_item": "Ghoulbane +1"},
        ])
        self.assertEqual(self._view()["pending_merges"], 1)
        self.book.use(self.character, MINOR, 1, "2026-08-04T22:00:30")
        self.assertEqual(self._row(MINOR)["storage"], 3)
        self.assertEqual(self._view()["pending_merges"], 0)


class CurrencyReplayTests(unittest.TestCase):
    def test_parser_replay_feeds_the_ledger(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        service = ParserService(user_data=root / "user", db_path=root / "parser.db", idle_seconds=30)
        self.addCleanup(service.close)
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text("\n".join([
            _line("22:00:05", "You looted Wind Rune Caza from a sky drake's corpse and stored it in your currency"),
            _line("22:00:23", "You looted Wind Rune Caza from a sky drake's corpse and stored it in your currency"),
            _line("22:00:24", "You offered 1 Wind Rune Geza to a sky guardian."),
            _line("22:00:25", "You looted a Mote of Minor Potential from a goblin's corpse and sold it for 1 platinum"),
            _line("22:00:26", "You have successfully merged two items together to create a new item: Ghoulbane +2"),
            _line("22:00:27", "The item you are trying to add will not work, this mote is not sufficiently powerful to upgrade this item."),
        ]) + "\n", encoding="utf-8")
        service.replay(path)
        book = CurrencyBook(root / "currencies.json")
        book.set_anchor("Zasariz", CAZA, 0, "2026-08-04T22:00:20")
        book.set_anchor("Zasariz", GEZA, 3, "2026-08-04T22:00:20")
        book.set_anchor("Zasariz", MINOR, 4, "2026-08-04T22:00:20")
        events = service.currency_feed("Zasariz")
        book.sync("Zasariz", events)
        view = book.view("Zasariz")
        by_name = {row["name"]: row for row in view["motes"] + view["wind_runes"]}
        self.assertEqual(by_name[CAZA]["storage"], 1)
        self.assertEqual(by_name[GEZA]["storage"], 2)
        self.assertEqual(by_name[MINOR]["storage"], 4)
        self.assertTrue(by_name[MINOR]["autosold"])
        self.assertEqual(view["pending_merges"], 1)
        book.sync("Zasariz", service.currency_feed("Zasariz"))
        again = book.view("Zasariz")
        again_names = {row["name"]: row for row in again["motes"] + again["wind_runes"]}
        self.assertEqual(again_names[CAZA]["storage"], 1)
        self.assertEqual(again["pending_merges"], 1)


class CurrencyApiTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.book = CurrencyBook(Path(tmp.name) / "currencies.json")
        reset_book(self.book)
        self.addCleanup(lambda: reset_book(None))
        self.client = TestClient(app)

    def test_anchor_and_busy_parser_still_return_the_ledger(self):
        created = self.client.post("/api/currencies/anchor", json={
            "character": "Zasariz",
            "currency": CAZA,
            "count": 2,
            "ts": "2026-08-04T22:00:00",
        })
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        rune = next(row for row in body["wind_runes"] if row["name"] == CAZA)
        self.assertEqual(rune["storage"], 2)
        with patch("app.currencies_api.get_service") as service:
            service.return_value.currency_feed.side_effect = ParserBusy()
            busy = self.client.get("/api/currencies", params={"character": "Zasariz"})
        self.assertEqual(busy.status_code, 200, busy.text)
        payload = busy.json()
        self.assertIn("rebuilt", payload["warning"])
        self.assertEqual(payload["character"], "Zasariz")


if __name__ == "__main__":
    unittest.main()
