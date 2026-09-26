"""DPS-over-time buckets re-read from a fight's log byte range."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.service import ParserService  # noqa: E402
from app.parser.timeline import build_timeline, choose_bin  # noqa: E402
from test_parser_breakdown import LINES  # noqa: E402


def _sum(buckets: list[dict], key: str) -> int:
    return sum(int(row[key]) for row in buckets)


class TimelineTests(unittest.TestCase):
    def test_bin_width_stays_bounded(self):
        self.assertEqual(choose_bin(21), 1)
        self.assertEqual(choose_bin(720), 1)
        self.assertEqual(choose_bin(721), 2)
        self.assertEqual(choose_bin(901), 5)
        self.assertGreaterEqual(choose_bin(50_000), 30)
        self.assertLessEqual(50_000 / choose_bin(50_000), 720)

    def test_hand_counted_curve_on_the_goblin_fight(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        service = ParserService(user_data=root / "user", db_path=root / "parser.db", idle_seconds=30)
        self.addCleanup(service.close)
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        service.replay(path)
        fight_id = service.list_fights("Zasariz")["fights"][0]["id"]

        curve = service.fight_timeline(fight_id)
        self.assertTrue(curve["available"])
        self.assertEqual(curve["bin_seconds"], 1)
        buckets = {row["t"]: row for row in curve["buckets"]}
        # 22:00:01 is t=0: two slashes, 100 + 40.
        self.assertEqual(buckets[0]["you"], 140)
        # Warder the next second.
        self.assertEqual(buckets[1]["pets"], 50)
        self.assertEqual(buckets[2]["you"], 10)
        self.assertEqual(buckets[3]["you"], 30)
        # Incoming slash at 22:00:09.
        self.assertEqual(buckets[8]["incoming"], 30)
        # Flame Shock 15 + Ignite Blood 8.
        self.assertEqual(buckets[10]["incoming"], 23)
        self.assertEqual(buckets[11]["incoming"], 4)
        # Riposte slash still counts as your damage.
        self.assertEqual(buckets[17]["you"], 5)
        self.assertEqual(buckets[18]["incoming"], 3)
        # You 196, pet 50, incoming 60. Self-damage 6 is not on the curve.
        self.assertEqual(_sum(curve["buckets"], "you"), 196)
        self.assertEqual(_sum(curve["buckets"], "pets"), 50)
        self.assertEqual(_sum(curve["buckets"], "incoming"), 60)
        self.assertEqual(_sum(curve["buckets"], "heals"), 204 + 10 + 138 + 0)

        slash = service.fight_timeline(fight_id, ability="slash")
        self.assertEqual(slash["ability"], "slash")
        self.assertEqual(_sum(slash["buckets"], "you"), 145)
        self.assertEqual(_sum(slash["buckets"], "pets"), 50)
        self.assertEqual(_sum(slash["buckets"], "incoming"), 30)

        valor = service.fight_timeline(fight_id, ability="Valor")
        self.assertEqual(_sum(valor["buckets"], "heals"), 204)
        self.assertEqual(_sum(valor["buckets"], "you"), 0)

    def test_missing_log_is_an_empty_curve(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        self.addCleanup(service.close)
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text(
            "[Tue Aug 04 22:00:01 2026] You slash a goblin for 10 points of damage.\n"
            "[Tue Aug 04 22:00:02 2026] You have slain a goblin!\n",
            encoding="utf-8",
        )
        service.replay(path)
        fight_id = service.list_fights("Zasariz")["fights"][0]["id"]
        path.unlink()
        curve = service.fight_timeline(fight_id)
        self.assertFalse(curve["available"])
        self.assertEqual(curve["buckets"], [])
        self.assertIn("missing", curve["reason"])

    def test_builder_ignores_lines_without_amounts(self):
        curve = build_timeline(
            ["[Tue Aug 04 22:00:01 2026] You have entered Befallen."],
            character="Zasariz",
            sources=[{"source": "Zasariz", "kind": "self"}],
            start_ts="2026-08-04T22:00:01",
        )
        self.assertEqual(curve["buckets"], [])
        self.assertEqual(curve["bin_seconds"], 1)


if __name__ == "__main__":
    unittest.main()
