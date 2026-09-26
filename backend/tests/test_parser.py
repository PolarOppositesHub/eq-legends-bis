"""Parser core, tail, and /api/parser coverage.

Fixtures are short excerpts from Josh's own eqlog_Zasariz_qeynos log, or
synthetic lines with the same shapes. No player chat is committed.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.classify import classify_message  # noqa: E402
from app.parser.discover import discover_logs, parse_log_name  # noqa: E402
from app.parser.service import ParserService  # noqa: E402
from app.parser.tail import LogTail  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "parser" / "eqlog_Zasariz_qeynos.txt"

_CHAT = (
    " says, '",
    " say, '",
    " shouts, '",
    " shout, '",
    " auctions, '",
    " auction, '",
    "out of character",
    "told you, '",
    "tells you, '",
    "You told ",
    "tells the guild",
    "tells the group",
    "tells the raid",
)


def _no_chat(text: str) -> None:
    lowered = text.lower()
    for needle in _CHAT:
        if needle.lower() in lowered:
            raise AssertionError(f"chat line in fixture: {needle}")


class LineShapeTests(unittest.TestCase):
    def test_fixture_has_no_player_chat(self):
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertGreater(text.count("\n"), 100)
        _no_chat(text)

    def test_melee_you_and_third_and_crit(self):
        ev = classify_message("You slash a Teir`Dal priest for 85 points of damage. (Critical)")
        self.assertEqual(ev.kind, "melee")
        self.assertEqual(ev.source, "You")
        self.assertEqual(ev.target, "a Teir`Dal priest")
        self.assertEqual(ev.amount, 85)
        self.assertEqual(ev.verb, "slash")
        self.assertIn("Critical", ev.modifiers)

        ev = classify_message("A Teir`Dal priestess crushes YOU for 4 points of damage.")
        self.assertEqual(ev.kind, "melee")
        self.assertEqual(ev.source, "A Teir`Dal priestess")
        self.assertEqual(ev.target, "YOU")
        self.assertEqual(ev.amount, 4)
        self.assertEqual(ev.verb, "crushes")

        ev = classify_message("Soldier of V`Zher bashes YOU for 1 point of damage.")
        self.assertEqual(ev.amount, 1)
        self.assertEqual(ev.verb, "bashes")

        ev = classify_message("Healtank frenzies on a froglok shin knight for 37 points of damage.")
        self.assertEqual(ev.verb, "frenzies on")
        self.assertEqual(ev.target, "a froglok shin knight")

        ev = classify_message("Zasariz`s warder slashes a cracked skeleton for 16 points of damage.")
        self.assertEqual(ev.source, "Zasariz`s warder")
        self.assertEqual(ev.amount, 16)

        ev = classify_message("Amop shoots a ghoul for 10 points of damage. (Double Bow Shot)")
        self.assertEqual(tuple(ev.modifiers), ("Double", "Bow", "Shot"))
        ev = classify_message("Zasariz`s warder pierces a dread skeleton for 16 points of damage. (Flurry)")
        self.assertEqual(ev.modifiers, ("Flurry",))
        ev = classify_message("You slash Soldier of V`Zher for 44 points of damage. (Riposte Critical)")
        self.assertEqual(ev.modifiers, ("Riposte", "Critical"))

    def test_miss_and_avoidance(self):
        ev = classify_message("You try to slash a Teir`Dal priestess, but miss!")
        self.assertEqual(ev.kind, "miss")
        self.assertEqual(ev.avoidance, "miss")
        self.assertEqual(ev.source, "You")

        ev = classify_message("You try to slash a Teir`Dal priestess, but a Teir`Dal priestess dodges!")
        self.assertEqual(ev.avoidance, "dodge")
        self.assertEqual(ev.target, "a Teir`Dal priestess")

        ev = classify_message("Soldier of V`Zher tries to cleave YOU, but YOU parry!")
        self.assertEqual(ev.avoidance, "parry")
        self.assertEqual(ev.source, "Soldier of V`Zher")
        self.assertEqual(ev.target, "YOU")

        ev = classify_message("Asaka L`Rei tries to crush YOU, but YOU block!")
        self.assertEqual(ev.avoidance, "block")
        ev = classify_message("A Teir`Dal ranger tries to slash YOU, but YOU riposte!")
        self.assertEqual(ev.avoidance, "riposte")

        ev = classify_message("A Teir`Dal priestess tries to crush YOU, but misses! (Riposte)")
        self.assertEqual(ev.avoidance, "miss")
        self.assertEqual(ev.modifiers, ("Riposte",))

        ev = classify_message("You try to smite Kahaptra Z`Taj, but Kahaptra Z`Taj's magical skin absorbs the blow!")
        self.assertEqual(ev.avoidance, "absorb")

        ev = classify_message("A loathling lich tries to slice YOU, but YOU are INVULNERABLE!")
        self.assertEqual(ev.kind, "miss")
        self.assertEqual(ev.avoidance, "invulnerable")
        self.assertEqual(ev.source, "A loathling lich")
        self.assertEqual(ev.verb, "slice")
        self.assertEqual(ev.target, "YOU")

        ev = classify_message("A Teir`Dal shadowknight's magical skin absorbs the damage of Amop's thorns.")
        self.assertEqual(ev.kind, "avoid")
        self.assertEqual(ev.avoidance, "absorb")
        self.assertEqual(ev.target, "A Teir`Dal shadowknight")
        self.assertEqual(ev.source, "Amop")

        ev = classify_message("Rukgutt tries to cast a spell on you, but you are protected.")
        self.assertEqual(ev.kind, "avoid")
        self.assertEqual(ev.avoidance, "protected")
        self.assertEqual(ev.source, "Rukgutt")

    def test_spells_dots_and_damage_shields(self):
        ev = classify_message("You hit a Teir`Dal priestess for 297 points of magic damage by Garrison's Mighty Mana Shock.")
        self.assertEqual(ev.kind, "spell")
        self.assertEqual(ev.amount, 297)
        self.assertEqual(ev.damage_type, "magic")
        self.assertEqual(ev.spell, "Garrison's Mighty Mana Shock")

        ev = classify_message("You hit a Teir`Dal shadowknight for 235 points of magic damage by Garrison's Mighty Mana Shock. (Critical)")
        self.assertIn("Critical", ev.modifiers)
        self.assertEqual(ev.kind, "spell")

        ev = classify_message("a Teir`Dal priestess hit you for 32 points of magic damage by Holy Might.")
        self.assertEqual(ev.source, "a Teir`Dal priestess")
        self.assertEqual(ev.target, "you")

        ev = classify_message("Noble Dojorn hit you for 500 points of unresistable damage by Soul Devour.")
        self.assertEqual(ev.damage_type, "unresistable")

        ev = classify_message("Soldier of V`Zher has taken 41 damage from your Stinging Swarm.")
        self.assertEqual(ev.kind, "dot")
        self.assertEqual(ev.source, "You")
        self.assertEqual(ev.target, "Soldier of V`Zher")
        self.assertEqual(ev.amount, 41)
        self.assertEqual(ev.spell, "Stinging Swarm")

        ev = classify_message("You have taken 29 damage from Searing Arrow by a Teir`Dal ranger.")
        self.assertEqual(ev.target, "you")
        self.assertEqual(ev.source, "a Teir`Dal ranger")
        self.assertEqual(ev.spell, "Searing Arrow")

        ev = classify_message("Korven Nisere has taken 22 damage from Denon's Disruptive Discord by Mozzmozz. (Critical)")
        self.assertEqual(ev.source, "Mozzmozz")
        self.assertEqual(ev.spell, "Denon's Disruptive Discord")
        self.assertIn("Critical", ev.modifiers)

        ev = classify_message("Kobarab has taken 1 damage by Rabies.")
        self.assertIsNone(ev.source)
        self.assertEqual(ev.spell, "Rabies")

        ev = classify_message("YOU are pierced by a Teir`Dal shadowknight's thorns for 6 points of non-melee damage!")
        self.assertEqual(ev.kind, "ds")
        self.assertEqual(ev.source, "a Teir`Dal shadowknight")
        self.assertEqual(ev.target, "YOU")
        self.assertEqual(ev.amount, 6)
        self.assertEqual(ev.spell, "thorns")

        ev = classify_message("Konartik is burned by a willowisp's flames for 7 points of non-melee damage.")
        self.assertEqual(ev.source, "a willowisp")
        self.assertEqual(ev.verb, "burned")

        ev = classify_message("A froglok vis knight is tormented by Ayrik's frost for 12 points of non-melee damage.")
        self.assertEqual(ev.source, "Ayrik")
        self.assertEqual(ev.spell, "frost")

        ev = classify_message("You were hit by non-melee for 5 damage.")
        self.assertEqual(ev.kind, "ds")
        self.assertEqual(ev.amount, 5)
        self.assertIsNone(ev.source)

        ev = classify_message("Your Inner Fire spell did not take hold on Zasariz`s warder. (Blocked by Courage.)")
        self.assertEqual(ev.kind, "resist")
        self.assertEqual(ev.spell, "Inner Fire")
        self.assertEqual(ev.target, "Zasariz`s warder")
        self.assertIn("Blocked", ev.modifiers)

    def test_heals_including_overheal_and_unknown_spell(self):
        ev = classify_message("You healed Zasariz for 132 (181) hit points by Healing.")
        self.assertEqual(ev.kind, "heal")
        self.assertEqual(ev.amount, 132)
        self.assertEqual(ev.amount_full, 181)
        self.assertEqual(ev.overheal, 49)
        self.assertEqual(ev.spell, "Healing")
        self.assertFalse(ev.over_time)

        ev = classify_message("You healed Zasariz over time for 61 hit points by Flowering Heal.")
        self.assertTrue(ev.over_time)
        self.assertEqual(ev.spell, "Flowering Heal")
        self.assertEqual(ev.amount, 61)
        self.assertIsNone(ev.amount_full)

        ev = classify_message("Amop healed you for 48 hit points.")
        self.assertEqual(ev.source, "Amop")
        self.assertEqual(ev.target, "you")
        self.assertEqual(ev.amount, 48)
        self.assertIsNone(ev.spell)

        ev = classify_message("Amop healed himself for 0 (2) hit points by Blessing of the Squire.")
        self.assertEqual(ev.amount, 0)
        self.assertEqual(ev.amount_full, 2)
        self.assertEqual(ev.target, "himself")

        ev = classify_message("The heal within you effloresces.")
        self.assertEqual(ev.kind, "flavour")

        ev = classify_message("You mend your wounds and heal some damage.")
        self.assertEqual(ev.kind, "flavour")

    def test_deaths_casts_and_resists(self):
        ev = classify_message("You have slain Soldier of V`Zher!")
        self.assertEqual(ev.kind, "slain")
        self.assertEqual(ev.source, "You")
        self.assertEqual(ev.target, "Soldier of V`Zher")

        ev = classify_message("A scorched zombie has been slain by Amop!")
        self.assertEqual(ev.source, "Amop")
        self.assertEqual(ev.target, "A scorched zombie")

        ev = classify_message("You have been slain by ice boned skeleton!")
        self.assertEqual(ev.kind, "death")
        self.assertEqual(ev.target, "You")
        self.assertEqual(ev.source, "ice boned skeleton")

        ev = classify_message("You died.")
        self.assertEqual(ev.kind, "death")
        self.assertEqual(ev.target, "You")

        ev = classify_message("A frenzied ghoul died.")
        self.assertEqual(ev.kind, "death")
        self.assertEqual(ev.target, "A frenzied ghoul")

        ev = classify_message("You have been knocked unconscious!")
        self.assertEqual(ev.kind, "knockout")

        ev = classify_message("You begin casting Garrison's Mighty Mana Shock.")
        self.assertEqual(ev.kind, "cast")
        self.assertEqual(ev.spell, "Garrison's Mighty Mana Shock")

        ev = classify_message("A Teir`Dal priest begins casting Root.")
        self.assertEqual(ev.source, "A Teir`Dal priest")
        self.assertEqual(ev.spell, "Root")

        ev = classify_message("Your Stinging Swarm spell is interrupted.")
        self.assertEqual(ev.kind, "interrupt")
        self.assertEqual(ev.spell, "Stinging Swarm")

        ev = classify_message("a Teir`Dal ranger's Burst of Fire spell is interrupted.")
        self.assertEqual(ev.source, "a Teir`Dal ranger")
        self.assertEqual(ev.spell, "Burst of Fire")

        ev = classify_message("Your Symbol of Transal spell fizzles!")
        self.assertEqual(ev.kind, "fizzle")
        self.assertEqual(ev.spell, "Symbol of Transal")

        ev = classify_message("Amop's Minor Summoning: Air spell fizzles!")
        self.assertEqual(ev.source, "Amop")
        self.assertEqual(ev.spell, "Minor Summoning: Air")

        ev = classify_message("You resist a Teir`Dal ranger's Grasping Roots!")
        self.assertEqual(ev.kind, "resist")
        self.assertEqual(ev.spell, "Grasping Roots")
        self.assertEqual(ev.target, "You")

        ev = classify_message("Soldier of V`Zher resisted your Garrison's Mighty Mana Shock!")
        self.assertEqual(ev.target, "Soldier of V`Zher")
        self.assertEqual(ev.spell, "Garrison's Mighty Mana Shock")

        ev = classify_message("You gain a rune for 55 points of absorption.")
        self.assertEqual(ev.kind, "rune")
        self.assertEqual(ev.amount, 55)

        ev = classify_message("Your Golden Efreeti Boots shimmers briefly.")
        self.assertEqual(ev.kind, "proc")
        self.assertEqual(ev.item, "Golden Efreeti Boots")

    def test_loot_merge_xp_level_zone_group(self):
        ev = classify_message("--You have looted a Mote of Infinitesimal Potential from a Teir`Dal rogue's corpse.--")
        self.assertEqual(ev.kind, "loot")
        self.assertEqual(ev.mode, "bag")
        self.assertEqual(ev.item, "Mote of Infinitesimal Potential")
        self.assertEqual(ev.qty, 1)
        self.assertTrue(ev.extra["is_mote"])

        ev = classify_message("You looted a Fine Steel Two Handed Sword +1 from a Teir`Dal priest's corpse and sold it for 5 platinum.")
        self.assertEqual(ev.mode, "autosold")
        self.assertEqual(ev.item, "Fine Steel Two Handed Sword +1")
        self.assertEqual(ev.coin_copper, 5000)
        self.assertEqual(ev.target, "a Teir`Dal priest")

        ev = classify_message("You looted a Skeletal Rod from skeleton L`rodd's corpse and sold it for free.")
        self.assertEqual(ev.coin_copper, 0)

        ev = classify_message("You looted 2 Undead Froglok Tongue from a shin ghoul knight's corpse and sold it for 1 gold, 1 silver and 6 copper.")
        self.assertEqual(ev.qty, 2)
        self.assertEqual(ev.item, "Undead Froglok Tongue")
        self.assertEqual(ev.coin_copper, 116)

        ev = classify_message("You looted a Pristine Studded Leather Sleeves from Soldier of V`Zher's corpse to create a Pristine Studded Leather Sleeves +3")
        self.assertEqual(ev.mode, "merged")
        self.assertEqual(ev.result_item, "Pristine Studded Leather Sleeves +3")
        self.assertEqual(ev.result_tier, 3)

        ev = classify_message("You looted an Enchanted Fine Steel Rapier from Korven Nisere's corpse to create an Enchanted Fine Steel Rapier +4")
        self.assertEqual(ev.mode, "merged")
        self.assertEqual(ev.item, "Enchanted Fine Steel Rapier")
        self.assertEqual(ev.result_item, "Enchanted Fine Steel Rapier +4")
        self.assertEqual(ev.result_tier, 4)

        ev = classify_message("You looted a Mote of Greater Potential from Soldier of V`Zher's corpse and stored it in your currency")
        self.assertEqual(ev.mode, "stored_currency")
        self.assertTrue(ev.extra["is_mote"])

        ev = classify_message("You looted an Imbrued Platemail Bracer from a revultant rat's corpse and stored it in your Dragon Hoard")
        self.assertEqual(ev.mode, "stored_hoard")
        self.assertEqual(ev.item, "Imbrued Platemail Bracer")

        ev = classify_message("You looted a Crystallized Sulfur from Amygdalan warrior's corpse and stored it in your tradeskill depot")
        self.assertEqual(ev.mode, "stored_depot")

        ev = classify_message("You have been given: Void-Touched Potential")
        self.assertEqual(ev.mode, "given")
        self.assertTrue(ev.extra["is_mote"])

        ev = classify_message("You receive 4 silver and 1 copper from the corpse.")
        self.assertEqual(ev.mode, "coin")
        self.assertEqual(ev.coin_copper, 41)

        ev = classify_message("You offered 1 The Baron's Blade +3 to Amop.")
        self.assertEqual(ev.kind, "give")
        self.assertEqual(ev.qty, 1)
        self.assertEqual(ev.item, "The Baron's Blade +3")
        self.assertEqual(ev.target, "Amop")

        ev = classify_message("You offered 1,928 Copper to Amop.")
        self.assertEqual(ev.kind, "give")
        self.assertEqual(ev.qty, 1928)
        self.assertEqual(ev.item, "Copper")
        self.assertEqual(ev.target, "Amop")

        ev = classify_message("You receive 4 silver from Zok Zribb.")
        self.assertEqual(ev.kind, "loot")
        self.assertEqual(ev.mode, "payment")
        self.assertEqual(ev.coin_copper, 40)
        self.assertEqual(ev.target, "Zok Zribb")

        ev = classify_message("You have successfully merged two items together to create a new item: Garrison's Mighty Mana Shock I")
        self.assertEqual(ev.kind, "merge")
        self.assertIsNone(ev.result_tier)
        self.assertIn("Garrison's Mighty Mana Shock", ev.result_item)

        ev = classify_message("You have successfully merged two items together to create a new item: Damask Robe +1")
        self.assertEqual(ev.result_tier, 1)

        ev = classify_message("The item you are trying to add will not work, this mote is not sufficiently powerful to upgrade this item.")
        self.assertEqual(ev.kind, "mote_reject")

        ev = classify_message("You gain experience! (2.617%)")
        self.assertEqual(ev.kind, "xp")
        self.assertAlmostEqual(ev.xp_pct, 2.617)
        self.assertFalse(ev.party_xp)

        ev = classify_message("You gain party experience! (0.469%)")
        self.assertTrue(ev.party_xp)
        self.assertAlmostEqual(ev.xp_pct, 0.469)

        ev = classify_message("You gain party experience (with a bonus)! (3.712%)")
        self.assertTrue(ev.party_xp)
        self.assertTrue(ev.extra["bonus"])
        self.assertAlmostEqual(ev.xp_pct, 3.712)

        ev = classify_message("You gain party experience!")
        self.assertEqual(ev.kind, "xp")
        self.assertTrue(ev.party_xp)
        self.assertIsNone(ev.xp_pct)

        ev = classify_message("You gain experience!")
        self.assertEqual(ev.kind, "xp")
        self.assertFalse(ev.party_xp)
        self.assertIsNone(ev.xp_pct)

        ev = classify_message("You gain experience (with a bonus)! (5.788%)")
        self.assertFalse(ev.party_xp)
        self.assertTrue(ev.extra["bonus"])

        ev = classify_message("You have gained a level! Welcome to level 24!")
        self.assertEqual(ev.kind, "level")
        self.assertEqual(ev.level, 24)

        ev = classify_message("You have gained an ability point!  You now have 3 ability points.")
        self.assertEqual(ev.ability_points, 1)
        self.assertEqual(ev.ability_total, 3)

        ev = classify_message("You have gained 2 ability points!  You now have 5 ability points.")
        self.assertEqual(ev.ability_points, 2)
        self.assertEqual(ev.ability_total, 5)

        ev = classify_message("You have entered Befallen.")
        self.assertEqual(ev.kind, "zone")
        self.assertEqual(ev.zone, "Befallen")
        self.assertIsNone(ev.instance["tier"])

        ev = classify_message("You have entered Befallen 3 (Fused).")
        self.assertEqual(ev.zone, "Befallen")
        self.assertEqual(ev.instance["number"], 3)
        self.assertEqual(ev.instance["tier"], "Fused")

        ev = classify_message("You have entered The Lavastorm Mountains 1 (Awakened).")
        self.assertEqual(ev.zone, "The Lavastorm Mountains")
        self.assertEqual(ev.instance["number"], 1)
        self.assertEqual(ev.instance["tier"], "Awakened")

        ev = classify_message("You have entered Nagafen's Lair - Group.")
        self.assertEqual(ev.zone, "Nagafen's Lair")
        self.assertEqual(ev.instance["scope"], "Group")

        ev = classify_message("You have entered The Plane of Hate - Group 2 (Adaptive).")
        self.assertEqual(ev.zone, "The Plane of Hate")
        self.assertEqual(ev.instance["scope"], "Group")
        self.assertEqual(ev.instance["number"], 2)
        self.assertEqual(ev.instance["tier"], "Adaptive")

        ev = classify_message("You have joined the group.")
        self.assertEqual(ev.kind, "group_join")
        ev = classify_message("Amop has joined the group.")
        self.assertEqual(ev.target, "Amop")
        ev = classify_message("You have been removed from the group.")
        self.assertEqual(ev.kind, "group_leave")
        ev = classify_message("You invite amop to join your group.")
        self.assertEqual(ev.kind, "group_invite")
        self.assertEqual(ev.target, "amop")
        ev = classify_message("You are now the leader of your group.")
        self.assertEqual(ev.kind, "group_leader")

        ev = classify_message("[36 PAL/RNG/ENC] Warcrimes (Human) <Mudder Gukkers> ZONE: North Freeport (freportn)")
        self.assertEqual(ev.kind, "who")
        self.assertEqual(ev.player_name, "Warcrimes")
        self.assertEqual(ev.player_classes, "PAL/RNG/ENC")
        self.assertEqual(ev.player_level, 36)

    def test_pet_tell_binds_and_public_master_does_not(self):
        # Synthetic, same shape as ``Zasariz`s warder told you, 'Attacking ... Master.'``
        ev = classify_message("Jenann told you, 'Attacking a magician Master.'")
        self.assertEqual(ev.kind, "pet_tell")
        self.assertEqual(ev.pet, "Jenann")
        self.assertEqual(ev.evidence, "tell")

        ev = classify_message("Jaber says, 'My leader is Primitive.'")
        self.assertEqual(ev.kind, "pet_leader")
        self.assertEqual(ev.owner, "Primitive")

        ev = classify_message("Jaber says, 'Following you, Master.'")
        self.assertEqual(ev.kind, "pet_nominate")
        self.assertEqual(ev.evidence, "nominate")

        ev = classify_message("Fido says, 'Now greater holding master.  I will only attack something new if ordered.'")
        self.assertEqual(ev.kind, "pet_nominate")

        ev = classify_message("a goblin has been charmed.")
        self.assertEqual(ev.kind, "charm")
        self.assertEqual(ev.pet, "a goblin")

    def test_self_damage_is_not_a_melee_swing(self):
        ev = classify_message("You hurt yourself for 12 points of damage.")
        self.assertEqual(ev.kind, "self_damage")
        self.assertEqual(ev.amount, 12)


class FightReplayTests(unittest.TestCase):
    def _service(self) -> tuple[ParserService, Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        return ParserService(user_data=root, db_path=root / "parser.db", idle_seconds=30), root

    def test_synthetic_two_fights_dps_and_pets(self):
        service, root = self._service()
        log = root / "Logs"
        log.mkdir()
        path = log / "eqlog_Zasariz_qeynos.txt"
        path.write_text(
            "\n".join([
                "[Tue Aug 04 22:00:00 2026] You have joined the group.",
                "[Tue Aug 04 22:00:00 2026] Amop has joined the group.",
                "[Tue Aug 04 22:00:01 2026] You slash a rat for 100 points of damage.",
                "[Tue Aug 04 22:00:02 2026] You slash a rat for 50 points of damage. (Critical)",
                "[Tue Aug 04 22:00:02 2026] You try to slash a rat, but miss!",
                "[Tue Aug 04 22:00:03 2026] Zasariz`s warder slashes a rat for 25 points of damage.",
                "[Tue Aug 04 22:00:03 2026] Amop slashes a rat for 40 points of damage.",
                "[Tue Aug 04 22:00:04 2026] You healed Zasariz for 10 (30) hit points by Light Healing.",
                "[Tue Aug 04 22:00:04 2026] You have slain a rat!",
                "[Tue Aug 04 22:00:05 2026] You looted a Mote of Minor Potential from a rat's corpse and stored it in your currency",
                "[Tue Aug 04 22:00:40 2026] You slash a bat for 10 points of damage.",
                "[Tue Aug 04 22:00:41 2026] You have slain a bat!",
                "[Tue Aug 04 22:00:42 2026] You gain party experience! (1.250%)",
                "[Tue Aug 04 22:00:43 2026] You have gained a level! Welcome to level 12!",
                "",
            ]),
            encoding="utf-8",
        )
        stats = service.replay(path)
        self.assertEqual(stats["events_duplicate"], 0)
        self.assertEqual(stats["fights"], 2)
        self.assertEqual(stats["loot"], 1)
        self.assertEqual(stats["xp"], 1)
        self.assertEqual(stats["levels"], 1)

        fights = service.list_fights(character="Zasariz")["fights"]
        self.assertEqual(len(fights), 2)
        # Newest first.
        bat, rat = fights
        self.assertEqual(bat["targets"], ["a bat"])
        self.assertEqual(bat["your_damage"], 10)
        self.assertEqual(rat["targets"], ["a rat"])
        self.assertEqual(rat["your_damage"], 150)

        detail = service.fight_detail(rat["id"], merge_pets=False)
        by_name = {row["source"]: row for row in detail["sources"]}
        you = by_name["Zasariz"]
        self.assertEqual(you["damage"], 150)
        self.assertEqual(you["melee"], 150)
        self.assertEqual(you["hits"], 2)
        self.assertEqual(you["misses"], 1)
        self.assertEqual(you["crits"], 1)
        self.assertEqual(you["max_hit"], 100)
        self.assertEqual(you["heals"], 10)
        self.assertEqual(you["heals_full"], 30)
        self.assertEqual(you["overheal"], 20)
        self.assertAlmostEqual(you["dps"], 150.0)  # active window is 1 second
        self.assertAlmostEqual(you["sdps"], 50.0)  # 150 / 3s fight
        self.assertEqual(by_name["Zasariz`s warder"]["kind"], "pet")
        self.assertEqual(by_name["Zasariz`s warder"]["owner"], "Zasariz")
        self.assertEqual(by_name["Zasariz`s warder"]["damage"], 25)
        self.assertEqual(by_name["Amop"]["kind"], "group")
        self.assertEqual(by_name["Amop"]["damage"], 40)
        self.assertEqual(detail["totals"]["damage"], 215)

        merged = service.fight_detail(rat["id"], merge_pets=True)
        rolled = {row["source"]: row for row in merged["sources"]}
        self.assertNotIn("Zasariz`s warder", rolled)
        self.assertEqual(rolled["Zasariz"]["damage"], 175)
        self.assertEqual(len(rolled["Zasariz"]["pets"]), 1)
        self.assertAlmostEqual(rolled["Zasariz"]["dps"], 87.5)  # 175 over 22:00:01-22:00:03
        self.assertAlmostEqual(rolled["Zasariz"]["sdps"], 175 / 3)
        self.assertEqual(merged["totals"]["damage"], 215)

        pets = service.list_pets("Zasariz")
        self.assertEqual(pets[0]["pet"], "Zasariz`s warder")
        self.assertEqual(pets[0]["owner"], "Zasariz")
        self.assertEqual(pets[0]["evidence"], "warder_name")
        self.assertFalse(pets[0]["manual"])

    def test_public_master_say_does_not_bind_tell_does(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text(
            "\n".join([
                "[Tue Aug 04 22:00:00 2026] Jaber says, 'Following you, Master.'",
                "[Tue Aug 04 22:00:01 2026] Fido says, 'Now greater holding master.  I will only attack something new if ordered.'",
                "[Tue Aug 04 22:00:02 2026] Jenann told you, 'Attacking a magician Master.'",
                "[Tue Aug 04 22:00:03 2026] Jenann slashes a rat for 5 points of damage.",
                "[Tue Aug 04 22:00:03 2026] You slash a rat for 5 points of damage.",
                "[Tue Aug 04 22:00:04 2026] You have slain a rat!",
                "",
            ]),
            encoding="utf-8",
        )
        service.replay(path)
        pets = {row["pet"]: row for row in service.list_pets("Zasariz")}
        self.assertNotIn("Jaber", pets)
        self.assertNotIn("Fido", pets)
        self.assertEqual(pets["Jenann"]["owner"], "Zasariz")
        self.assertEqual(pets["Jenann"]["evidence"], "tell")

    def test_manual_pet_overrides_and_unassign_sticks(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text(
            "[Tue Aug 04 22:00:00 2026] Jenann told you, 'Attacking a magician Master.'\n",
            encoding="utf-8",
        )
        service.replay(path)
        service.set_pet_owner("Zasariz", "Jenann", "Amop")
        # A later tell must not pull the pet back to Zasariz.
        extra = root / "eqlog_Zasariz_qeynos.txt"
        with extra.open("a", encoding="utf-8") as handle:
            handle.write("[Tue Aug 04 22:00:05 2026] Jenann told you, 'Attacking a bat Master.'\n")
        service.replay(extra)
        pets = {row["pet"]: row for row in service.list_pets("Zasariz")}
        self.assertEqual(pets["Jenann"]["owner"], "Amop")
        self.assertTrue(pets["Jenann"]["manual"])

        service.set_pet_owner("Zasariz", "Jenann", None)
        with extra.open("a", encoding="utf-8") as handle:
            handle.write("[Tue Aug 04 22:00:06 2026] Jenann told you, 'Attacking a bat Master.'\n")
        service.replay(extra)
        pets = {row["pet"]: row for row in service.list_pets("Zasariz")}
        self.assertIsNone(pets["Jenann"]["owner"])
        self.assertTrue(pets["Jenann"]["manual"])

    def test_charm_requires_your_cast(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        path.write_text(
            "\n".join([
                "[Tue Aug 04 22:00:00 2026] a goblin has been charmed.",
                "[Tue Aug 04 22:00:20 2026] You begin casting Charm.",
                "[Tue Aug 04 22:00:22 2026] a wolf has been charmed.",
                "",
            ]),
            encoding="utf-8",
        )
        service.replay(path)
        pets = {row["pet"]: row for row in service.list_pets("Zasariz")}
        self.assertNotIn("a goblin", pets)
        self.assertEqual(pets["a wolf"]["evidence"], "charm")
        self.assertEqual(pets["a wolf"]["owner"], "Zasariz")

    def test_real_excerpt_fights_and_idempotent_reread(self):
        service, _root = self._service()
        stats = service.replay(FIXTURE)
        self.assertEqual(stats["events_duplicate"], 0)
        self.assertGreaterEqual(stats["fights"], 2)
        self.assertGreater(stats["loot"], 0)
        self.assertGreater(stats["xp"], 0)
        fights = service.list_fights(character="Zasariz")["fights"]
        # Newest first: rogue, then soldier, then the priest/priestess pull.
        self.assertGreaterEqual(len(fights), 3)
        rogue = next(f for f in fights if "a Teir`Dal rogue" in f["targets"])
        soldier = next(f for f in fights if "Soldier of V`Zher" in f["targets"])
        priests = next(f for f in fights if "a Teir`Dal priestess" in f["targets"])
        self.assertIn("a Teir`Dal priest", priests["targets"])
        self.assertNotIn("Soldier of V`Zher", priests["targets"])
        self.assertEqual(rogue["your_damage"], 853)
        self.assertGreater(rogue["your_dps"], 0)
        self.assertGreater(rogue["duration_seconds"], 0)
        self.assertAlmostEqual(rogue["your_sdps"], 853 / rogue["duration_seconds"])

        detail = service.fight_detail(rogue["id"], merge_pets=True)
        you = next(row for row in detail["sources"] if row["source"] == "Zasariz")
        self.assertEqual(you["melee"], 176)
        self.assertEqual(you["spell"], 677)
        self.assertEqual(you["hits"], 8)
        self.assertEqual(you["misses"], 1)
        self.assertEqual(you["max_hit"], 297)
        soldier_detail = service.fight_detail(soldier["id"], merge_pets=False)
        you = next(row for row in soldier_detail["sources"] if row["source"] == "Zasariz")
        self.assertGreater(you["dot"], 0)
        self.assertGreater(you["spell"], 0)
        self.assertGreater(soldier_detail["totals"]["damage"], 0)

        event_count = stats["event_count"]
        loot_count = stats["loot"]
        again = service.replay(FIXTURE)
        self.assertEqual(again["events_inserted"], 0)
        self.assertGreater(again["events_duplicate"], 0)
        self.assertEqual(again["event_count"], event_count)
        self.assertEqual(again["loot"], loot_count)
        self.assertEqual(again["fights"], stats["fights"])
        rogue_again = next(f for f in service.list_fights("Zasariz")["fights"] if "a Teir`Dal rogue" in f["targets"])
        self.assertEqual(rogue_again["your_damage"], 853)

    def test_replay_reports_progress_on_a_large_synthetic_log(self):
        service, root = self._service()
        path = root / "eqlog_Zasariz_qeynos.txt"
        line = "[Tue Aug 04 22:00:00 2026] You slash a rat for 10 points of damage.\n"
        # Just over one chunk so a progress event is required, and cheap enough
        # for the unit suite. The full-log timing is reported from the real file.
        count = CHUNK if False else 50_000
        from app.parser.service import CHUNK_LINES
        count = CHUNK_LINES
        with path.open("w", encoding="utf-8") as handle:
            for _ in range(count):
                handle.write(line)
        seen = []
        service.hub.publish = lambda event: seen.append(event)  # type: ignore[method-assign]
        stats = service.replay(path)
        self.assertEqual(stats["lines"], count)
        self.assertEqual(stats["unclassified"], 0)
        self.assertTrue(any(event.get("type") == "progress" and event.get("lines") == count for event in seen))
        self.assertLess(stats["elapsed_ms"], 15_000)


class TailTests(unittest.TestCase):
    def test_fragments_are_delivered_once_and_file_is_closed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "eqlog_Zasariz_qeynos.txt"
        path.write_bytes(b"")
        opened = []
        real_open = open

        def wrapped(*args, **kwargs):
            handle = real_open(*args, **kwargs)
            if args and str(args[0]) == str(path) and "b" in str(kwargs.get("mode", args[1] if len(args) > 1 else "")):
                opened.append(handle)
            return handle

        import builtins
        builtins.open = wrapped
        self.addCleanup(setattr, builtins, "open", real_open)
        tail = LogTail(path, poll_interval=0.25)
        self.assertEqual(tail.poll_interval, 0.25)
        with real_open(path, "ab") as handle:
            handle.write(b"[Tue Aug 04 22:04:06 2026] You slash a rat for 10 ")
        self.assertEqual(tail.poll().lines, [])
        with real_open(path, "ab") as handle:
            handle.write(b"points of damage.\r\n[Tue Aug 04 22:04:07 2026] You ")
        first = tail.poll()
        self.assertEqual(len(first.lines), 1)
        self.assertIn("10 points of damage.", first.lines[0].text)
        with real_open(path, "ab") as handle:
            handle.write(b"have slain a rat!\r\n")
        second = tail.poll()
        self.assertEqual(len(second.lines), 1)
        self.assertIn("slain a rat", second.lines[0].text)
        third = tail.poll()
        self.assertEqual(third.lines, [])
        self.assertTrue(opened)
        self.assertTrue(all(handle.closed for handle in opened))
        # Rename succeeds because the tail does not keep the file open.
        renamed = path.with_suffix(".txt.moved")
        path.rename(renamed)
        self.assertTrue(renamed.exists())

    def test_truncation_resets_to_zero(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "eqlog_Zasariz_qeynos.txt"
        path.write_bytes(b"[Tue Aug 04 22:04:06 2026] You slash a rat for 10 points of damage.\r\n")
        tail = LogTail(path)
        first = tail.poll()
        self.assertEqual(len(first.lines), 1)
        self.assertFalse(first.truncated)
        self.assertGreater(tail.offset, 0)
        path.write_bytes(b"[Tue Aug 04 22:05:00 2026] You slash a bat for 1 point of damage.\r\n")
        second = tail.poll()
        self.assertTrue(second.truncated)
        self.assertEqual(len(second.lines), 1)
        self.assertIn("a bat", second.lines[0].text)
        self.assertNotIn("a rat", second.lines[0].text)
        self.assertEqual(second.lines[0].offset, 0)


class DiscoveryAndApiTests(unittest.TestCase):
    def test_filename_and_discovery_use_logs_folder(self):
        self.assertEqual(parse_log_name("eqlog_Zasariz_qeynos.txt"), ("Zasariz", "qeynos"))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        logs = root / "Logs"
        logs.mkdir()
        older = logs / "eqlog_Amop_qeynos.txt"
        newer = logs / "eqlog_Zasariz_qeynos.txt"
        older.write_text("x\n", encoding="utf-8")
        newer.write_text("y\n", encoding="utf-8")
        os.utime(older, (1_000, 1_000))
        os.utime(newer, (2_000, 2_000))
        (root / "notes.txt").write_text("nope", encoding="utf-8")
        found = discover_logs(root)
        self.assertEqual([row["character"] for row in found], ["Zasariz", "Amop"])
        self.assertEqual(found[0]["server"], "qeynos")

    def test_settings_json_folder_is_reused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        user = root / "user"
        install = root / "eq"
        (install / "Logs").mkdir(parents=True)
        log = install / "Logs" / "eqlog_Zasariz_qeynos.txt"
        log.write_text("[Tue Aug 04 22:00:00 2026] You gain experience! (1.000%)\n", encoding="utf-8")
        service = ParserService(user_data=user, db_path=user / "parser.db")
        service.set_eq_folder(str(install))
        # Other settings keys survive.
        settings = (user / "settings.json").read_text(encoding="utf-8")
        self.assertIn("eqInstallFolder", settings)
        listed = service.list_logs()
        self.assertEqual(listed["logs"][0]["character"], "Zasariz")
        service.set_idle(45)
        self.assertEqual(service.config()["idle_seconds"], 45)

    def test_rest_endpoints(self):
        httpx = __import__("importlib").import_module("importlib").util
        try:
            import httpx  # noqa: F401
        except ImportError:
            self.skipTest("httpx is not installed")
        from fastapi.testclient import TestClient

        from app.main import app
        from app.parser.api import reset_service

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        install = root / "eq"
        (install / "Logs").mkdir(parents=True)
        log = install / "Logs" / "eqlog_Zasariz_qeynos.txt"
        log.write_text(
            "\n".join([
                "[Tue Aug 04 22:00:01 2026] You slash a rat for 20 points of damage.",
                "[Tue Aug 04 22:00:02 2026] You have slain a rat!",
                "",
            ]),
            encoding="utf-8",
        )
        service = ParserService(user_data=root / "user", db_path=root / "parser.db")
        reset_service(service)
        self.addCleanup(reset_service, None)
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["ok"])

        cfg = client.post("/api/parser/config", json={"eq_install_folder": str(install), "idle_seconds": 30})
        self.assertEqual(cfg.status_code, 200)
        logs = client.get("/api/parser/logs")
        self.assertEqual(logs.status_code, 200)
        self.assertEqual(logs.json()["logs"][0]["name"], "eqlog_Zasariz_qeynos.txt")

        loaded = client.post("/api/parser/load", json={"path": str(log)})
        self.assertEqual(loaded.status_code, 200, loaded.text)
        body = loaded.json()
        self.assertEqual(body["fights"], 1)
        self.assertEqual(body["events_inserted"], body["classified"])

        fights = client.get("/api/parser/fights")
        self.assertEqual(fights.status_code, 200)
        fight_id = fights.json()["fights"][0]["id"]
        detail = client.get(f"/api/parser/fights/{fight_id}", params={"merge_pets": True})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["totals"]["damage"], 20)
        self.assertIn("dps", detail.json()["sources"][0])
        self.assertIn("sdps", detail.json()["sources"][0])

        bound = client.post("/api/parser/pets", json={"character": "Zasariz", "pet": "Jaber", "owner": "Zasariz"})
        self.assertEqual(bound.status_code, 200)
        listed = client.get("/api/parser/pets", params={"character": "Zasariz"})
        self.assertEqual(listed.json()["pets"][0]["owner"], "Zasariz")
        cleared = client.post("/api/parser/pets", json={"character": "Zasariz", "pet": "Jaber", "owner": None})
        self.assertIsNone(cleared.json()["owner"])

        again = client.post("/api/parser/load", json={"path": str(log)})
        self.assertEqual(again.json()["events_inserted"], 0)

        rejected = client.post("/api/parser/load", json={"path": str(root / "missing.txt")})
        self.assertEqual(rejected.status_code, 404)

    def test_sse_hello_over_a_real_socket(self):
        """Starlette's TestClient buffers an infinite SSE body, so this uses a socket."""
        import socket
        import threading

        import httpx
        import uvicorn

        from app.main import app
        from app.parser.api import reset_service

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        reset_service(ParserService(user_data=root / "user", db_path=root / "parser.db"))
        self.addCleanup(reset_service, None)

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        self.addCleanup(setattr, server, "should_exit", True)
        deadline = time.time() + 5
        while not getattr(server, "started", False) and time.time() < deadline:
            time.sleep(0.02)
        self.assertTrue(server.started)

        with httpx.stream("GET", f"http://127.0.0.1:{port}/api/parser/stream", timeout=5.0) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            chunk = next(response.iter_text())
            self.assertIn("event: hello", chunk)
        server.should_exit = True
        thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
