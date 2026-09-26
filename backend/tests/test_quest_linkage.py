"""Item Search quest labels must resolve to a real Quest Hub entry.

Loads the shipped item related-quest snapshot, Plane of Sky table, and the
decoded catalog. A listed quest that does not resolve has to be named in
fixtures/quest_linkage_allowlist.json with a reason.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.item_catalog import _catalog_reward_quests_by_item, _quests_payload_for_item  # noqa: E402
from app.quest_links import (  # noqa: E402
    PACKAGED_DATA_FILES,
    data_path,
    parse_related_quest_wikitext,
    parse_related_quests_from_item_html,
    pos_tests,
    quest_name_key,
    resolve_quest_label,
    resolve_quest_link,
)

ALLOWLIST = Path(__file__).resolve().parent / "fixtures" / "quest_linkage_allowlist.json"
WOVEN_HTML = Path(__file__).resolve().parent / "fixtures" / "woven_skull_cap_related.html"

BLACK_TEAR_WIKITEXT = """
|relatedquests =
<ul><li>  [[Request of the Arcane]] -- {{:Mask of the Silver Eyes}}
* [[Black Tear]]
* [[White Tear]]
* [[Runed Tear]]
</li><li> [[The Second Arcane Test]] -- {{:Boots of Deep Thought}}
* [[Ruby Tear]]
* [[Black Tear]]
</li><li> [[Test of the Living Flame]] -- {{:Earring of the Living Flame}}
* [[Black Tear]]
* [[Black Symbol]]
</li></ul>
}}
"""


def _allow_pairs() -> set[tuple[str, str]]:
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    pairs = set()
    for entry in data["entries"]:
        pairs.add((entry["name"], entry.get("page") or ""))
    return pairs


def _listed_unresolved(item_name: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for row in _quests_payload_for_item(item_name):
        if row.get("in_hub"):
            continue
        out.add(((row.get("name") or "").strip(), (row.get("page") or "") or ""))
    return out


class QuestLinkageTests(unittest.TestCase):
    def test_woven_skull_cap_resolves_to_wizard_test_of_focus(self):
        rows = _quests_payload_for_item("Woven Skull Cap")
        focus = [row for row in rows if row.get("name") == "Wizard Test of Focus"]
        self.assertEqual(len(focus), 1)
        self.assertTrue(focus[0]["in_hub"])
        self.assertNotIn("Plane of Sky", [row.get("name") for row in rows])
        self.assertFalse(any(row.get("in_hub") is False for row in rows))

    def test_woven_html_uses_visible_quest_name(self):
        links = parse_related_quests_from_item_html(WOVEN_HTML.read_text(encoding="utf-8"))
        self.assertEqual(links, [{"name": "Wizard Test of Focus", "page": "Plane of Sky"}])

    def test_nested_component_links_are_not_quests(self):
        links = parse_related_quest_wikitext(BLACK_TEAR_WIKITEXT)
        names = [link["name"] for link in links]
        self.assertEqual(
            names,
            ["Request of the Arcane", "The Second Arcane Test", "Test of the Living Flame"],
        )

    def test_plane_of_sky_table_has_95_tests(self):
        tests = pos_tests()
        self.assertEqual(len(tests), 95)
        wizard = next(row for row in tests if row["quest"] == "Wizard Test of Focus")
        self.assertEqual(wizard["giver"], "Wizard Schrock")
        self.assertEqual(wizard["keyword"], "focus")
        self.assertEqual(wizard["reward"], "Al`Kabor's Cap of Binding")
        self.assertEqual(wizard["runes"], ["Wind Rune Fana"])
        self.assertEqual(wizard["items"], [{"name": "Woven Skull Cap", "tag": "4-KoS"}])
        self.assertEqual(wizard["class"], "Wizard")

    def test_every_pos_component_and_reward_resolves_to_its_test(self):
        for test in pos_tests():
            quest = test["quest"]
            self.assertEqual(quest_name_key(resolve_quest_label(quest, loose=False)), quest_name_key(quest))
            names = [test.get("reward") or ""]
            for item in test.get("items") or []:
                names.append(item.get("name") if isinstance(item, dict) else item)
            for alias in test.get("aliases") or []:
                self.assertEqual(quest_name_key(resolve_quest_label(alias, loose=False)), quest_name_key(quest))
            for name in names:
                if not name:
                    continue
                rows = _quests_payload_for_item(name)
                matched = [
                    row for row in rows
                    if row.get("in_hub") and quest_name_key(row.get("name") or "") == quest_name_key(quest)
                ]
                self.assertTrue(matched, f"{name} did not list {quest}")

    def test_catalog_reward_quests_resolve(self):
        seen: set[str] = set()
        for names in _catalog_reward_quests_by_item().values():
            for name in names:
                if name in seen:
                    continue
                seen.add(name)
                self.assertIsNotNone(
                    resolve_quest_label(name, loose=False),
                    f"catalog reward quest {name!r} is not in Quest Hub",
                )
        self.assertGreater(len(seen), 0)

    def test_every_listed_quest_resolves_or_is_allowlisted(self):
        from app.paths import decoded_dir

        item_names: set[str] = set()
        related_path = data_path("eqlwiki_item_related_quests.json")
        self.assertIsNotNone(related_path)
        related = json.loads(related_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
        item_names.update(related.get("items") or {})
        for test in pos_tests():
            if test.get("reward"):
                item_names.add(test["reward"])
            for item in test.get("items") or []:
                item_names.add(item.get("name") if isinstance(item, dict) else item)
        catalog = json.loads((decoded_dir() / "catalog.json").read_text(encoding="utf-8"))
        for kind in (
            "tooltips",
            "focusItemTooltips",
            "clickyItemTooltips",
            "wornItemTooltips",
            "procItemTooltips",
        ):
            for tip in (catalog.get(kind) or {}).values():
                if isinstance(tip, dict) and tip.get("rewardFromQuests") and tip.get("name"):
                    item_names.add(tip["name"])

        unresolved: set[tuple[str, str]] = set()
        for name in item_names:
            if name:
                unresolved |= _listed_unresolved(name)
        allow = _allow_pairs()
        self.assertEqual(
            unresolved,
            allow,
            f"only in data: {sorted(unresolved - allow)[:8]}; only in allowlist: {sorted(allow - unresolved)[:8]}",
        )
        listed = json.loads(ALLOWLIST.read_text(encoding="utf-8"))["entries"]
        self.assertLessEqual(len(listed), 40)
        for entry in listed:
            self.assertTrue(str(entry.get("reason") or "").strip())
            self.assertIsNone(
                resolve_quest_link(entry["name"], entry.get("page") or ""),
                entry["name"],
            )

    def test_packaging_copies_quest_data(self):
        bundle = (ROOT / "scripts" / "bundle_desktop_resources.py").read_text(encoding="utf-8")
        for name in PACKAGED_DATA_FILES:
            self.assertIn(name, bundle)
            path = data_path(name)
            self.assertIsNotNone(path, name)
            assert path is not None
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 100)
        self.assertTrue((ROOT / "backend" / "app" / "quest_links.py").is_file())


if __name__ == "__main__":
    unittest.main()
