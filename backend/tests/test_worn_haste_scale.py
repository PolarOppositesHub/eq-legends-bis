"""Worn haste follows eqlegendstools: tooltip base + integer upgrade, not the AC curve."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine import apply_worn_haste, scale_slider_stats, scale_worn_haste  # noqa: E402
from app.simulate import scale_stats, simulate_loadout  # noqa: E402


CLOAK0 = {"AC": 10, "HP": 50, "AGI": 9, "DEX": 9, "SVF": 15, "Haste": 36}


class WornHasteScaleTests(unittest.TestCase):
    def test_tools_rule_not_ac_curve(self):
        # scale_item_stat(36, 10) is 72. The tools page adds the level: 46.
        self.assertEqual(scale_worn_haste(36, 0), 36)
        self.assertEqual(scale_worn_haste(36, 10), 46)
        self.assertEqual(scale_worn_haste(36, 5), 41)

    def test_slider_scales_haste_and_keeps_ac_formula(self):
        plus0 = scale_slider_stats(CLOAK0, 0)
        plus10 = scale_slider_stats(CLOAK0, 10)
        self.assertEqual(plus0["Haste"], 36)
        self.assertEqual(plus10["Haste"], 46)
        self.assertEqual(plus0["AC"], 10)
        self.assertEqual(plus10["AC"], 20)
        self.assertEqual(plus10["HP"], 100)

    def test_explicit_plus10_haste_is_kept_when_it_differs(self):
        stats = {"Haste": 36, "AC": 20}
        apply_worn_haste(stats, {"Haste": 36}, 10, {"Haste": 40})
        self.assertEqual(stats["Haste"], 40)

    def test_copied_plus10_haste_still_adds_the_level(self):
        stats = {"Haste": 36, "AC": 20}
        apply_worn_haste(stats, {"Haste": 36}, 10, {"Haste": 36})
        self.assertEqual(stats["Haste"], 46.0)

    def test_sim_scale_and_loadout(self):
        scaled = scale_stats(CLOAK0, 10)
        self.assertEqual(scaled["Haste"], 46)
        self.assertEqual(scaled["AC"], 20)
        out = simulate_loadout(
            {"BACK": {"name": "Cloak of Flames", "stats_plus0": CLOAK0, "stats_plus10": {**CLOAK0, "AC": 20, "HP": 100, "AGI": 19, "DEX": 19, "SVF": 30}}},
            upgrade=10,
        )
        self.assertEqual(out["haste"]["applied_pct"], 46)
        self.assertEqual(out["slots"]["BACK"]["stats"]["AC"], 20)
        self.assertEqual(out["slots"]["BACK"]["stats"]["Haste"], 46)


if __name__ == "__main__":
    unittest.main()
