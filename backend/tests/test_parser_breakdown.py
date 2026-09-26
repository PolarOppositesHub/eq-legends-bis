"""Hand-computed fight breakdowns for parser depth (1.1.1-A).

Every expected number below is counted from the fixture lines, not from the
parser's own output. The heal line ``204 (216)`` is 12 overheal.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.service import ParserService  # noqa: E402
from app.parser.store import SCHEMA_VERSION  # noqa: E402

# One encounter. Comments are the hand count, not parsed text.
LINES = [
    # Resist before the pull. It must not open a fight or land on this one.
    "[Tue Aug 04 21:59:00 2026] a goblin resisted your Pacify!",
    "[Tue Aug 04 22:00:00 2026] You have joined the group.",
    "[Tue Aug 04 22:00:00 2026] Amop has joined the group.",
    # 22:00:01 two slashes: one double-attack round. 100 + 40 crit.
    "[Tue Aug 04 22:00:01 2026] You slash a goblin for 100 points of damage.",
    "[Tue Aug 04 22:00:01 2026] You slash a goblin for 40 points of damage. (Critical)",
    # Pet, same second: one double. 25 + 25.
    "[Tue Aug 04 22:00:02 2026] Zasariz`s warder slashes a goblin for 25 points of damage.",
    "[Tue Aug 04 22:00:02 2026] Zasariz`s warder slashes a goblin for 25 points of damage.",
    # One pierce: a single.
    "[Tue Aug 04 22:00:03 2026] You pierce a goblin for 10 points of damage.",
    # Three kicks: a triple. 10 + 10 + 10.
    "[Tue Aug 04 22:00:04 2026] You kick a goblin for 10 points of damage.",
    "[Tue Aug 04 22:00:04 2026] You kick a goblin for 10 points of damage.",
    "[Tue Aug 04 22:00:04 2026] You kick a goblin for 10 points of damage.",
    # Four punches: a flurry by cluster size. 1 + 1 + 1 + 1.
    "[Tue Aug 04 22:00:05 2026] You punch a goblin for 1 point of damage.",
    "[Tue Aug 04 22:00:05 2026] You punch a goblin for 1 point of damage.",
    "[Tue Aug 04 22:00:05 2026] You punch a goblin for 1 point of damage.",
    "[Tue Aug 04 22:00:05 2026] You punch a goblin for 1 point of damage.",
    # One bash tagged Flurry: a flurry even though the cluster length is 1.
    "[Tue Aug 04 22:00:06 2026] You bash a goblin for 7 points of damage. (Flurry)",
    # Your miss. The goblin parries, so this is your miss, not your avoidance.
    # One swing in this second: a single.
    "[Tue Aug 04 22:00:08 2026] You try to crush a goblin, but a goblin parries!",
    # Goblin hit + miss in the same second: a double. Incoming 30, one dodge.
    "[Tue Aug 04 22:00:09 2026] A goblin slashes YOU for 30 points of damage.",
    "[Tue Aug 04 22:00:09 2026] A goblin tries to slash YOU, but YOU dodge!",
    # Two misses, no hit: a double. Avoidance block + parry.
    "[Tue Aug 04 22:00:10 2026] A goblin tries to maul YOU, but YOU block!",
    "[Tue Aug 04 22:00:10 2026] A goblin tries to maul YOU, but YOU parry!",
    # --- resume split is after the parry line ---
    "[Tue Aug 04 22:00:11 2026] a goblin hit you for 15 points of fire damage by Flame Shock.",
    "[Tue Aug 04 22:00:11 2026] You have taken 8 damage from Ignite Blood by a goblin.",
    "[Tue Aug 04 22:00:12 2026] YOU are burned by a goblin's flames for 4 points of non-melee damage.",
    "[Tue Aug 04 22:00:12 2026] You gain a rune for 50 points of absorption.",
    "[Tue Aug 04 22:00:13 2026] You hurt yourself for 6 points of damage.",
    # 204 of 216 is 12 overheal. The critical tag does not change that.
    "[Tue Aug 04 22:00:14 2026] Amop healed you for 204 (216) hit points by Valor. (Critical)",
    # HoT is separate from the direct heal. 10 of 40 is 30 overheal.
    "[Tue Aug 04 22:00:14 2026] You healed Zasariz over time for 10 (40) hit points by Regeneration.",
    # No parenthetical and no spell: full == actual, overheal 0, "(unknown spell)".
    "[Tue Aug 04 22:00:15 2026] You healed Zasariz for 138 hit points.",
    # 0 of 181 is 181 overheal. "himself" is Amop.
    "[Tue Aug 04 22:00:15 2026] Amop healed himself for 0 (181) hit points by Siphon Life.",
    "[Tue Aug 04 22:00:16 2026] a goblin resisted your Pacify!",
    "[Tue Aug 04 22:00:16 2026] a goblin resisted your Pacify!",
    "[Tue Aug 04 22:00:16 2026] You resist a goblin's Fear!",
    "[Tue Aug 04 22:00:17 2026] Your Djarn's Amethyst Ring (Exaltation) shimmers briefly.",
    "[Tue Aug 04 22:00:18 2026] Your Goblin Skull Earring feels alive with power.",
    # Riposte damage counts. The swing does not join a multi-attack cluster.
    "[Tue Aug 04 22:00:18 2026] You slash a goblin for 5 points of damage. (Riposte)",
    # Three hits in one second: a triple. 1 + 1 + 1.
    "[Tue Aug 04 22:00:19 2026] A goblin hits YOU for 1 point of damage.",
    "[Tue Aug 04 22:00:19 2026] A goblin hits YOU for 1 point of damage.",
    "[Tue Aug 04 22:00:19 2026] A goblin hits YOU for 1 point of damage.",
    "[Tue Aug 04 22:00:20 2026] You have been knocked unconscious!",
    "[Tue Aug 04 22:00:21 2026] You have been slain by a goblin!",
    # After the death snapshot, so it is avoidance and not one of the last 10.
    "[Tue Aug 04 22:00:21 2026] A goblin tries to cast a spell on you, but you are protected.",
    "[Tue Aug 04 22:00:22 2026] You have slain a goblin!",
    "[Tue Aug 04 22:00:23 2026] You looted a Mote of Minor Potential from a goblin's corpse and stored it in your currency",
    "[Tue Aug 04 22:00:24 2026] You have been given: Void-Touched Potential",
    "[Tue Aug 04 22:00:25 2026] You offered 1 Wind Rune Geza to Dason Goldblade.",
    "[Tue Aug 04 22:00:26 2026] You have successfully merged two items together to create a new item: Ghoulbane +2",
]

SPLIT_MARK = "but YOU parry!"


def _ability(detail: dict, source: str, category: str, name: str) -> dict:
    matches = [
        row for row in detail["abilities"]
        if row["source"] == source and row["category"] == category and row["ability"] == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"{source} {category} {name}: {matches}")
    return matches[0]


def _multi(detail: dict, source: str) -> dict:
    matches = [row for row in detail["multi_attack"]["sources"] if row["source"] == source]
    if len(matches) != 1:
        raise AssertionError(f"multi {source}: {detail['multi_attack']}")
    return matches[0]


def _heal(detail: dict, source: str, spell: str) -> dict:
    matches = [
        row for row in detail["healing"]["rows"]
        if row["source"] == source and row["spell"] == spell
    ]
    if len(matches) != 1:
        raise AssertionError(f"heal {source} {spell}: {detail['healing']}")
    return matches[0]


class BreakdownTests(unittest.TestCase):
    def _service(self, root: Path | None = None) -> tuple[ParserService, Path]:
        if root is None:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            root = Path(tmp.name)
        service = ParserService(user_data=root / "user", db_path=root / "parser.db", idle_seconds=30)
        self.addCleanup(service.close)
        return service, root

    def _assert_closed_fight(self, detail: dict) -> None:
        self.assertEqual(detail["targets"], ["a goblin"])
        self.assertEqual(detail["duration_seconds"], 21.0)
        self.assertTrue(detail["player_died"])
        self.assertFalse(detail["open"])

        by_name = {row["source"]: row for row in detail["sources"]}
        you = by_name["Zasariz"]
        # 100+40+5 slash, 10 pierce, 30 kick, 4 punch, 7 bash.
        self.assertEqual(you["damage"], 196)
        self.assertEqual(you["melee"], 196)
        self.assertEqual(you["hits"], 12)
        self.assertEqual(you["misses"], 1)
        self.assertEqual(you["crits"], 1)
        self.assertEqual(you["max_hit"], 100)
        self.assertEqual(you["damage_taken"], 60)
        # Direct 138 plus HoT 10. Full 138+40. Overheal 30.
        self.assertEqual(you["heals"], 148)
        self.assertEqual(you["heals_full"], 178)
        self.assertEqual(you["overheal"], 30)
        pet = by_name["Zasariz`s warder"]
        self.assertEqual(pet["kind"], "pet")
        self.assertEqual(pet["damage"], 50)
        amop = by_name["Amop"]
        self.assertEqual(amop["heals"], 204)
        self.assertEqual(amop["heals_full"], 397)
        self.assertEqual(amop["overheal"], 193)
        goblin = by_name["a goblin"]
        # NPC misses stay off the source row. They still feed avoidance and the estimate.
        self.assertEqual(goblin["damage"], 60)
        self.assertEqual(goblin["hits"], 7)
        self.assertEqual(goblin["misses"], 0)
        self.assertEqual(detail["totals"]["damage"], 246)
        self.assertEqual(detail["totals"]["damage_taken"], 60)

        slash = _ability(detail, "Zasariz", "melee", "slash")
        self.assertEqual(slash["damage"], 145)
        self.assertEqual(slash["hits"], 3)
        self.assertEqual(slash["crits"], 1)
        self.assertEqual(slash["misses"], 0)
        self.assertEqual(slash["max_hit"], 100)
        pierce = _ability(detail, "Zasariz", "melee", "pierce")
        self.assertEqual((pierce["damage"], pierce["hits"], pierce["max_hit"]), (10, 1, 10))
        kick = _ability(detail, "Zasariz", "melee", "kick")
        self.assertEqual((kick["damage"], kick["hits"], kick["max_hit"]), (30, 3, 10))
        punch = _ability(detail, "Zasariz", "melee", "punch")
        self.assertEqual((punch["damage"], punch["hits"], punch["max_hit"]), (4, 4, 1))
        bash = _ability(detail, "Zasariz", "melee", "bash")
        self.assertEqual((bash["damage"], bash["hits"], bash["max_hit"]), (7, 1, 7))
        crush = _ability(detail, "Zasariz", "melee", "crush")
        self.assertEqual((crush["damage"], crush["hits"], crush["misses"]), (0, 0, 1))
        warder = _ability(detail, "Zasariz`s warder", "melee", "slash")
        self.assertEqual((warder["damage"], warder["hits"], warder["max_hit"]), (50, 2, 25))
        self.assertEqual(_ability(detail, "a goblin", "spell", "Flame Shock")["damage"], 15)
        self.assertEqual(_ability(detail, "a goblin", "dot", "Ignite Blood")["damage"], 8)
        self.assertEqual(_ability(detail, "a goblin", "ds", "flames")["damage"], 4)
        goblin_hits = _ability(detail, "a goblin", "melee", "hit")
        self.assertEqual((goblin_hits["damage"], goblin_hits["hits"], goblin_hits["max_hit"]), (3, 3, 1))
        friendly_damage = sum(
            row["damage"] for row in detail["abilities"]
            if row["source"] in {"Zasariz", "Zasariz`s warder", "Amop"}
        )
        self.assertEqual(friendly_damage, 246)

        valor = _heal(detail, "Amop", "Valor")
        self.assertEqual(valor["target"], "Zasariz")
        self.assertFalse(valor["over_time"])
        self.assertEqual(valor["actual"], 204)
        self.assertEqual(valor["full"], 216)
        self.assertEqual(valor["overheal"], 12)
        self.assertEqual(valor["hits"], 1)
        self.assertEqual(valor["crits"], 1)
        hot = _heal(detail, "Zasariz", "Regeneration")
        self.assertTrue(hot["over_time"])
        self.assertEqual((hot["actual"], hot["full"], hot["overheal"]), (10, 40, 30))
        unknown = _heal(detail, "Zasariz", "(unknown spell)")
        self.assertFalse(unknown["over_time"])
        self.assertEqual((unknown["actual"], unknown["full"], unknown["overheal"]), (138, 138, 0))
        siphon = _heal(detail, "Amop", "Siphon Life")
        self.assertEqual(siphon["target"], "Amop")
        self.assertEqual((siphon["actual"], siphon["full"], siphon["overheal"]), (0, 181, 181))
        totals = detail["healing"]["totals"]
        self.assertEqual(totals["actual"], 352)
        self.assertEqual(totals["full"], 575)
        self.assertEqual(totals["overheal"], 223)
        self.assertEqual(totals["direct_actual"], 342)
        self.assertEqual(totals["direct_full"], 535)
        self.assertEqual(totals["direct_overheal"], 193)
        self.assertEqual(totals["hot_actual"], 10)
        self.assertEqual(totals["hot_full"], 40)
        self.assertEqual(totals["hot_overheal"], 30)

        incoming = {(row["source"], row["category"], row["ability"]): row for row in detail["tanking"]["incoming"]}
        self.assertEqual(incoming[("a goblin", "melee", "slash")]["damage"], 30)
        self.assertEqual(incoming[("a goblin", "spell", "Flame Shock")]["damage"], 15)
        self.assertEqual(incoming[("a goblin", "dot", "Ignite Blood")]["damage"], 8)
        self.assertEqual(incoming[("a goblin", "ds", "flames")]["damage"], 4)
        melee_hits = incoming[("a goblin", "melee", "hit")]
        self.assertEqual((melee_hits["damage"], melee_hits["hits"], melee_hits["max_hit"]), (3, 3, 1))
        self.assertEqual(sum(row["damage"] for row in detail["tanking"]["incoming"]), 60)
        avoidance = {(row["target"], row["kind"]): row["count"] for row in detail["tanking"]["avoidance"]}
        self.assertEqual(avoidance[("Zasariz", "dodge")], 1)
        self.assertEqual(avoidance[("Zasariz", "block")], 1)
        self.assertEqual(avoidance[("Zasariz", "parry")], 1)
        self.assertEqual(avoidance[("Zasariz", "protected")], 1)
        self.assertEqual(detail["tanking"]["runes"], [{"source": "Zasariz", "absorption": 50, "count": 1}])
        self.assertEqual(detail["tanking"]["self_damage"], [{"target": "Zasariz", "damage": 6, "hits": 1}])

        self.assertEqual(len(detail["deaths"]), 1)
        death = detail["deaths"][0]
        self.assertEqual(death["who"], "Zasariz")
        self.assertEqual(death["killer"], "a goblin")
        self.assertEqual(death["kind"], "death")
        self.assertEqual(death["ts"], "2026-08-04T22:00:21")
        # 12 incoming events, keep the last 10. The 30 slash and the dodge drop off.
        self.assertEqual(len(death["incoming"]), 10)
        kinds = [(row["kind"], row["ability"], row["amount"], row["avoidance"]) for row in death["incoming"]]
        self.assertEqual(kinds, [
            ("miss", "maul", 0, "block"),
            ("miss", "maul", 0, "parry"),
            ("spell", "Flame Shock", 15, None),
            ("dot", "Ignite Blood", 8, None),
            ("ds", "flames", 4, None),
            ("self_damage", "hurt yourself", 6, None),
            ("melee", "hit", 1, None),
            ("melee", "hit", 1, None),
            ("melee", "hit", 1, None),
            ("knockout", None, None, None),
        ])
        self.assertEqual(death["incoming"][0]["source"], "a goblin")
        self.assertEqual(death["incoming"][5]["source"], "Zasariz")
        self.assertIsNone(death["incoming"][-1]["source"])

        resists = {(row["source"], row["target"], row["spell"]): row["count"] for row in detail["resists"]}
        # The 21:59 Pacify is outside the fight, so the in-fight pair is 2, not 3.
        self.assertEqual(resists[("Zasariz", "a goblin", "Pacify")], 2)
        self.assertEqual(resists[("a goblin", "Zasariz", "Fear")], 1)
        self.assertEqual(len(resists), 2)

        self.assertEqual(detail["procs"]["count"], 2)
        self.assertAlmostEqual(detail["procs"]["per_minute"], 2 * 60 / 21)
        proc_items = {row["item"]: row for row in detail["procs"]["items"]}
        self.assertEqual(proc_items["Djarn's Amethyst Ring (Exaltation)"]["count"], 1)
        self.assertEqual(proc_items["Djarn's Amethyst Ring (Exaltation)"]["source"], "Zasariz")
        self.assertEqual(proc_items["Goblin Skull Earring"]["count"], 1)

        self.assertTrue(detail["multi_attack"]["estimate"])
        you_multi = _multi(detail, "Zasariz")
        # singles: pierce, crush miss. double: two slashes. triple: three kicks.
        # flurries: four punches, and the one-swing Flurry tag. Riposte is not a round.
        self.assertEqual(you_multi["rounds"], 6)
        self.assertEqual(you_multi["singles"], 2)
        self.assertEqual(you_multi["doubles"], 1)
        self.assertEqual(you_multi["triples"], 1)
        self.assertEqual(you_multi["flurries"], 2)
        self.assertAlmostEqual(you_multi["double_rate"], 1 / 6)
        self.assertAlmostEqual(you_multi["triple_rate"], 1 / 6)
        self.assertAlmostEqual(you_multi["flurry_rate"], 2 / 6)
        pet_multi = _multi(detail, "Zasariz`s warder")
        self.assertEqual((pet_multi["rounds"], pet_multi["doubles"], pet_multi["double_rate"]), (1, 1, 1.0))
        goblin_multi = _multi(detail, "a goblin")
        # Hit+dodge, block+parry, three hits. Misses count here even though source.misses stays 0.
        self.assertEqual(goblin_multi["rounds"], 3)
        self.assertEqual(goblin_multi["doubles"], 2)
        self.assertEqual(goblin_multi["triples"], 1)
        self.assertEqual(goblin_multi["singles"], 0)
        self.assertEqual(goblin_multi["flurries"], 0)
        self.assertAlmostEqual(goblin_multi["double_rate"], 2 / 3)
        self.assertAlmostEqual(goblin_multi["triple_rate"], 1 / 3)

    def test_hand_computed_metrics_and_loot_api(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        stats = service.replay(path)
        self.assertEqual(stats["fights"], 1)
        self.assertEqual(stats["loot"], 2)
        self.assertEqual(stats["gives"], 1)
        self.assertEqual(stats["merges"], 1)

        fight_id = service.list_fights("Zasariz")["fights"][0]["id"]
        detail = service.fight_detail(fight_id, merge_pets=False)
        self._assert_closed_fight(detail)

        merged = service.fight_detail(fight_id, merge_pets=True)
        rolled = {row["source"]: row for row in merged["sources"]}
        self.assertNotIn("Zasariz`s warder", rolled)
        self.assertEqual(rolled["Zasariz"]["damage"], 246)
        owner_slash = [
            row for row in rolled["Zasariz"]["abilities"]
            if row["ability"] == "slash" and row["category"] == "melee"
        ]
        self.assertEqual(owner_slash[0]["damage"], 145)
        self.assertEqual(rolled["Zasariz"]["pets"][0]["damage"], 50)
        pet_slash = rolled["Zasariz"]["pets"][0]["abilities"]
        self.assertEqual(pet_slash[0]["ability"], "slash")
        self.assertEqual(pet_slash[0]["damage"], 50)
        # The fight-level ability list stays unmerged so a row can still be expanded.
        self.assertEqual(_ability(merged, "Zasariz`s warder", "melee", "slash")["damage"], 50)

        economy = service.list_economy("Zasariz")
        loot = {row["item"]: row for row in economy["loot"]}
        mote = loot["Mote of Minor Potential"]
        self.assertEqual(mote["mode"], "stored_currency")
        self.assertEqual(mote["qty"], 1)
        self.assertEqual(mote["from"], "a goblin")
        self.assertTrue(mote["is_mote"])
        self.assertFalse(mote["is_wind_rune"])
        self.assertIsNone(mote["coin_value"])
        given = loot["Void-Touched Potential"]
        self.assertEqual(given["mode"], "given")
        self.assertTrue(given["is_mote"])
        self.assertIsNone(given["from"])
        self.assertEqual(len(economy["gives"]), 1)
        offer = economy["gives"][0]
        self.assertEqual(offer["item"], "Wind Rune Geza")
        self.assertEqual(offer["qty"], 1)
        self.assertEqual(offer["npc"], "Dason Goldblade")
        self.assertTrue(offer["is_wind_rune"])
        self.assertFalse(offer["is_mote"])
        self.assertEqual(economy["merges"], [{
            "ts": "2026-08-04T22:00:26",
            "character": "Zasariz",
            "result_item": "Ghoulbane +2",
            "result_tier": 2,
        }])

        again = service.replay(path)
        self.assertEqual(again["events_inserted"], 0)
        self.assertEqual(again["loot"], 2)
        self.assertEqual(again["gives"], 1)
        self.assertEqual(again["merges"], 1)
        reread = service.fight_detail(fight_id, merge_pets=False)
        self.assertEqual(_ability(reread, "Zasariz", "melee", "slash")["damage"], 145)
        self.assertEqual(_heal(reread, "Amop", "Valor")["overheal"], 12)
        self.assertEqual(len(service.list_economy("Zasariz")["loot"]), 2)
        paged = service.list_economy("Zasariz", limit=1, offset=1)
        self.assertEqual([row["item"] for row in paged["loot"]], ["Void-Touched Potential"])

        from fastapi.testclient import TestClient

        from app.main import app
        from app.parser.api import reset_service

        reset_service(service)
        self.addCleanup(reset_service, None)
        client = TestClient(app)
        body = client.get(f"/api/parser/fights/{fight_id}").json()
        self.assertEqual(_heal(body, "Amop", "Valor")["overheal"], 12)
        self.assertIn("tanking", body)
        self.assertIn("deaths", body)
        self.assertIn("resists", body)
        self.assertIn("procs", body)
        self.assertIn("multi_attack", body)
        listed = client.get("/api/parser/loot", params={"character": "Zasariz"})
        self.assertEqual(listed.status_code, 200)
        payload = listed.json()
        self.assertEqual({row["item"] for row in payload["loot"]}, {"Mote of Minor Potential", "Void-Touched Potential"})
        self.assertEqual(payload["gives"][0]["item"], "Wind Rune Geza")
        self.assertEqual(payload["merges"][0]["result_tier"], 2)

    def test_open_fight_resume_keeps_partial_aggregates(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        split = next(i for i, line in enumerate(LINES) if SPLIT_MARK in line)
        path.write_text("\n".join(LINES[: split + 1]) + "\n", encoding="utf-8")
        first = service.replay(path, finalize=False)
        self.assertEqual(first["fights"], 1)
        fight_id = service.list_fights("Zasariz")["fights"][0]["id"]
        mid = service.fight_detail(fight_id, merge_pets=False)
        self.assertTrue(mid["open"])
        # Slash is 140 until the later riposte. Clusters already closed, plus the
        # still-open crush single and the pet double, match the final rates.
        self.assertEqual(_ability(mid, "Zasariz", "melee", "slash")["damage"], 140)
        you_multi = _multi(mid, "Zasariz")
        self.assertEqual((you_multi["singles"], you_multi["doubles"], you_multi["triples"], you_multi["flurries"]), (2, 1, 1, 2))
        self.assertEqual(_multi(mid, "Zasariz`s warder")["doubles"], 1)
        self.assertEqual(_multi(mid, "a goblin")["doubles"], 2)
        self.assertEqual(_ability(mid, "Zasariz`s warder", "melee", "slash")["damage"], 50)
        service.close()

        resumed, _root = self._service(root)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(LINES[split + 1 :]) + "\n")
        resumed.replay(path, finalize=True)
        detail = resumed.fight_detail(fight_id, merge_pets=False)
        self._assert_closed_fight(detail)
        self.assertEqual(resumed.list_fights("Zasariz")["count"], 1)

    def _write_log(self, root: Path) -> Path:
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        return path

    def _legacy_database(self) -> tuple[Path, Path, int]:
        """A 1.1.0-shaped database: the log was read, breakdowns were not stored."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        service, _root = self._service(root)
        path = self._write_log(root)
        replayed = service.replay(path)
        self.assertGreater(replayed["events_inserted"], 0)
        event_count = service.db.count_events()
        fight_id = service.list_fights("Zasariz")["fights"][0]["id"]
        self.assertEqual(_heal(service.fight_detail(fight_id), "Amop", "Valor")["overheal"], 12)
        # Drop the aggregate version and the breakdowns a 1.1.0 file never had.
        # Leave events in place so a naive reread would skip observe().
        with service.db.lock:
            service.db.conn.execute("DELETE FROM settings WHERE key='schema_version'")
            service.db.conn.execute("DELETE FROM fight_breakdown")
            service.db.commit()
        service.set_idle(45)
        service.set_eq_folder(str(root / "EverQuest Legends"))
        service.db.set_setting("custom_note", "keep-me")
        service.set_pet_owner("Zasariz", "Zasariz`s warder", "Amop")
        service.close()
        return root, path, event_count

    def test_old_database_upgrades_and_gains_breakdowns(self):
        root, _path, event_count = self._legacy_database()
        service, _root = self._service(root)
        self.assertTrue(service.config()["upgrading"] or service.config()["schema_version"] == SCHEMA_VERSION)
        self.assertTrue(service.wait_for_upgrade(30))
        self.assertFalse(service.config()["upgrading"])
        self.assertEqual(service.db.stored_schema_version(), SCHEMA_VERSION)
        self.assertIsNone(service.config()["upgrade_error"])
        fights = service.list_fights("Zasariz")["fights"]
        self.assertEqual(len(fights), 1)
        detail = service.fight_detail(fights[0]["id"])
        self.assertEqual(_heal(detail, "Amop", "Valor")["overheal"], 12)
        self.assertGreaterEqual(len(detail["abilities"]), 1)
        # Rebuilt once from the log. The old events were replaced, not appended.
        self.assertEqual(service.db.count_events(), event_count)
        self.assertEqual(service.db.count_where("fights"), 1)

    def test_second_load_does_not_rebuild(self):
        root, _path, event_count = self._legacy_database()
        first, _root = self._service(root)
        self.assertTrue(first.wait_for_upgrade(30))
        self.assertEqual(first.db.stored_schema_version(), SCHEMA_VERSION)
        with first.db.lock:
            row = first.db.conn.execute("SELECT id, generation FROM log_files").fetchone()
            first.db.conn.execute(
                "INSERT INTO events(file_id, generation, offset, kind) VALUES(?, ?, ?, ?)",
                (row["id"], row["generation"], 9_999_999, "sentinel"),
            )
            first.db.commit()
        first.close()

        second, _root = self._service(root)
        self.assertFalse(second.config()["upgrading"])
        self.assertIsNone(second._upgrade_thread)
        self.assertTrue(second.wait_for_upgrade(5))
        with second.db.lock:
            kept = second.db.conn.execute(
                "SELECT kind FROM events WHERE offset=?",
                (9_999_999,),
            ).fetchone()
        self.assertIsNotNone(kept)
        self.assertEqual(kept["kind"], "sentinel")
        self.assertEqual(second.db.count_events(), event_count + 1)
        self.assertEqual(second.db.stored_schema_version(), SCHEMA_VERSION)
        fight_id = second.list_fights("Zasariz")["fights"][0]["id"]
        self.assertEqual(_heal(second.fight_detail(fight_id), "Amop", "Valor")["overheal"], 12)

    def test_user_settings_survive_rebuild(self):
        root, _path, _event_count = self._legacy_database()
        service, _root = self._service(root)
        self.assertTrue(service.wait_for_upgrade(30))
        self.assertEqual(service.idle, 45.0)
        self.assertEqual(service.db.get_setting("idle_seconds"), "45.0")
        self.assertEqual(service.db.get_setting("custom_note"), "keep-me")
        folder = str(root / "EverQuest Legends")
        self.assertEqual(service.eq_folder(), folder)
        self.assertEqual(service.db.get_setting("eq_install_folder"), folder)
        settings = json.loads((root / "user" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["eqInstallFolder"], folder)
        pets = service.list_pets("Zasariz")
        manual = [pet for pet in pets if pet["pet"] == "Zasariz`s warder"]
        self.assertEqual(len(manual), 1)
        self.assertTrue(manual[0]["manual"])
        self.assertEqual(manual[0]["owner"], "Amop")

    def test_upgrade_does_not_block_startup(self):
        root, path, _event_count = self._legacy_database()
        started = threading.Event()
        release = threading.Event()
        original = ParserService._consume

        def blocked(self, log_path, finalize=True):
            started.set()
            if not release.wait(5):
                raise TimeoutError("upgrade gate")
            return original(self, log_path, finalize=finalize)

        with patch.object(ParserService, "_consume", blocked):
            began = time.perf_counter()
            service = ParserService(user_data=root / "user", db_path=root / "parser.db", idle_seconds=30)
            self.addCleanup(service.close)
            self.addCleanup(release.set)
            self.assertLess(time.perf_counter() - began, 2.0)
            self.assertTrue(service.config()["upgrading"])
            self.assertTrue(started.wait(2))
            config_began = time.perf_counter()
            cfg = service.config()
            self.assertLess(time.perf_counter() - config_began, 1.0)
            self.assertTrue(cfg["upgrading"])
            self.assertEqual(cfg["schema_version"], None)
            release.set()
            self.assertTrue(service.wait_for_upgrade(10))
        self.assertFalse(service.config()["upgrading"])
        self.assertEqual(service.db.stored_schema_version(), SCHEMA_VERSION)
        self.assertTrue(path.is_file())

    def test_packaging_includes_breakdown_module(self):
        module = ROOT / "backend" / "app" / "parser" / "breakdown.py"
        mirror = ROOT / "desktop" / "resources" / "backend" / "app" / "parser" / "breakdown.py"
        self.assertTrue(module.is_file())
        self.assertTrue(
            mirror.is_file(),
            "desktop/resources/backend is a git snapshot of backend/. "
            "scripts/bundle_desktop_resources.py copies backend/ into the package; "
            "the snapshot can lag (it has been missing timeline.py) and is not what "
            "a dev Electron launch imports.",
        )
        specs = [
            ROOT / "backend" / "packaging" / "eq-api.spec",
            ROOT / "packaging" / "eq-api.spec",
            ROOT / "desktop" / "resources" / "backend" / "packaging" / "eq-api.spec",
        ]
        for spec in specs:
            text = spec.read_text(encoding="utf-8")
            self.assertIn("backend.app.parser.breakdown", text, spec)


if __name__ == "__main__":
    unittest.main()
