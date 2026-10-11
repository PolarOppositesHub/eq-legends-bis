"""Alert rules fire once per verified line. Charm break stays off."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.alerts import CHARM_NOTE, match_rule  # noqa: E402
from app.parser.classify import classify_message  # noqa: E402
from app.parser.service import ParserService  # noqa: E402


LOG = "\n".join([
    "[Tue Sep 01 21:00:00 2026] Amygdalan knight's limbs move slower!",
    "[Tue Sep 01 21:00:01 2026] Your Reckless Strength spell has worn off of Zabobtik.",
    "[Tue Sep 01 21:00:02 2026] You have been slain by ice boned skeleton!",
    "[Tue Sep 01 21:00:03 2026] You died.",
    "[Tue Sep 01 21:00:04 2026] A plague rat has been slain by Felra!",
    "[Tue Sep 01 21:00:05 2026] You slash a rat for 10 points of damage.",
    "",
])


class AlertClassifyTests(unittest.TestCase):
    def test_owner_log_shapes_classify(self):
        slow = classify_message("a revultant rat's limbs move slower!")
        self.assertEqual(slow.kind, "slow")
        fade = classify_message("Your Reckless Strength spell has worn off of Amop.")
        self.assertEqual(fade.kind, "spell_fade")
        self.assertEqual(fade.spell, "Reckless Strength")
        self.assertEqual(fade.target, "Amop")
        died = classify_message("You died.")
        self.assertEqual(died.kind, "death")

    def test_charm_break_rule_does_not_match(self):
        event = classify_message("Your Charm spell has worn off.")
        rule = {"id": "builtin-charm", "enabled": False, "gated": True, "kind": "charm_break"}
        self.assertIsNone(match_rule(rule, event, "Your Charm spell has worn off."))
        self.assertIn("unverified", CHARM_NOTE.lower())


class AlertReplayTests(unittest.TestCase):
    def test_rules_fire_once_and_charm_stays_off(self):
        root = Path(tempfile.mkdtemp())
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        self.addCleanup(service.close)
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text(LOG, encoding="utf-8")
        service.save_alert_rule({
            "id": "builtin-raid-slain",
            "name": "Raid target slain",
            "enabled": True,
            "kind": "raid_slain",
            "names": ["A plague rat"],
            "cooldown": 0,
            "sound": "none",
            "builtin": True,
        })
        service.replay(path)
        messages = [row["message"] for row in service.recent_alerts()["alerts"]]
        self.assertIn("Amygdalan knight's limbs move slower!", messages)
        self.assertIn("Your Reckless Strength spell has worn off of Zabobtik.", messages)
        self.assertIn("You have been slain by ice boned skeleton!", messages)
        self.assertIn("You died.", messages)
        self.assertIn("A plague rat has been slain by Felra!", messages)
        self.assertFalse(any("Charm" in message for message in messages))
        first = len(messages)
        service.replay(path)
        again = service.recent_alerts()["alerts"]
        self.assertEqual(len(again), first)

    def test_share_import_adds_and_does_not_delete(self):
        root = Path(tempfile.mkdtemp())
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        self.addCleanup(service.close)
        service.save_alert_rule({
            "id": "custom-1",
            "name": "Named",
            "enabled": True,
            "kind": "regex",
            "pattern": "slain",
            "cooldown": 0,
            "sound": "speech",
        })
        share = service.list_alert_rules()["share"]
        before = len(service.list_alert_rules()["rules"])
        imported = service.import_alert_share(share)
        self.assertEqual(imported["added"], 0)
        self.assertEqual(len(imported["rules"]), before)
        service.save_alert_rule({
            "id": "custom-2",
            "name": "Other",
            "enabled": True,
            "kind": "regex",
            "pattern": "slower",
            "cooldown": 0,
            "sound": "none",
        })
        other = service.list_alert_rules()["share"]
        # Re-import the first paste. custom-2 stays.
        imported = service.import_alert_share(share)
        ids = {row["id"] for row in imported["rules"]}
        self.assertIn("custom-1", ids)
        self.assertIn("custom-2", ids)
        self.assertIn("builtin-slow", ids)


if __name__ == "__main__":
    unittest.main()
