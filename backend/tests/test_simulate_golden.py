"""Golden snapshots of the build simulator on v1.0.23.

Covers pool totals (HP, mana, endurance, attributes), worn haste as
tooltip base plus upgrade level, per-slot upgrades, and the single
worn-haste rule (only the highest piece counts).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.engine import simulate  # noqa: E402
from app.simulate import simulate_loadout  # noqa: E402
from golden_support import assert_golden  # noqa: E402


CLOAK0 = {"AC": 10, "HP": 50, "MANA": 20, "END": 15, "STR": 5, "STA": 5, "AGI": 9, "DEX": 9, "INT": 8, "WIS": 4, "SVF": 15, "Haste": 36}
SASH0 = {"AC": 4, "HP": 20, "STA": 3, "Haste": 21}
BELT0 = {"AC": 6, "HP": 25, "END": 10, "Haste": 31}


def _plus10(stats0: dict) -> dict:
    """Mirror a decoded +10 row whose haste column still copies +0."""
    out = {}
    for key, value in stats0.items():
        if str(key).lower() == "haste":
            out[key] = value
        elif key in ("DLY",):
            out[key] = value
        else:
            out[key] = value * 2 if isinstance(value, (int, float)) else value
    return out


class SimulateGoldenTests(unittest.TestCase):
    def test_engine_simulate_loadouts(self):
        cases = [
            (
                "sim_wizard_human_cloak_sash_u0",
                {
                    "classes": ["Wizard"],
                    "race": "Human",
                    "equipment": {
                        "BACK": "Cloak of Flames",
                        "WAIST": "Flowing Black Silk Sash",
                    },
                    "upgrade": 0,
                    "character_level": 50,
                },
            ),
            (
                "sim_wizard_human_cloak_sash_u10",
                {
                    "classes": ["Wizard"],
                    "race": "Human",
                    "equipment": {
                        "BACK": "Cloak of Flames",
                        "WAIST": "Flowing Black Silk Sash",
                    },
                    "upgrade": 10,
                    "character_level": 50,
                },
            ),
            (
                "sim_wizard_darkelf_cloak_belt_u5",
                {
                    "classes": ["Wizard"],
                    "race": "Dark Elf",
                    "equipment": {
                        "BACK": "Cloak of Flames",
                        "WAIST": "Runed Bolster Belt",
                    },
                    "upgrade": 5,
                    "character_level": 50,
                },
            ),
            (
                "sim_monk_barbarian_slot_upgrades",
                {
                    "classes": ["Monk"],
                    "race": "Barbarian",
                    "equipment": {
                        "BACK": "Cloak of Flames",
                        "WAIST": "Runed Bolster Belt",
                        "PRIMARY": "Blued Two-Handed Hammer",
                    },
                    "upgrade": 10,
                    "character_level": 50,
                    "slot_upgrades": {"BACK": 0, "WAIST": 10, "PRIMARY": 10},
                },
            ),
        ]
        for name, kwargs in cases:
            with self.subTest(case=name):
                result = simulate(**kwargs)
                equipped = [row for row in result["equipment"] if row.get("name")]
                self.assertTrue(equipped, name)
                applied = [row for row in equipped if row.get("haste_applied")]
                self.assertLessEqual(len(applied), 1, name)
                assert_golden(self, name, result)

    def test_synthetic_loadout_single_haste_rule(self):
        """Direct simulate_loadout path: summed attributes and one haste piece."""
        equipped = {
            "BACK": {"name": "Cloak of Flames", "stats_plus0": CLOAK0, "stats_plus10": _plus10(CLOAK0)},
            "WAIST": {"name": "Flowing Black Silk Sash", "stats_plus0": SASH0, "stats_plus10": _plus10(SASH0)},
            "CHEST": {"name": "Synthetic Chest", "stats_plus0": BELT0, "stats_plus10": _plus10(BELT0)},
        }
        at0 = simulate_loadout(equipped, race="Human", upgrade=0)
        at10 = simulate_loadout(equipped, race="Human", upgrade=10)
        self.assertEqual(at0["haste"]["applied_pct"], 36)
        self.assertIn("Cloak of Flames (+36% @ BACK)", at0["haste_warning"])
        self.assertIn("Multiple worn haste", at0["haste_warning"])
        self.assertEqual(at0["slots"]["BACK"]["stats"]["Haste"], 36)
        self.assertEqual(at10["slots"]["BACK"]["stats"]["Haste"], 46)
        self.assertEqual(at10["slots"]["WAIST"]["stats"]["Haste"], 31)
        self.assertEqual(at10["haste"]["applied_pct"], 46)
        self.assertIn("Cloak of Flames (+46% @ BACK)", at10["haste_warning"])
        # Chest haste 31+10 stays below the cloak. It is equipped and ignored.
        self.assertEqual(at10["slots"]["CHEST"]["stats"]["Haste"], 41)
        assert_golden(self, "sim_synthetic_human_three_haste_u0", at0)
        assert_golden(self, "sim_synthetic_human_three_haste_u10", at10)


if __name__ == "__main__":
    unittest.main()
