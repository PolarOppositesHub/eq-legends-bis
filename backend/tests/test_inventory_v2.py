"""Inventory import v2 parser (SPEC §4.4 tests 1–6).

Fixtures are synthetic and follow the verified Inventory.txt shapes:
two TSV tables, -Slot children, Personal-Depot1, and mote names from
the eqlwiki list. No item stats are invented. An unverified section
header is kept as raw unknown_rows and is not parsed into columns.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.inventory import (  # noqa: E402
    EXALTATION_SOCKET_LABELS,
    MOTE_GRADES,
    VOID_TOUCHED_NAME,
    WIND_RUNE_NAMES,
    parse_inventory_tsv,
)
from app.main import app  # noqa: E402
from app.parser.sources import MOTE_NAMES, WIND_RUNES  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_inventory.txt"

LOCATION_HEADER = "Location\tName\tID\tCount\tSlots"
KEYRING_HEADER = "KeyRing\tName\tID\t"


def _parent_name(parsed: dict, row: dict) -> str | None:
    parent_idx = row["parent_idx"]
    if parent_idx is None:
        return None
    return parsed["rows"][parent_idx]["name_raw"]


def _by_name(parsed: dict, name: str) -> dict:
    matches = [row for row in parsed["rows"] if row["name_raw"] == name]
    if len(matches) != 1:
        raise AssertionError(f"expected one row named {name!r}, found {len(matches)}")
    return matches[0]


class InventoryV2SpecTests(unittest.TestCase):
    def test_mote_names_match_the_log_parser_list(self):
        self.assertEqual([name for _grade, name in MOTE_GRADES], list(MOTE_NAMES[:10]))
        self.assertEqual(MOTE_NAMES[10], VOID_TOUCHED_NAME)
        self.assertEqual(WIND_RUNE_NAMES, WIND_RUNES)

    def test_1_table2_header_is_never_an_item(self):
        text = FIXTURE.read_text(encoding="utf-8")
        parsed = parse_inventory_tsv(text)
        names = [row["name"] for row in parsed["all_items"]]
        locations = [row["location"] for row in parsed["all_items"]]
        self.assertNotIn("Name", names)
        self.assertNotIn("KeyRing", locations)
        self.assertNotIn("Location", locations)
        rings = [entry["ring"] for entry in parsed["keyring"]]
        self.assertEqual(rings, ["Equipment", "Augmentation", "Activated"])
        self.assertTrue(all(entry["count"] == 1 for entry in parsed["keyring"]))

    def test_2_personal_depot_slot_parent_keeps_the_hyphen(self):
        text = FIXTURE.read_text(encoding="utf-8")
        parsed = parse_inventory_tsv(text)
        parent = _by_name(parsed, "Depot Sample")
        child = _by_name(parsed, "Depot Child")
        self.assertEqual(parent["location_raw"], "Personal-Depot1")
        self.assertEqual(parent["container_kind"], "depot")
        self.assertEqual(parent["depth"], 0)
        self.assertIsNone(parent["parent_idx"])
        self.assertEqual(child["location_raw"], "Personal-Depot1-Slot3")
        self.assertEqual(child["container_kind"], "depot")
        self.assertEqual(child["depth"], 1)
        self.assertEqual(child["socket_index"], 3)
        self.assertIsNone(child["socket_label"])
        self.assertEqual(_parent_name(parsed, child), "Depot Sample")
        shared = _by_name(parsed, "Shared Sample")
        self.assertEqual(shared["container_kind"], "sharedbank")
        self.assertEqual(shared["location_raw"], "SharedBank1")

    def test_3_each_ear_gets_its_own_slot7_child(self):
        text = "\n".join([
            LOCATION_HEADER,
            "Ear\tLeft Ear\t1\t1\t10",
            "Ear-Slot7\tLeft Focus\t2\t1\t10",
            "Ear\tRight Ear\t3\t1\t10",
            "Ear-Slot7\tRight Focus\t4\t1\t10",
        ])
        parsed = parse_inventory_tsv(text)
        left = _by_name(parsed, "Left Focus")
        right = _by_name(parsed, "Right Focus")
        self.assertEqual(_parent_name(parsed, left), "Left Ear")
        self.assertEqual(_parent_name(parsed, right), "Right Ear")
        self.assertEqual(left["socket_index"], 7)
        self.assertEqual(left["socket_label"], "Slot7 (Focus?)")
        # The synthetic dump's single Ear-Slot7 follows both ears, so it
        # attaches to the most recent one.
        synthetic = parse_inventory_tsv(FIXTURE.read_text(encoding="utf-8"))
        focus = _by_name(synthetic, "Focus Stone")
        self.assertEqual(_parent_name(synthetic, focus), "Right Ear Stud")

    def test_4_plus5_with_slot2_and_slot7_through_10_has_four_sockets(self):
        text = "\n".join([
            LOCATION_HEADER,
            "Primary\tFixture Blade +5\t1\t1\t10",
            "Primary-Slot2\tOrdinary Aug\t2\t1\t10",
            "Primary-Slot7\tFocus Aug\t3\t1\t10",
            "Primary-Slot8\tClick Aug\t4\t1\t10",
            "Primary-Slot9\tWorn Aug\t5\t1\t10",
            "Primary-Slot10\tProc Aug\t6\t1\t10",
        ])
        parsed = parse_inventory_tsv(text)
        blade = _by_name(parsed, "Fixture Blade +5")
        self.assertEqual(blade["tier"], 5)
        self.assertEqual(blade["name"], "Fixture Blade")
        children = [row for row in parsed["rows"] if row["parent_idx"] == parsed["rows"].index(blade)]
        exaltation = [row for row in children if row["socket_index"] in (7, 8, 9, 10)]
        self.assertEqual(len(exaltation), 4)
        self.assertEqual(len(exaltation), min(blade["tier"], 4))
        self.assertEqual(
            [row["socket_label"] for row in exaltation],
            [EXALTATION_SOCKET_LABELS[n] for n in (7, 8, 9, 10)],
        )
        ordinary = [row for row in children if row["socket_index"] == 2]
        self.assertEqual(len(ordinary), 1)
        self.assertIsNone(ordinary[0]["socket_label"])
        self.assertEqual(parsed["equipment"].get("PRIMARY"), "Fixture Blade")

    def test_5_mote_rows_yield_grade_counts(self):
        text = "\n".join([
            LOCATION_HEADER,
            "General 2-Slot1\tMote of Infinitesimal Potential\t148590\t5\t10",
            "General 2-Slot2\tMote of Minor Potential\t148591\t2\t10",
            "General 3-Slot1\tMote of Infinitesimal Potential\t148590\t1\t10",
            "Bank1\tVoid-Touched Potential\t148600\t1\t10",
            "General 4-Slot1\tWind Rune Azia\t1\t1\t10",
            # An unknown id must not become a mote. Name match only.
            "General 5-Slot1\tNot A Mote\t148600\t4\t10",
            "",
            KEYRING_HEADER,
            "Equipment\tMote of Potential\t148593",
            "Equipment\tMote of Potential\t148593",
        ])
        parsed = parse_inventory_tsv(text)
        by_grade = {row["grade"]: row for row in parsed["motes"]}
        self.assertEqual(set(by_grade), {1, 2, 4})
        self.assertEqual(by_grade[1]["name"], "Mote of Infinitesimal Potential")
        self.assertEqual(by_grade[1]["count"], 6)
        self.assertEqual(
            by_grade[1]["locations"],
            ["General 2-Slot1", "General 3-Slot1"],
        )
        self.assertEqual(by_grade[2]["count"], 2)
        self.assertEqual(by_grade[4]["name"], "Mote of Potential")
        self.assertEqual(by_grade[4]["count"], 2)
        self.assertEqual(by_grade[4]["locations"], ["Equipment"])
        self.assertEqual(parsed["void_touched"]["count"], 1)
        self.assertEqual(parsed["void_touched"]["locations"], ["Bank1"])
        self.assertEqual(parsed["wind_runes"], [{
            "name": "Wind Rune Azia",
            "count": 1,
            "locations": ["General 4-Slot1"],
        }])
        self.assertNotIn("Not A Mote", [row["name"] for row in parsed["motes"]])
        collapsed = [entry for entry in parsed["keyring"] if entry["name"] == "Mote of Potential"]
        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["count"], 2)

    def test_6_unknown_header_block_keeps_line_numbers(self):
        text = "\n".join([
            LOCATION_HEADER,
            "Head\tCloak of Flames\t1\t1\t10",
            "",
            "UnverifiedSection\tTitle\tValue",
            "Alpha\tone\t1",
            "Beta\ttwo\t2",
        ])
        parsed = parse_inventory_tsv(text)
        self.assertEqual(parsed["equipment"].get("HEAD"), "Cloak of Flames")
        self.assertEqual(
            [(row["line"], row["header_line"], row["header"], row["raw"]) for row in parsed["unknown_rows"]],
            [
                (5, 4, "UnverifiedSection\tTitle\tValue", "Alpha\tone\t1"),
                (6, 4, "UnverifiedSection\tTitle\tValue", "Beta\ttwo\t2"),
            ],
        )
        names = [row["name"] for row in parsed["all_items"]]
        self.assertNotIn("one", names)
        self.assertNotIn("two", names)
        self.assertNotIn("Alpha", [row["location_raw"] for row in parsed["rows"]])
        self.assertEqual(parsed["motes"], [])

    def test_unknown_header_mote_text_is_not_extracted(self):
        text = "\n".join([
            "UnverifiedSection\tName\tID",
            "Mote of Potential\t148593\t4",
        ])
        parsed = parse_inventory_tsv(text)
        self.assertEqual(parsed["motes"], [])
        self.assertEqual(parsed["void_touched"]["count"], 0)
        self.assertEqual(parsed["all_items"], [])
        self.assertEqual(parsed["rows"], [])
        self.assertEqual(parsed["unknown_rows"][0]["raw"], "Mote of Potential\t148593\t4")
        self.assertIn("No inventory header found", parsed["warnings"])

    def test_unknown_location_token_is_kept(self):
        text = "\n".join([
            LOCATION_HEADER,
            "NotASlot\tMystery Item\t9\t1\t10",
        ])
        parsed = parse_inventory_tsv(text)
        self.assertEqual(parsed["equipment"], {})
        self.assertEqual(len(parsed["unknown_rows"]), 1)
        self.assertEqual(parsed["unknown_rows"][0]["line"], 2)
        self.assertEqual(parsed["unknown_rows"][0]["raw"], "NotASlot\tMystery Item\t9\t1\t10")
        self.assertEqual(parsed["rows"][0]["container_kind"], "unknown")
        self.assertEqual(parsed["all_items"][0]["name"], "Mystery Item")
        self.assertEqual(parsed["all_items"][0]["reason"], "unknown location")

    def test_nested_bag_uses_the_immediate_parent_token(self):
        text = "\n".join([
            LOCATION_HEADER,
            "General 1\tBag\t1\t1\t24",
            "General 1-Slot9\tInner Bag\t2\t1\t8",
            "General 1-Slot9-Slot7\tDeep Item\t3\t1\t10",
        ])
        parsed = parse_inventory_tsv(text)
        inner = _by_name(parsed, "Inner Bag")
        deep = _by_name(parsed, "Deep Item")
        self.assertEqual(_parent_name(parsed, inner), "Bag")
        self.assertEqual(inner["socket_index"], 9)
        self.assertIsNone(inner["socket_label"])
        self.assertEqual(inner["container_kind"], "general")
        self.assertEqual(_parent_name(parsed, deep), "Inner Bag")
        self.assertEqual(deep["depth"], 2)
        self.assertEqual(deep["socket_index"], 7)
        self.assertIsNone(deep["socket_label"])

    def test_columns_are_read_by_name_and_case(self):
        text = "\n".join([
            "name\tID\tSlots\tCount\tLocation",
            "Cloak of Flames\t3001\t10\t1\tBack",
        ])
        parsed = parse_inventory_tsv(text)
        self.assertEqual(parsed["equipment"].get("BACK"), "Cloak of Flames")
        row = parsed["rows"][0]
        self.assertEqual(row["id"], "3001")
        self.assertEqual(row["count"], 1)
        self.assertEqual(row["slots"], 10)
        self.assertEqual(row["location_raw"], "Back")

    def test_header_after_tabbed_preamble_is_still_found(self):
        text = "\n".join(["preamble"] * 25 + [
            "junk\tnot a header",
            LOCATION_HEADER,
            "Back\tCloak of Flames\t1\t1\t10",
        ])
        parsed = parse_inventory_tsv(text)
        self.assertEqual(parsed["equipment"].get("BACK"), "Cloak of Flames")
        self.assertEqual(parsed["unknown_rows"], [{
            "line": 26,
            "header": "junk\tnot a header",
            "header_line": 26,
            "raw": "junk\tnot a header",
        }])
        self.assertNotIn("Name", [row["name"] for row in parsed["all_items"]])

    def test_held_is_known_and_charm_alias_still_maps(self):
        text = "\n".join([
            LOCATION_HEADER,
            "Held\tA Lamp\t1\t1\t10",
            "Charm\tCharm of the Fixture\t2\t1\t10",
        ])
        parsed = parse_inventory_tsv(text)
        held = _by_name(parsed, "A Lamp")
        self.assertEqual(held["container_kind"], "worn")
        self.assertEqual(parsed["unknown_rows"], [])
        self.assertNotIn("HELD", parsed["equipment"])
        self.assertEqual(parsed["equipment"].get("ANY1"), "Charm of the Fixture")

    def test_trailing_star_is_a_flag_and_tier_is_kept(self):
        parsed = parse_inventory_tsv(FIXTURE.read_text(encoding="utf-8"))
        hammer = _by_name(parsed, "Blued Two-Handed Hammer +5*")
        self.assertTrue(hammer["flag_star"])
        self.assertEqual(hammer["tier"], 5)
        self.assertEqual(hammer["name"], "Blued Two-Handed Hammer")
        cloak = _by_name(parsed, "Cloak of Flames +0")
        self.assertEqual(cloak["tier"], 0)
        self.assertFalse(cloak["flag_star"])
        self.assertEqual(parsed["upgrade_hints"].get("PRIMARY"), 5)

    def test_worn_equipment_map_is_unchanged_for_suggest_upgrades(self):
        parsed = parse_inventory_tsv(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(parsed["equipment"], {
            "ANY1": "Charm of the Fixture",
            "BACK": "Cloak of Flames",
            "EAR1": "Left Ear Stud",
            "EAR2": "Right Ear Stud",
            "FINGER1": "Ring of the Test Fixture",
            "FINGER2": "Ring of the Test Fixture Two",
            "HEAD": "Midnight Clad Headband",
            "PRIMARY": "Blued Two-Handed Hammer",
            "WAIST": "Flowing Black Silk Sash",
        })
        self.assertEqual(parsed["upgrade_hints"], {
            "BACK": 0,
            "EAR1": 2,
            "PRIMARY": 5,
            "WAIST": 10,
        })
        owned = {entry["name"] for entry in parsed["keyring"]}
        self.assertIn("Synthetic Spare Cap", owned)
        self.assertNotIn("Synthetic Spare Cap", parsed["equipment"].values())
        self.assertNotIn("Name", parsed["equipment"].values())
        reasons = {
            (row["location"], row["name"]): row["reason"]
            for row in parsed["all_items"]
        }
        self.assertEqual(reasons[("SharedBank1", "Shared Sample")], "shared bank")
        self.assertEqual(reasons[("Personal-Depot1", "Depot Sample")], "depot")
        self.assertEqual(reasons[("Equipment", "Synthetic Spare Cap")], "owned")
        self.assertEqual(reasons[("Activated", "Synthetic Guise +4")], "owned")
        self.assertEqual(reasons[("Augmentation", "Synthetic Stone (Exaltation)")], "owned")

    def test_unseen_bank_and_depot_indexes_stay_unknown(self):
        text = "\n".join([
            LOCATION_HEADER,
            "SharedBank7\tSeventh\t1\t1\t10",
            "Bank25\tOverflow\t2\t1\t10",
            "Personal-Depot2\tOther Depot\t3\t1\t10",
            "Personal-Depot1\tDepot Sample\t4\t1\t10",
        ])
        parsed = parse_inventory_tsv(text)
        kinds = {row["location_raw"]: row["container_kind"] for row in parsed["rows"]}
        self.assertEqual(kinds["Personal-Depot1"], "depot")
        self.assertEqual(kinds["SharedBank7"], "unknown")
        self.assertEqual(kinds["Bank25"], "unknown")
        self.assertEqual(kinds["Personal-Depot2"], "unknown")
        unknown_lines = {row["raw"].split("\t")[0] for row in parsed["unknown_rows"]}
        self.assertEqual(unknown_lines, {"SharedBank7", "Bank25", "Personal-Depot2"})

    def test_binary_payload_is_still_rejected(self):
        with self.assertRaises(ValueError):
            parse_inventory_tsv("MZ\x00this is not Inventory.txt")

    def test_import_route_returns_the_snapshot_fields(self):
        client = TestClient(app)
        body = "\n".join([
            LOCATION_HEADER,
            "Back\tCloak of Flames\t1\t1\t10",
            "General 1-Slot1\tMote of Minor Potential\t148591\t3\t10",
            "",
            KEYRING_HEADER,
            "Equipment\tSynthetic Spare Cap\t1001",
        ])
        response = client.post("/api/inventory/import", json={"text": body})
        self.assertEqual(response.status_code, 200, response.text[:500])
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["equipment"].get("BACK"), "Cloak of Flames")
        self.assertEqual(payload["motes"], [{
            "grade": 2,
            "name": "Mote of Minor Potential",
            "count": 3,
            "locations": ["General 1-Slot1"],
        }])
        self.assertEqual(payload["keyring"], [{
            "ring": "Equipment",
            "name": "Synthetic Spare Cap",
            "id": "1001",
            "count": 1,
        }])
        self.assertEqual(payload["unknown_rows"], [])
        self.assertGreaterEqual(len(payload["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
