"""Tracking dashboards: drop rates, pace, notable loot, and live-only toasts.

Fixtures are the log shapes already classified. Item names that are checked
against BiS or Plane of Sky come from files already in the repo.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.currencies import weekly_reset  # noqa: E402
from app.parser.classify import classify_message  # noqa: E402
from app.parser.dashboards import (  # noqa: E402
    MULTI_CLASS_CAVEAT,
    bis_name_keys,
    drop_rate,
    drop_rates,
    item_key,
    leveling_summary,
    lockout_week,
    notable_reasons,
    pos_item_keys,
    raid_kills,
    spells_new_at_level,
    toast_for_event,
)
from app.parser.service import ParserService  # noqa: E402
from app.spell_buffs import load_spell_buffs  # noqa: E402


class DropRateTests(unittest.TestCase):
    def test_rate_is_loots_divided_by_kills(self):
        self.assertEqual(drop_rate(2, 4), 0.5)
        self.assertIsNone(drop_rate(2, 0))
        rows = drop_rates({"a rat": 2, "a bat": 0}, {"A Rat": 4, "a bat": 1})
        by_mob = {row["mob"].casefold(): row for row in rows}
        self.assertEqual(by_mob["a rat"]["rate"], 0.5)
        self.assertEqual(by_mob["a rat"]["rate_text"], "2 / 4")
        self.assertEqual(by_mob["a bat"]["rate"], 0.0)
        self.assertEqual(by_mob["a bat"]["kills"], 1)

    def test_replay_of_a_short_log_matches_the_hand_count(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        log = root / "eqlog_Zasariz_qeynos.txt"
        log.write_text(
            "\n".join([
                "[Wed Oct 01 12:00:00 2026] You have slain a rat!",
                "[Wed Oct 01 12:00:05 2026] You have slain a rat!",
                "[Wed Oct 01 12:00:06 2026] --You have looted a Rusty Dagger from a rat's corpse.--",
                "[Wed Oct 01 12:00:10 2026] You gain experience!",
                "[Wed Oct 01 12:00:11 2026] You gain experience! (10.000%)",
                "[Wed Oct 01 12:00:20 2026] Key Master regards you indifferently -- looks like he would wipe the floor with you! (Lvl: 55)",
                "[Wed Oct 01 12:01:00 2026] You have gained a level! Welcome to level 12!",
            ]) + "\n",
            encoding="utf-8",
        )
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        self.addCleanup(service.close)
        published = []
        service.hub.publish = lambda event: published.append(event)
        service.replay(log)
        loot = service.dashboard_loot("Zasariz")
        rat = next(row for row in loot["drop_rates"] if row["mob"].casefold() == "a rat")
        self.assertEqual(rat["loots"], 1)
        self.assertEqual(rat["kills"], 2)
        self.assertEqual(rat["rate"], 0.5)
        xp = service.db.list_xp_events("Zasariz")
        percents = [row["pct"] for row in xp]
        self.assertIn(None, percents)
        self.assertNotIn(0, percents)
        considered = service.dashboard_considered("Zasariz")["considered"]
        self.assertEqual(considered[0]["mob"], "Key Master")
        self.assertEqual(considered[0]["level"], 55)
        self.assertEqual(considered[0]["level_source"], "consider line")
        self.assertFalse(any(event.get("type") == "toast" for event in published))
        service.replay(log)
        again = service.dashboard_loot("Zasariz")
        rat_again = next(row for row in again["drop_rates"] if row["mob"].casefold() == "a rat")
        self.assertEqual(rat_again["loots"], 1)
        self.assertEqual(rat_again["kills"], 2)


class NotableTests(unittest.TestCase):
    def test_rules_use_catalog_names_and_a_chosen_mote_grade(self):
        bis = bis_name_keys()
        self.assertIn(item_key("A Shimmering Orb"), bis)
        pos = pos_item_keys()
        self.assertIn(item_key("Light Woolen Mask"), pos)
        reasons = notable_reasons(
            "A Shimmering Orb",
            bis_keys=bis,
            wish_keys={item_key("Jade Mace")},
            pos_keys=pos,
            mote_min_grade=8,
        )
        self.assertEqual(reasons, ["bis"])
        self.assertEqual(
            notable_reasons(
                "Jade Mace",
                bis_keys=bis,
                wish_keys={item_key("Jade Mace")},
                pos_keys=pos,
                mote_min_grade=8,
            ),
            ["wish"],
        )
        self.assertEqual(
            notable_reasons(
                "Light Woolen Mask",
                bis_keys=set(),
                wish_keys=set(),
                pos_keys=pos,
                mote_min_grade=8,
            ),
            ["pos"],
        )
        self.assertIn(
            "mote",
            notable_reasons(
                "Mote of Grand Potential",
                bis_keys=set(),
                wish_keys=set(),
                pos_keys=set(),
                mote_min_grade=8,
                is_mote=True,
            ),
        )
        self.assertEqual(
            notable_reasons(
                "Mote of Minor Potential",
                bis_keys=set(),
                wish_keys=set(),
                pos_keys=set(),
                mote_min_grade=8,
                is_mote=True,
            ),
            [],
        )
        self.assertEqual(
            notable_reasons(
                "Not A Real Item Zzzzz",
                bis_keys=bis,
                wish_keys=set(),
                pos_keys=pos,
                mote_min_grade=8,
            ),
            [],
        )

    def test_toasts_do_not_fire_unless_the_line_is_live(self):
        event = classify_message("You have gained a level! Welcome to level 24!")
        self.assertIsNone(toast_for_event(
            event, live=False, bis_keys=set(), wish_keys=set(), pos_keys=set(), mote_min_grade=None,
        ))
        live = toast_for_event(
            event, live=True, bis_keys=set(), wish_keys=set(), pos_keys=set(), mote_min_grade=None,
        )
        self.assertEqual(live["kind"], "level")
        self.assertEqual(live["level"], 24)
        ability = classify_message("You have gained an ability point!  You now have 4 ability points.")
        self.assertIsNone(toast_for_event(
            ability, live=True, bis_keys=set(), wish_keys=set(), pos_keys=set(), mote_min_grade=None,
        ))
        plain = classify_message("--You have looted a Rusty Dagger from a rat's corpse.--")
        self.assertIsNone(toast_for_event(
            plain, live=True, bis_keys=bis_name_keys(), wish_keys=set(), pos_keys=pos_item_keys(), mote_min_grade=8,
        ))

    def test_a_live_level_up_publishes_and_a_replay_does_not(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        self.addCleanup(service.close)
        published = []
        service.hub.publish = lambda event: published.append(event)
        service._replaying = True
        service._maybe_toast(classify_message("You have gained a level! Welcome to level 24!"), "Zasariz")
        self.assertEqual(published, [])
        service._replaying = False
        service._maybe_toast(classify_message("You have gained a level! Welcome to level 24!"), "Zasariz")
        self.assertEqual(published[-1]["type"], "toast")
        self.assertTrue(published[-1]["live"])
        self.assertEqual(published[-1]["toast"]["level"], 24)


class LevelingTests(unittest.TestCase):
    def test_pace_matches_a_hand_calculation(self):
        t0 = datetime(2026, 10, 1, 12, 0, 0)
        t1 = datetime(2026, 10, 1, 12, 30, 0)
        t2 = datetime(2026, 10, 1, 13, 0, 0)
        levels = [
            {"ts": datetime(2026, 10, 1, 11, 0, 0), "level": 20, "evidence": "level_line", "offset": 1},
            {"ts": t0, "ability_points": 1, "ability_total": 10, "evidence": "ability", "offset": 2},
            {"ts": t2, "ability_points": 1, "ability_total": 11, "evidence": "ability", "offset": 3},
        ]
        known = leveling_summary(
            [
                {"ts": t0, "pct": 10},
                {"ts": t1, "pct": 10},
                {"ts": t2, "pct": 10},
            ],
            levels,
            classes="WIZ/ENC/MAG",
            level=20,
            spells=[{
                "name": "Unsourced Glow",
                "classes": ["Wizard"],
                "level": 20,
            }],
            zone="Not A Real Zone",
            zone_level=None,
        )
        # 30% across one hour is 0.30 levels of progress per hour.
        # 70% of the bar remains, so time to level is 0.70 / 0.30 hours.
        self.assertAlmostEqual(known["levels_per_hour"], 0.30)
        self.assertEqual(known["progress_pct"], 30)
        self.assertTrue(known["bar_known"])
        self.assertAlmostEqual(known["hours_to_level"], 0.70 / 0.30)
        self.assertAlmostEqual(known["aa_per_hour"], 2.0)
        self.assertEqual(known["aa_total"], 11)
        self.assertEqual(known["new_at_level"], [])
        self.assertEqual(known["zone_band"]["status"], "unknown")
        self.assertIn("50 then 10", known["caveat"])
        partial = leveling_summary(
            [
                {"ts": t0, "pct": 10},
                {"ts": t1, "pct": None},
                {"ts": t2, "pct": 10},
            ],
            levels,
        )
        self.assertFalse(partial["bar_known"])
        self.assertIsNone(partial["progress_pct"])
        self.assertIsNone(partial["hours_to_level"])
        self.assertEqual(partial["xp_lines_without_percent"], 1)
        self.assertAlmostEqual(partial["levels_per_hour"], 0.20)

    def test_a_level_drop_is_a_second_loadout(self):
        summary = leveling_summary(
            [],
            [
                {"ts": "2026-10-01T12:00:00", "level": 50, "classes": "WIZ/ENC/MAG", "evidence": "who", "offset": 1},
                {"ts": "2026-10-01T13:00:00", "level": 10, "classes": "CLR/DRU/SHM", "evidence": "who", "offset": 2},
            ],
        )
        self.assertEqual(len(summary["history"]), 2)
        self.assertEqual(summary["history"][0]["end_level"], 50)
        self.assertEqual(summary["history"][1]["start_level"], 10)
        self.assertEqual(summary["caveat"], MULTI_CLASS_CAVEAT)

    def test_new_at_level_uses_sourced_spell_levels_only(self):
        buffs = load_spell_buffs()["buffs"]
        cleric = spells_new_at_level(buffs, ["Cleric"], 42)
        names = [row["name"] for row in cleric]
        self.assertIn("Resolution", names)
        paladin = spells_new_at_level(buffs, ["Paladin"], 42)
        self.assertNotIn("Resolution", [row["name"] for row in paladin])
        self.assertEqual(spells_new_at_level([
            {"name": "No Source", "classes": ["Cleric"], "level": 42},
        ], ["Cleric"], 42), [])


class RaidLockoutTests(unittest.TestCase):
    def test_lockout_week_reuses_the_currencies_reset(self):
        now = datetime(2026, 10, 14, 18, 0, tzinfo=ZoneInfo("America/Chicago"))
        got = lockout_week(now)
        base = weekly_reset(now)
        self.assertEqual(got["source"], "currencies.weekly_reset")
        self.assertEqual(got["next_reset"], base["next_reset"].isoformat())
        self.assertEqual(got["last_reset"], base["last_reset"].isoformat())
        self.assertEqual(got["countdown_label"], base["countdown_label"])
        self.assertEqual(got["ct_clock"], base["ct_clock"])

    def test_raid_kill_keeps_the_instance_tier_from_the_fight(self):
        now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
        payload = raid_kills(
            [{"ts": "2026-10-16T12:05:00", "mob": "Innoruuk"}],
            [{
                "start_ts": "2026-10-16T12:00:00",
                "end_ts": "2026-10-16T12:10:00",
                "zone": "The Plane of Hate",
                "instance": {"tier": "Fused", "scope": "Group", "number": 2},
                "targets": ["Innoruuk"],
                "open": False,
            }],
            {"innoruuk": {"name": "Innoruuk", "kinds": ["raid"]}},
            now,
        )
        self.assertEqual(payload["kills"][0]["difficulty"], "Fused")
        self.assertEqual(payload["kills"][0]["zone"], "The Plane of Hate")
        missed = raid_kills(
            [{"ts": "2026-10-16T12:05:00", "mob": "a rat"}],
            [],
            {},
            now,
        )
        self.assertEqual(missed["kills"], [])


class ConsiderClassifyTests(unittest.TestCase):
    def test_spec_consider_line(self):
        event = classify_message(
            "Key Master regards you indifferently -- looks like he would wipe the floor with you! (Lvl: 55)"
        )
        self.assertEqual(event.kind, "consider")
        self.assertEqual(event.target, "Key Master")
        self.assertEqual(event.extra["mob_level"], 55)
        self.assertIn("wipe the floor", event.extra["con"])
        melee = classify_message("You slash a rat for 10 points of damage.")
        self.assertEqual(melee.kind, "melee")
