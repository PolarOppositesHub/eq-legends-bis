"""Current class and level. Formats match the owner's log and SPEC §5.1.

/who: ``[36 PAL/DRU/WIZ] Zasariz (High Elf)  ZONE: North Freeport (freportn)``
Level: ``You have gained a level! Welcome to level 24!``
No class-change line is parsed.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.identity import REPLACED_NOTE, SWAP_NOTE, resolve_current  # noqa: E402
from app.parser.service import ParserService  # noqa: E402


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ResolveCurrentTests(unittest.TestCase):
    def test_level_up_updates_the_current_trio(self):
        resolved = resolve_current([
            {"ts": "2026-09-01T21:12:22", "level": 36, "classes": "PAL/DRU/WIZ", "evidence": "who"},
            {"ts": "2026-09-01T21:13:00", "level": 37, "classes": None, "evidence": "level_line"},
        ])
        current = resolved["current"]
        self.assertEqual(current["classes"], "PAL/DRU/WIZ")
        self.assertEqual(current["level"], 37)
        self.assertEqual(current["source"], "level")
        self.assertEqual(resolved["history"], [])

    def test_level_drop_flags_a_probable_swap(self):
        resolved = resolve_current([
            {"ts": "2026-09-01T21:12:22", "level": 36, "classes": "PAL/DRU/WIZ", "evidence": "who"},
            {"ts": "2026-09-01T21:20:00", "level": 12, "classes": None, "evidence": "level_line"},
        ])
        current = resolved["current"]
        self.assertIsNone(current["classes"])
        self.assertEqual(current["level"], 12)
        self.assertEqual(current["source"], "level")
        self.assertEqual(current["note"], SWAP_NOTE)
        self.assertEqual(resolved["history"][0]["classes"], "PAL/DRU/WIZ")
        self.assertEqual(resolved["history"][0]["level"], 36)

    def test_newer_who_replaces_a_manual_override(self):
        resolved = resolve_current(
            [{"ts": "2026-09-02T10:00:00", "level": 40, "classes": "WAR/SHD/PAL", "evidence": "who"}],
            {"ts": "2026-09-02T09:00:00", "classes": "PAL/DRU/WIZ", "level": 36},
        )
        current = resolved["current"]
        self.assertEqual(current["source"], "who")
        self.assertEqual(current["classes"], "WAR/SHD/PAL")
        self.assertEqual(current["level"], 40)
        self.assertTrue(current["replaced_manual"])
        self.assertEqual(current["note"], REPLACED_NOTE)

    def test_manual_beats_an_older_who_and_a_later_level_line(self):
        resolved = resolve_current(
            [
                {"ts": "2026-09-01T21:12:22", "level": 36, "classes": "PAL/DRU/WIZ", "evidence": "who"},
                {"ts": "2026-09-03T12:00:00", "level": 37, "classes": None, "evidence": "level_line"},
            ],
            {"ts": "2026-09-02T09:00:00", "classes": "WAR/BER/ROG", "level": 20},
        )
        current = resolved["current"]
        self.assertEqual(current["source"], "manual")
        self.assertEqual(current["classes"], "WAR/BER/ROG")
        self.assertEqual(current["level"], 20)


class ParserIdentityServiceTests(unittest.TestCase):
    def _service(self):
        root = Path(tempfile.mkdtemp())
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        self.addCleanup(service.close)
        return service, root

    def test_replay_exposes_current_and_a_newer_who_replaces_override(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Sep 01 21:12:20 2026] You have gained a level! Welcome to level 24!",
            "[Tue Sep 01 21:12:22 2026] [36 PAL/DRU/WIZ] Zasariz (High Elf)  ZONE: North Freeport (freportn)",
            "[Tue Sep 01 21:13:00 2026] You have gained a level! Welcome to level 37!",
        ])
        service.replay(path)
        current = service.roster("Zasariz")["current"]
        self.assertEqual(current["classes"], "PAL/DRU/WIZ")
        self.assertEqual(current["level"], 37)
        self.assertEqual(current["source"], "level")

        service.set_identity("Zasariz", ["WAR", "SHD", "PAL"], 12)
        overridden = service.roster("Zasariz")["current"]
        self.assertEqual(overridden["source"], "manual")
        self.assertEqual(overridden["classes"], "WAR/SHD/PAL")
        self.assertEqual(overridden["level"], 12)

        _write(path, [
            "[Tue Sep 01 21:12:20 2026] You have gained a level! Welcome to level 24!",
            "[Tue Sep 01 21:12:22 2026] [36 PAL/DRU/WIZ] Zasariz (High Elf)  ZONE: North Freeport (freportn)",
            "[Tue Sep 01 21:13:00 2026] You have gained a level! Welcome to level 37!",
            "[Wed Sep 02 10:00:00 2026] [40 WAR/MNK/BER] Zasariz (High Elf)  ZONE: North Freeport (freportn)",
        ])
        service.replay(path)
        # The manual stamp is "now", after the log line, so this /who does not replace it.
        still = service.roster("Zasariz")["current"]
        self.assertEqual(still["source"], "manual")

        # An older override loses to a later own-character /who.
        service.db.set_override("Zasariz", "WAR/SHD/PAL", 12, "2026-09-01T22:00:00")
        service.db.commit()
        replaced = service.roster("Zasariz")["current"]
        self.assertEqual(replaced["source"], "who")
        self.assertEqual(replaced["classes"], "WAR/MNK/BER")
        self.assertEqual(replaced["level"], 40)
        self.assertTrue(replaced["replaced_manual"])
        self.assertEqual(replaced["note"], REPLACED_NOTE)
        history = service.roster("Zasariz")["history"]
        self.assertTrue(any(row["classes"] == "PAL/DRU/WIZ" for row in history))

    def test_below_level_10_the_override_is_two_classes(self):
        service, _root = self._service()
        with self.assertRaises(ValueError):
            service.set_identity("Zasariz", ["WAR", "SHD", "PAL"], 9)
        saved = service.set_identity("Zasariz", ["WAR", "SHD"], 9)
        self.assertEqual(saved["current"]["classes"], "WAR/SHD")
        service.clear_identity("Zasariz")
        self.assertIsNone(service.roster("Zasariz")["current"])


if __name__ == "__main__":
    unittest.main()
