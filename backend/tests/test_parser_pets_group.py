"""Pets, group allowlist, and /who loadouts (1.1.1-B).

A nominating say is a prompt only. Manual pet bindings, dismissals, and the
allowlist survive a schema rebuild. A per-character fight clear and retention
pruning remove fights only; they leave those same rows in place.
"""

from __future__ import annotations

import gzip
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.service import ParserService  # noqa: E402
from app.parser.store import SCHEMA_VERSION  # noqa: E402

SAMPLE = Path(os.environ["EQ_SAMPLE_LOG"]) if os.environ.get("EQ_SAMPLE_LOG") else None


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class PetsGroupTests(unittest.TestCase):
    def _service(self, root: Path | None = None, clock=None) -> tuple[ParserService, Path]:
        if root is None:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            root = Path(tmp.name)
        service = ParserService(
            user_data=root / "user",
            db_path=root / "parser.db",
            idle_seconds=30,
            clock=clock,
        )
        self.addCleanup(service.close)
        return service, root

    def test_candidate_is_prompted_and_never_merged(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Aug 04 22:00:00 2026] Jaber says, 'Following you, Master.'",
            "[Tue Aug 04 22:00:01 2026] You slash a rat for 10 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Jaber slashes a rat for 40 points of damage.",
            "[Tue Aug 04 22:00:03 2026] You have slain a rat!",
        ])
        service.replay(path)
        pets = {row["pet"]: row for row in service.list_pets("Zasariz")}
        self.assertNotIn("Jaber", pets)
        roster = service.roster("Zasariz")
        self.assertEqual([row["pet"] for row in roster["candidates"]], ["Jaber"])
        self.assertEqual(roster["candidates"][0]["evidence"], "nominate")

        detail = service.fight_detail(service.list_fights("Zasariz")["fights"][0]["id"], merge_pets=True)
        by_name = {row["source"]: row for row in detail["sources"]}
        self.assertEqual(by_name["Jaber"]["kind"], "candidate")
        self.assertIsNone(by_name["Jaber"]["owner"])
        self.assertEqual(by_name["Zasariz"].get("pets") or [], [])
        self.assertEqual(detail["totals"]["damage"], 10)
        self.assertNotIn("Jaber", [pet["source"] for pet in by_name["Zasariz"].get("pets") or []])

    def test_dismiss_sticks_and_confirm_is_manual(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Aug 04 22:00:00 2026] Jaber says, 'Following you, Master.'",
            "[Tue Aug 04 22:00:01 2026] Fido says, 'Now holding, Master.  I will not start new attacks until ordered.'",
        ])
        service.replay(path)
        service.dismiss_candidate("Zasariz", "Jaber")
        service.set_pet_owner("Zasariz", "Fido", "Zasariz")
        with path.open("a", encoding="utf-8") as handle:
            handle.write("[Tue Aug 04 22:00:05 2026] Jaber says, 'Following you, Master.'\n")
            handle.write("[Tue Aug 04 22:00:06 2026] Fido says, 'Following you, Master.'\n")
        service.replay(path)
        roster = service.roster("Zasariz")
        self.assertEqual(roster["candidates"], [])
        pets = {row["pet"]: row for row in roster["pets"]}
        self.assertNotIn("Jaber", pets)
        self.assertEqual(pets["Fido"]["owner"], "Zasariz")
        self.assertTrue(pets["Fido"]["manual"])
        self.assertEqual(pets["Fido"]["evidence"], "manual")

    def test_manual_binding_and_allowlist_survive_schema_rebuild(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Aug 04 22:00:00 2026] You have joined the group.",
            "[Tue Aug 04 22:00:00 2026] Amop has joined the group.",
            "[Tue Aug 04 22:00:00 2026] Jenann told you, 'Attacking a rat Master.'",
            "[Tue Aug 04 22:00:00 2026] Fido told you, 'Attacking a rat Master.'",
            "[Tue Aug 04 22:00:00 2026] Jaber says, 'Following you, Master.'",
            "[Tue Aug 04 22:00:01 2026] You slash a rat for 10 points of damage.",
            "[Tue Aug 04 22:00:01 2026] Amop slashes a rat for 2 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Jenann slashes a rat for 4 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Fido slashes a rat for 3 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Jaber slashes a rat for 9 points of damage.",
            "[Tue Aug 04 22:00:03 2026] You have slain a rat!",
        ])
        service.replay(path)
        service.set_pet_owner("Zasariz", "Jenann", "Amop")
        service.set_pet_owner("Zasariz", "Fido", None)
        service.dismiss_candidate("Zasariz", "Jaber")
        service.add_allow("Zasariz", "Cara")
        service.db.set_setting("custom_note", "keep-me")
        with service.db.lock:
            service.db.conn.execute("DELETE FROM settings WHERE key='schema_version'")
            service.db.commit()
        service.close()

        rebuilt, _root = self._service(root)
        self.assertTrue(rebuilt.wait_for_upgrade(30))
        self.assertEqual(rebuilt.db.stored_schema_version(), SCHEMA_VERSION)
        self.assertEqual(rebuilt.db.get_setting("custom_note"), "keep-me")

        pets = {row["pet"]: row for row in rebuilt.list_pets("Zasariz")}
        self.assertEqual(pets["Jenann"]["owner"], "Amop")
        self.assertTrue(pets["Jenann"]["manual"])
        self.assertIsNone(pets["Fido"]["owner"])
        self.assertTrue(pets["Fido"]["manual"])
        self.assertNotIn("Jaber", pets)
        roster = rebuilt.roster("Zasariz")
        self.assertEqual(roster["candidates"], [])
        self.assertEqual(roster["allowlist"], ["Cara"])
        self.assertIn("Amop", [row["name"] for row in roster["group"]])

        detail = rebuilt.fight_detail(rebuilt.list_fights("Zasariz")["fights"][0]["id"], merge_pets=True)
        by_name = {row["source"]: row for row in detail["sources"]}
        self.assertNotIn("Jenann", by_name)
        self.assertEqual(by_name["Amop"]["damage"], 6)
        self.assertEqual(by_name["Amop"]["pets"][0]["source"], "Jenann")
        self.assertNotIn("Jaber", by_name)
        fido = by_name["Fido"]
        self.assertNotEqual(fido["kind"], "pet")
        self.assertIsNone(fido["owner"])
        self.assertEqual(fido.get("pets") or [], [])

    def test_clear_and_retention_keep_manual_pets_and_dismissals(self):
        """Fight history expires. Pet choices do not.

        Retention deletes closed fights older than the window. Clear deletes
        one character's fights and combat events. Neither drops a manual pet
        binding, an unassign, a dismissed prompt, the allowlist, or a /who
        loadout.
        """
        service, root = self._service(clock=lambda: datetime(2026, 9, 26, 12, 0, 0))
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Aug 04 22:00:00 2026] You have joined the group.",
            "[Tue Aug 04 22:00:00 2026] Amop has joined the group.",
            "[Tue Aug 04 22:00:00 2026] [36 PAL/DRU/WIZ] Zasariz (High Elf)  ZONE: North Freeport (freportn)",
            "[Tue Aug 04 22:00:00 2026] Jenann told you, 'Attacking a rat Master.'",
            "[Tue Aug 04 22:00:00 2026] Fido told you, 'Attacking a rat Master.'",
            "[Tue Aug 04 22:00:00 2026] Jaber says, 'Following you, Master.'",
            "[Tue Aug 04 22:00:01 2026] You slash a rat for 10 points of damage.",
            "[Tue Aug 04 22:00:03 2026] You have slain a rat!",
        ])
        service.replay(path)
        service.set_pet_owner("Zasariz", "Jenann", "Amop")
        service.set_pet_owner("Zasariz", "Fido", None)
        service.dismiss_candidate("Zasariz", "Jaber")
        service.add_allow("Zasariz", "Cara")
        self.assertEqual(service.list_fights("Zasariz")["count"], 1)

        service.set_retention_days(30)
        self.assertEqual(service.list_fights("Zasariz")["count"], 0)
        self._assert_pet_choices(service)

        cleared = service.clear_character_history("Zasariz")
        self.assertTrue(cleared["ok"])
        self.assertEqual(service.list_fights("Zasariz")["count"], 0)
        self.assertEqual(service.db.retention_days(), 30)
        self._assert_pet_choices(service)

        service.close()
        restarted, _root = self._service(root, clock=lambda: datetime(2026, 9, 26, 12, 0, 0))
        self.assertEqual(restarted.list_fights("Zasariz")["count"], 0)
        self.assertEqual(restarted.db.retention_days(), 30)
        self._assert_pet_choices(restarted)

    def _assert_pet_choices(self, service: ParserService) -> None:
        pets = {row["pet"]: row for row in service.list_pets("Zasariz")}
        self.assertEqual(pets["Jenann"]["owner"], "Amop")
        self.assertTrue(pets["Jenann"]["manual"])
        self.assertIsNone(pets["Fido"]["owner"])
        self.assertTrue(pets["Fido"]["manual"])
        self.assertNotIn("Jaber", pets)
        roster = service.roster("Zasariz")
        self.assertEqual(roster["candidates"], [])
        self.assertEqual(roster["allowlist"], ["Cara"])
        self.assertEqual(roster["loadouts"][0]["classes"], "PAL/DRU/WIZ")
        self.assertEqual(roster["loadouts"][0]["level"], 36)
        with service.db.lock:
            dismissed = service.db.conn.execute(
                "SELECT status FROM pet_candidates WHERE character=? AND pet=?",
                ("Zasariz", "Jaber"),
            ).fetchone()
        self.assertEqual(dismissed["status"], "dismissed")

    def test_group_leave_clears_the_log_roster_and_keeps_the_allowlist(self):
        service, root = self._service()
        service.add_allow("Zasariz", "Cara")
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Aug 04 22:00:00 2026] You have joined the group.",
            "[Tue Aug 04 22:00:00 2026] Amop has joined the group.",
            "[Tue Aug 04 22:00:01 2026] You have been removed from the group.",
            "[Tue Aug 04 22:00:02 2026] You slash a rat for 10 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Cara slashes a rat for 5 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Amop slashes a rat for 7 points of damage.",
            "[Tue Aug 04 22:00:03 2026] You have slain a rat!",
        ])
        service.replay(path)
        roster = service.roster("Zasariz")
        self.assertEqual(roster["group"], [])
        self.assertEqual(roster["allowlist"], ["Cara"])
        detail = service.fight_detail(service.list_fights("Zasariz")["fights"][0]["id"], merge_pets=False)
        by_name = {row["source"]: row for row in detail["sources"]}
        self.assertEqual(by_name["Cara"]["kind"], "group")
        self.assertEqual(by_name["Cara"]["damage"], 5)
        self.assertNotIn("Amop", by_name)
        self.assertEqual(detail["totals"]["damage"], 15)

    def test_who_levels_are_per_loadout(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Sep 01 21:12:20 2026] [50 PAL/DRU/WIZ] Zasariz (High Elf)  ZONE: North Freeport (freportn)",
            "[Tue Sep 01 21:12:21 2026] [12 WAR/SHD/PAL] Zasariz (High Elf)",
            "[Tue Sep 01 21:12:22 2026] [20 PAL/DRU/WIZ] Amop (High Elf)",
            "[Tue Sep 01 21:12:23 2026] [10 PAL/DRU/WIZ] Zasariz (High Elf)",
        ])
        service.replay(path)
        rows = service.roster("Zasariz")["loadouts"]
        got = {(row["name"], row["classes"]): row["level"] for row in rows}
        self.assertEqual(got[("Zasariz", "PAL/DRU/WIZ")], 10)
        self.assertEqual(got[("Zasariz", "WAR/SHD/PAL")], 12)
        self.assertEqual(got[("Amop", "PAL/DRU/WIZ")], 20)
        self.assertEqual(len(rows), 3)
        levels = [row["level"] for row in service.list_levels("Zasariz")["levels"]]
        self.assertIn(50, levels)
        self.assertIn(12, levels)
        self.assertIn(10, levels)

    def test_raid_scope_is_allowlist_plus_players_on_the_same_npc(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Aug 04 22:00:00 2026] [40 WAR/BER/ROG] Brinn (Barbarian) ZONE: Befallen (befallen)",
            "[Tue Aug 04 22:00:01 2026] You slash a rat for 10 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Brinn slashes a rat for 8 points of damage.",
            "[Tue Aug 04 22:00:03 2026] You have slain a rat!",
        ])
        service.replay(path)
        detail = service.fight_detail(service.list_fights("Zasariz")["fights"][0]["id"], merge_pets=False)
        by_name = {row["source"]: row for row in detail["sources"]}
        self.assertEqual(by_name["Brinn"]["kind"], "other")
        self.assertEqual(by_name["Brinn"]["damage"], 8)
        self.assertEqual(detail["totals"]["damage"], 10)
        self.assertEqual(service.roster("Zasariz")["loadouts"][0]["classes"], "WAR/BER/ROG")

        alone, alone_root = self._service()
        alone_path = alone_root / "eqlog_Zasariz_qeynos.txt"
        _write(alone_path, [
            "[Tue Aug 04 22:00:01 2026] You slash a rat for 10 points of damage.",
            "[Tue Aug 04 22:00:02 2026] Brinn slashes a rat for 8 points of damage.",
            "[Tue Aug 04 22:00:03 2026] You have slain a rat!",
        ])
        alone.replay(alone_path)
        quiet = alone.fight_detail(alone.list_fights("Zasariz")["fights"][0]["id"], merge_pets=False)
        self.assertNotIn("Brinn", {row["source"] for row in quiet["sources"]})

    def test_roster_endpoints(self):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.parser.api import reset_service

        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        _write(path, [
            "[Tue Aug 04 22:00:00 2026] Jaber says, 'Following you, Master.'",
            "[Tue Aug 04 22:00:00 2026] [36 PAL/DRU/WIZ] Zasariz (High Elf)",
            "[Tue Aug 04 22:00:01 2026] You slash a rat for 10 points of damage.",
            "[Tue Aug 04 22:00:02 2026] You have slain a rat!",
        ])
        service.replay(path)
        reset_service(service)
        self.addCleanup(reset_service, None)
        client = TestClient(app)
        roster = client.get("/api/parser/roster", params={"character": "Zasariz"})
        self.assertEqual(roster.status_code, 200)
        self.assertEqual(roster.json()["candidates"][0]["pet"], "Jaber")
        self.assertEqual(roster.json()["loadouts"][0]["classes"], "PAL/DRU/WIZ")
        self.assertEqual(roster.json()["loadouts"][0]["level"], 36)

        added = client.post("/api/parser/group", json={"character": "Zasariz", "member": "Cara", "action": "add"})
        self.assertEqual(added.status_code, 200)
        self.assertEqual(client.get("/api/parser/roster", params={"character": "Zasariz"}).json()["allowlist"], ["Cara"])
        removed = client.post("/api/parser/group", json={"character": "Zasariz", "member": "Cara", "action": "remove"})
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(client.get("/api/parser/roster", params={"character": "Zasariz"}).json()["allowlist"], [])

        dismissed = client.post(
            "/api/parser/candidates",
            json={"character": "Zasariz", "pet": "Jaber", "action": "dismiss"},
        )
        self.assertEqual(dismissed.status_code, 200)
        self.assertEqual(client.get("/api/parser/roster", params={"character": "Zasariz"}).json()["candidates"], [])
        self.assertEqual(client.get("/api/parser/pets", params={"character": "Zasariz"}).json()["pets"], [])


