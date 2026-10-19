"""Companion timers, maps, exaltations, resists, and the feedback zip.

Numbers come from the log, a user entry, or decoded data. A missing one stays
unknown. A duration entered for one loadout is not applied to another.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.companion import (  # noqa: E402
    buff_timers,
    export_profile,
    feedback_zip,
    import_profile,
    loadout_key,
    map_rows,
    merge_profile,
    resist_profile,
    respawn_timers,
    exaltation_plan,
)
from app.parser.service import ParserService  # noqa: E402
from app.races import race_bases  # noqa: E402


WHEN = "2026-10-01T12:00:30"
LOADOUT_A = "Warrior / Shadow Knight / Paladin @ 50"
LOADOUT_B = "Wizard / Enchanter / Magician @ 29"


class BuffTimerTests(unittest.TestCase):
    def test_a_cast_does_not_start_a_timer(self):
        payload = buff_timers(
            [{"kind": "cast", "spell": "Resolution", "source": "You", "ts": "2026-10-01T12:00:00", "offset": 1}],
            loadout=LOADOUT_A,
            now=WHEN,
        )
        self.assertEqual(payload["active"], [])

    def test_slow_duration_stays_on_its_loadout(self):
        events = [{"kind": "slow", "target": "a rat", "ts": "2026-10-01T12:00:00", "offset": 1}]
        warrior = buff_timers(events, loadout=LOADOUT_A, durations={"Slow": 90}, now=WHEN)
        wizard = buff_timers(events, loadout=LOADOUT_B, durations={}, now=WHEN)
        self.assertEqual(warrior["active"][0]["remaining_seconds"], 60)
        self.assertEqual(warrior["active"][0]["duration_source"], "user")
        self.assertEqual(wizard["active"][0]["remaining_text"], "unknown")
        self.assertIsNone(wizard["active"][0]["duration_seconds"])
        self.assertEqual(wizard["active"][0]["loadout"], LOADOUT_B)

    def test_a_fade_with_no_start_is_unknown(self):
        payload = buff_timers(
            [{
                "kind": "spell_fade",
                "spell": "Resolution",
                "target": "You",
                "ts": "2026-10-01T12:01:00",
                "offset": 2,
            }],
            loadout="Cleric @ 42",
            now="2026-10-01T12:02:00",
        )
        self.assertEqual(payload["active"], [])
        self.assertIsNone(payload["recent"][0]["observed_seconds"])
        self.assertEqual(payload["recent"][0]["remaining_text"], "unknown")

    def test_a_user_start_and_a_later_fade_are_observed(self):
        payload = buff_timers(
            [{
                "kind": "spell_fade",
                "spell": "Resolution",
                "target": "You",
                "ts": "2026-10-01T12:01:00",
                "offset": 4,
            }],
            loadout="Cleric @ 42",
            manual=[{
                "loadout": "Cleric @ 42",
                "spell": "Resolution",
                "target": "You",
                "started": "2026-10-01T12:00:00",
                "duration_seconds": 600,
            }],
            now="2026-10-01T12:02:00",
        )
        self.assertEqual(payload["active"], [])
        self.assertEqual(payload["recent"][-1]["observed_seconds"], 60)
        self.assertEqual(payload["recent"][-1]["remaining_text"], "ended")


class RespawnTests(unittest.TestCase):
    def test_two_kills_do_not_become_a_respawn_time(self):
        payload = respawn_timers(
            [
                {"mob": "a rat", "zone": "Befallen", "ts": "2026-10-01T12:00:00", "offset": 1},
                {"mob": "a rat", "zone": "Befallen", "ts": "2026-10-01T12:10:00", "offset": 2},
            ],
            {},
            now="2026-10-01T12:12:00",
        )
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["kills"], 2)
        self.assertEqual(payload["rows"][0]["last_kill"], "2026-10-01T12:10:00")
        self.assertEqual(payload["rows"][0]["remaining_text"], "unknown")
        self.assertIsNone(payload["rows"][0]["respawn_seconds"])

    def test_a_user_respawn_counts_down_from_the_last_kill(self):
        payload = respawn_timers(
            [{"mob": "a ghoul", "zone": "", "ts": "2026-10-01T12:00:00", "offset": 1}],
            {"\na ghoul": {"zone": "", "mob": "a ghoul", "seconds": 120}},
            now="2026-10-01T12:00:40",
        )
        row = payload["rows"][0]
        self.assertEqual(row["zone_text"], "unknown")
        self.assertEqual(row["remaining_seconds"], 80)
        self.assertEqual(row["respawn_source"], "user")


class MapAndExaltationTests(unittest.TestCase):
    def test_a_zone_with_no_file_has_an_unknown_map(self):
        payload = map_rows([{"zone": "Befallen", "ts": "2026-10-01T12:00:00"}], lambda _name: None)
        zone = payload["zones"][0]
        self.assertEqual(zone["map_text"], "unknown")
        self.assertEqual(zone["level_requirement_text"], "unknown")
        self.assertFalse(zone["research"])

    def test_a_research_file_is_copied_and_not_extended(self):
        payload = map_rows(
            [{"zone": "Plane of Sky"}],
            lambda _name: {
                "zone": "Plane of Sky",
                "map_url": "https://example.test/sky.png",
                "overview": {"brief": "Islands.", "level_requirement": ""},
                "mobs": [{"name": "Keeper of Souls", "level": None, "spawn_known": False, "coords": None}],
            },
        )
        zone = payload["zones"][0]
        self.assertEqual(zone["map_text"], "https://example.test/sky.png")
        self.assertEqual(zone["mobs"][0]["level_text"], "unknown")
        self.assertEqual(zone["mobs"][0]["location_text"], "unknown")
        self.assertEqual(zone["level_requirement_text"], "unknown")

    def test_exaltation_stats_stay_unknown_without_a_catalog_row(self):
        payload = exaltation_plan(
            [{
                "name": "Blade of the Ocean (Exaltation)",
                "socket_label": "Slot7 (Focus?)",
                "location_raw": "Primary-Slot7",
                "tier": None,
            }],
            loadout=LOADOUT_B,
            notes={},
            stat_lookup=lambda _name: None,
        )
        row = payload["rows"][0]
        self.assertEqual(row["stats_text"], "unknown")
        self.assertEqual(row["loadout"], LOADOUT_B)
        self.assertIsNone(row["stats"])

    def test_a_normal_item_is_not_an_exaltation(self):
        payload = exaltation_plan(
            [{"name": "Cloak of Flames", "socket_label": None, "location_raw": "Back"}],
            loadout=LOADOUT_A,
            stat_lookup=lambda _name: {"AC": 1},
        )
        self.assertEqual(payload["rows"], [])


class ResistAndShareTests(unittest.TestCase):
    def test_unknown_race_and_unknown_item_are_not_zero(self):
        missing = resist_profile(
            loadout=LOADOUT_B,
            classes=["Wizard"],
            level=29,
            race="Not A Race",
            worn=[{"slot": "BACK", "name": "Cloak of Flames", "upgrade": 0}],
            stat_lookup=lambda name: {"SVF": 10} if name == "Cloak of Flames" else None,
        )
        self.assertFalse(missing["race_known"])
        self.assertEqual(missing["totals_text"], "unknown")
        self.assertIsNone(missing["totals"]["SVF"])
        self.assertEqual(missing["gear"]["SVF"], 10)
        self.assertEqual(missing["cap_text"], "unknown")

        partial = resist_profile(
            loadout=LOADOUT_A,
            classes=["Warrior"],
            level=50,
            race="Human",
            worn=[
                {"slot": "BACK", "name": "Cloak of Flames", "upgrade": 0},
                {"slot": "HEAD", "name": "Missing Helm", "upgrade": 0},
            ],
            stat_lookup=lambda name: {"SVM": 4} if name == "Cloak of Flames" else None,
        )
        self.assertEqual(partial["totals_text"], "partial")
        self.assertIn("Missing Helm", partial["unknown_items"])
        human = race_bases("Human")
        self.assertEqual(partial["race_resists"]["SVM"], human["SVM"])
        self.assertEqual(partial["warrior_svm"], 25)
        self.assertEqual(partial["totals"]["SVM"], human["SVM"] + 4 + 25)

    def test_export_drops_tokens_and_import_keeps_loadouts_apart(self):
        blob = {
            "durations": {LOADOUT_A: {"Slow": 90}},
            "respawns": {},
            "manual_buffs": [],
            "exaltation_notes": {},
            "resist_profiles": {},
        }
        exported = export_profile(blob, {"theme": "classic", "refresh_token": "secret-value", "note": "Bearer abc"}, "Zasariz")
        self.assertNotIn("refresh_token", exported["ui"])
        self.assertNotIn("secret-value", json.dumps(exported))
        self.assertNotIn("abc", exported["ui"].get("note", ""))
        incoming = import_profile({
            "v": 1,
            "kind": "eq-legends-bis-profile",
            "durations": {LOADOUT_B: {"Slow": 30}},
            "access_token": "nope",
        })
        merged = merge_profile(blob, incoming)
        self.assertEqual(merged["durations"][LOADOUT_A]["Slow"], 90)
        self.assertEqual(merged["durations"][LOADOUT_B]["Slow"], 30)
        self.assertNotIn("access_token", merged)

    def test_feedback_zip_skips_secret_files_and_scrubs_bearer_lines(self):
        data = feedback_zip(
            {"refresh_token": "secret-value", "theme": "classic"},
            [
                ("main.log", b"hello\nAuthorization: Bearer super-secret\n"),
                ("tokens.json", b"refresh_token=nope"),
                ("../eq-api.log", b"sidecar\n"),
            ],
            {"version": "1.1.16", "rss_text": "unknown"},
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            self.assertIn("logs/main.log", names)
            self.assertIn("logs/eq-api.log", names)
            self.assertNotIn("logs/tokens.json", names)
            text = archive.read("logs/main.log").decode("utf-8")
            settings = archive.read("settings.json").decode("utf-8")
        self.assertNotIn("super-secret", text)
        self.assertIn("[redacted]", text)
        self.assertNotIn("secret-value", settings)
        self.assertIn("classic", settings)


class ServiceTests(unittest.TestCase):
    def test_replay_feeds_respawn_zone_and_buffs(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        log = root / "eqlog_Zasariz_qeynos.txt"
        log.write_text(
            "\n".join([
                "[Wed Oct 01 12:00:00 2026] You have entered Befallen 3 (Fused).",
                "[Wed Oct 01 12:00:05 2026] You begin casting Resolution.",
                "[Wed Oct 01 12:00:06 2026] a rat's limbs move slower!",
                "[Wed Oct 01 12:00:10 2026] You slash a rat for 20 points of damage.",
                "[Wed Oct 01 12:00:12 2026] You have slain a rat!",
                "[Wed Oct 01 12:00:40 2026] Your Resolution spell has worn off of You.",
            ]) + "\n",
            encoding="utf-8",
        )
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        self.addCleanup(service.close)
        service.replay(log)
        buffs = service.companion_buffs("Zasariz", LOADOUT_A, now=__import__("datetime").datetime(2026, 10, 1, 12, 1, 0))
        names = [row["name"] for row in buffs["active"]]
        self.assertIn("Slow", names)
        self.assertNotIn("Resolution", names)
        self.assertEqual(buffs["active"][0]["remaining_text"], "unknown")
        faded = [row for row in buffs["recent"] if row["name"] == "Resolution"]
        self.assertEqual(faded[0]["remaining_text"], "unknown")
        service.companion_set_duration("Zasariz", LOADOUT_A, "Slow", 90)
        other = service.companion_buffs("Zasariz", LOADOUT_B)
        slow = next(row for row in other["active"] if row["name"] == "Slow")
        self.assertEqual(slow["remaining_text"], "unknown")
        respawns = service.companion_respawns("Zasariz")
        rat = next(row for row in respawns["rows"] if row["mob"] == "a rat")
        self.assertEqual(rat["zone"], "Befallen")
        self.assertEqual(rat["remaining_text"], "unknown")
        maps = service.companion_maps("Zasariz")
        self.assertEqual(maps["zones"][0]["zone"], "Befallen")
        self.assertEqual(maps["zones"][0]["map_text"], "unknown")
        (root / "user" / "logs").mkdir(parents=True)
        (root / "user" / "logs" / "main.log").write_text("Authorization: Bearer super-secret\n", encoding="utf-8")
        (root / "user" / "logs" / "secrets.json").write_text("nope", encoding="utf-8")
        packed = service.companion_feedback()
        with zipfile.ZipFile(io.BytesIO(packed)) as archive:
            self.assertIn("logs/main.log", archive.namelist())
            self.assertNotIn("logs/secrets.json", archive.namelist())
            self.assertNotIn("super-secret", archive.read("logs/main.log").decode("utf-8"))
            perf = json.loads(archive.read("perf.json"))
        self.assertIn("version", perf)

    def test_loadout_key_keeps_the_selected_order(self):
        self.assertEqual(loadout_key(["Wizard", "Cleric"], 50), "Wizard / Cleric @ 50")
        self.assertEqual(loadout_key([], None), "unknown classes @ unknown")


if __name__ == "__main__":
    unittest.main()
