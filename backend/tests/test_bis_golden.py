"""Golden snapshots of recommend_bis on v1.0.23.

Six fixed inputs: class trios (including multiclass and a single class),
upgrade levels, and priority / max / AI presets. Any scoring change fails
the diff. Regenerate only with EQ_UPDATE_GOLDENS=1 and a PR note.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.engine import recommend_bis  # noqa: E402
from golden_support import assert_golden  # noqa: E402


CASES = [
    {
        "id": "bis_pal_mnk_wiz_priority_int_u10",
        "classes": ["Paladin", "Monk", "Wizard"],
        "mode": "priority",
        "priority_stat": "INT",
        "upgrade": 10,
        "character_level": 50,
        "prefer_ranged_damage": True,
        "maximize_hp_regen": False,
    },
    {
        "id": "bis_wiz_enc_mag_priority_mana_u0",
        "classes": ["Wizard", "Enchanter", "Magician"],
        "mode": "priority",
        "priority_stat": "Mana",
        "upgrade": 0,
        "character_level": 50,
        "prefer_ranged_damage": True,
        "maximize_hp_regen": False,
    },
    {
        "id": "bis_war_sk_pal_max_u10",
        "classes": ["Warrior", "Shadow Knight", "Paladin"],
        "mode": "max",
        "priority_stat": "HP",
        "upgrade": 10,
        "character_level": 50,
        "prefer_ranged_damage": True,
        "maximize_hp_regen": False,
    },
    {
        "id": "bis_rog_rng_brd_ai_u5_l40",
        "classes": ["Rogue", "Ranger", "Bard"],
        "mode": "ai",
        "priority_stat": "STR",
        "upgrade": 5,
        "character_level": 40,
        "prefer_ranged_damage": False,
        "maximize_hp_regen": False,
    },
    {
        "id": "bis_clr_dru_shm_priority_wis_u10_regen",
        "classes": ["Cleric", "Druid", "Shaman"],
        "mode": "priority",
        "priority_stat": "WIS",
        "upgrade": 10,
        "character_level": 50,
        "prefer_ranged_damage": True,
        "maximize_hp_regen": True,
    },
    {
        "id": "bis_mnk_priority_sta_u7_l30",
        "classes": ["Monk"],
        "mode": "priority",
        "priority_stat": "STA",
        "upgrade": 7,
        "character_level": 30,
        "prefer_ranged_damage": True,
        "maximize_hp_regen": False,
    },
]


class BisGoldenTests(unittest.TestCase):
    def test_recommend_bis_matches_goldens(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                kwargs = {k: v for k, v in case.items() if k != "id"}
                result = recommend_bis(alts=5, **kwargs)
                self.assertTrue(result.get("slots"), case["id"])
                self.assertLessEqual(len(result.get("haste_in_loadout") or []), 1, case["id"])
                assert_golden(self, case["id"], result)


if __name__ == "__main__":
    unittest.main()