@unittest.skipUnless(SAMPLE is not None and SAMPLE.is_file(), "set EQ_SAMPLE_LOG to replay Josh's log")
class FullLogRosterTests(unittest.TestCase):
    def test_replay_reports_pets_candidates_and_group(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        path = root / "eqlog_Zasariz_qeynos.txt"
        if SAMPLE.suffix == ".gz":
            with gzip.open(SAMPLE, "rb") as src, path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        else:
            shutil.copyfile(SAMPLE, path)
        service = ParserService(user_data=root / "user", db_path=root / "parser.db", idle_seconds=30)
        self.addCleanup(service.close)
        stats = service.replay(path)
        roster = service.roster("Zasariz")
        pets = roster["pets"]
        with service.db.lock:
            joins = [
                row["source"]
                for row in service.db.conn.execute(
                    "SELECT DISTINCT source FROM events WHERE kind='group_join' AND source!='You' ORDER BY source"
                )
            ]
        print(
            "FULL_LOG",
            "lines", stats["lines"],
            "pets", len(pets),
            "pet_names", [row["pet"] for row in pets],
            "candidates", len(roster["candidates"]),
            "candidate_names", [row["pet"] for row in roster["candidates"]],
            "group_now", len(roster["group"]),
            "group_names", [row["name"] for row in roster["group"]],
            "joined", joins,
            "loadouts", len(roster["loadouts"]),
        )
        self.assertGreater(stats["lines"], 1000)
        self.assertGreaterEqual(len(pets), 1)
        self.assertTrue(any(row["pet"] == "Zasariz`s warder" for row in pets))
        self.assertEqual(roster["candidates"], [])
        self.assertIn("Amop", joins)


if __name__ == "__main__":
    unittest.main()
