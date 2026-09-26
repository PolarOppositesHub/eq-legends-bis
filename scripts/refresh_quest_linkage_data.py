#!/usr/bin/env python3
"""Refresh Plane of Sky tests, eqlwiki quest titles, and item related-quest links.

Sources (CC BY-SA), never invented:
  https://eqlwiki.com/Plane_of_Sky
  https://eqlwiki.com/Category:Quests
  https://eqlwiki.com/Category:Quest_Items  (item page relatedquests fields)

Writes:
  data/pos_class_tests.json
  data/eqlwiki_quest_names.json
  data/eqlwiki_item_related_quests.json
  backend/tests/fixtures/quest_linkage_allowlist.json
  data/quest_linkage_audit.json
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.quest_links import (  # noqa: E402
    item_name_key,
    parse_related_quest_wikitext,
    quest_name_key,
)

DATA = ROOT / "data"
API = "https://eqlwiki.com/api.php"
UA = "EQ-Legends-BiS/1.1.1 (quest-linkage refresh; local)"
CLASS_SECTIONS = (
    "Bard",
    "Beastlord",
    "Berserker",
    "Cleric",
    "Druid",
    "Enchanter",
    "Magician",
    "Monk",
    "Necromancer",
    "Paladin",
    "Ranger",
    "Rogue",
    "Shadow_Knight",
    "Shaman",
    "Warrior",
    "Wizard",
)


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"eqlwiki API failed: {last}")


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def textify(fragment: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragment or "")
    t = htmllib.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def parse_pos_tests(html: str) -> list[dict]:
    """Class-test rows from the Plane of Sky page. Stops at the next heading."""
    raw = re.sub(r'<span class="hb">[\s\S]*?</span>', "", html or "", flags=re.I)
    ids = "|".join(CLASS_SECTIONS)
    parts = re.split(rf'<h3[^>]*id="((?:{ids})_Tests)"[^>]*>', raw)
    tests: list[dict] = []
    for i in range(1, len(parts), 2):
        section_id = parts[i]
        body = re.split(r"<h[23]\b", parts[i + 1], maxsplit=1)[0]
        giver_m = re.search(
            r"Quest Giver:\s*</b>\s*(?:<a[^>]*>)?([^<]+)",
            body,
            re.I,
        )
        giver = htmllib.unescape(giver_m.group(1)).strip() if giver_m else ""
        class_name = section_id.replace("_Tests", "").replace("_", " ")
        section = f"{class_name} Tests"
        for row in re.findall(r"<tr>([\s\S]*?)</tr>", body):
            if "<th>" in row:
                continue
            cells = re.findall(r"<td>([\s\S]*?)</td>", row)
            if len(cells) < 5:
                continue
            reward_m = re.search(r"<a[^>]*>([^<]+)</a>", cells[0])
            reward = htmllib.unescape(reward_m.group(1)).strip() if reward_m else textify(cells[0])
            quest = textify(cells[1])
            keyword = textify(cells[2])
            runes = [
                htmllib.unescape(x).strip()
                for x in re.findall(r"<a[^>]*>([^<]+)</a>", cells[3])
            ]
            runes = [r for r in runes if r]
            if not quest or not runes:
                continue
            items = []
            for li in re.findall(r"<li[^>]*>([\s\S]*?)</li>", cells[4]):
                im = re.search(r"<a[^>]*>([^<]+)</a>", li)
                iname = htmllib.unescape(im.group(1)).strip() if im else textify(li)
                if not iname:
                    continue
                tag_m = re.search(r"\(([^)]+)\)\s*$", textify(li))
                items.append({
                    "name": iname,
                    "tag": tag_m.group(1).strip() if tag_m else "",
                })
            tests.append({
                "class": class_name,
                "section": section,
                "quest": quest,
                "giver": giver,
                "keyword": keyword,
                "reward": reward,
                "runes": runes,
                "items": items,
                "aliases": [],
            })
    return tests


def fetch_category_quests() -> list[str]:
    titles: list[str] = []
    cont = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:Quests",
            "cmnamespace": "0",
            "cmtype": "page",
            "cmlimit": "500",
            "format": "json",
        }
        if cont:
            params["cmcontinue"] = cont
        data = api(params)
        for member in (data.get("query") or {}).get("categorymembers") or []:
            title = (member.get("title") or "").strip()
            if title:
                titles.append(title)
        cont = (data.get("continue") or {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(0.1)
    # Preserve order, drop dupes.
    seen: set[str] = set()
    out: list[str] = []
    for title in titles:
        key = quest_name_key(title)
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
    return out


def fetch_quest_item_wikitext() -> list[dict]:
    rows: list[dict] = []
    cont = None
    while True:
        params = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": "Category:Quest Items",
            "gcmnamespace": "0",
            "gcmlimit": "50",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
            "formatversion": "2",
        }
        if cont:
            params.update(cont)
        data = api(params)
        for page in (data.get("query") or {}).get("pages") or []:
            revs = page.get("revisions") or []
            content = ""
            if revs:
                slots = (revs[0].get("slots") or {}).get("main") or {}
                content = slots.get("content") or slots.get("*") or ""
            rows.append({"title": page.get("title") or "", "wikitext": content})
        print(f"  quest items {len(rows)}", flush=True)
        cont = data.get("continue")
        if not cont:
            break
        time.sleep(0.12)
    return rows


def page_categories(titles: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        data = api({
            "action": "query",
            "prop": "categories",
            "cllimit": "50",
            "titles": "|".join(chunk),
            "format": "json",
            "redirects": "1",
        })
        pages = (data.get("query") or {}).get("pages") or {}
        if isinstance(pages, dict):
            page_list = list(pages.values())
        elif isinstance(pages, list):
            page_list = pages
        else:
            page_list = []
        for page in page_list:
            if not isinstance(page, dict):
                continue
            title = page.get("title") or ""
            cats = [
                (c.get("title") or "").replace("Category:", "")
                for c in (page.get("categories") or [])
            ]
            if title:
                out[title] = cats
        time.sleep(0.1)
    return out


def catalog_test_names_by_reward(decoded: Path) -> dict[str, set[str]]:
    """reward item key → catalog quest names that contain 'test of'."""
    out: dict[str, set[str]] = defaultdict(set)
    catalog_path = decoded / "catalog.json"
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if isinstance(catalog, dict):
            for kind in (
                "tooltips",
                "focusItemTooltips",
                "clickyItemTooltips",
                "wornItemTooltips",
                "procItemTooltips",
            ):
                tip_map = catalog.get(kind) or {}
                if not isinstance(tip_map, dict):
                    continue
                for tip in tip_map.values():
                    if not isinstance(tip, dict):
                        continue
                    item = (tip.get("name") or "").strip()
                    for q in tip.get("rewardFromQuests") or []:
                        if isinstance(q, str) and "test of" in q.lower():
                            out[item_name_key(item)].add(q.strip())
    for path in sorted(decoded.glob("flat_*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = (row.get("name") or "").strip()
            for fld in ("quest_source", "source"):
                val = row.get(fld)
                if not isinstance(val, str):
                    continue
                # "Reward from Plane of Sky Quest: Wizard Test of Focus"
                m = re.search(r"quest:\s*(.+)$", val, re.I)
                title = m.group(1).strip() if m else ""
                if title and "test of" in title.lower():
                    out[item_name_key(item)].add(title)
    return out


def load_item_name_keys(decoded: Path) -> set[str]:
    path = decoded / "eqlwiki_item_names.json"
    if not path.is_file():
        path = ROOT / "packaging" / "required-decoded" / "eqlwiki_item_names.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    names = data.get("names") if isinstance(data, dict) else []
    return {item_name_key(n) for n in names if isinstance(n, str)}


def wiki_url(page: str) -> str:
    return "https://eqlwiki.com/" + urllib.parse.quote((page or "").replace(" ", "_"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pos-html", type=Path, help="Saved Plane of Sky HTML")
    parser.add_argument("--categories-json", type=Path, help="JSON list of Category:Quests titles")
    parser.add_argument("--wikitext-jsonl", type=Path, help="Quest item wikitext jsonl")
    parser.add_argument("--skip-category-probe", action="store_true")
    parser.add_argument(
        "--reports-only",
        action="store_true",
        help="Rebuild the allowlist and audit from the JSON already in data/",
    )
    args = parser.parse_args()
    if args.reports_only:
        return write_linkage_reports()

    if args.pos_html:
        pos_html = args.pos_html.read_text(encoding="utf-8")
    else:
        print("fetch Plane of Sky")
        pos_html = fetch_text("https://eqlwiki.com/Plane_of_Sky")
    tests = parse_pos_tests(pos_html)
    print(f"parsed {len(tests)} Plane of Sky class tests")
    if len(tests) != 95:
        print("ERROR: expected 95 Plane of Sky class tests", file=sys.stderr)
        return 1

    if args.categories_json:
        category_titles = json.loads(args.categories_json.read_text(encoding="utf-8"))
    else:
        print("fetch Category:Quests")
        category_titles = fetch_category_quests()
    print(f"category quests {len(category_titles)}")

    if args.wikitext_jsonl:
        pages = [json.loads(line) for line in args.wikitext_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        print("fetch Category:Quest Items wikitext")
        pages = fetch_quest_item_wikitext()

    decoded = ROOT / "desktop" / "resources" / "data" / "decoded"
    if not (decoded / "catalog.json").is_file():
        decoded = ROOT / "data" / "decoded"
    reward_quests = catalog_test_names_by_reward(decoded)
    item_keys = load_item_name_keys(decoded)

    by_quest = {quest_name_key(t["quest"]): t for t in tests}
    # Catalog spelling → wiki test, only when the reward item has exactly one
    # "test of" quest name (same reward proves it is the same test).
    for test in tests:
        names = reward_quests.get(item_name_key(test["reward"]), set())
        specific = {n for n in names if "test of" in n.lower()}
        if len(specific) != 1:
            continue
        only = next(iter(specific))
        if quest_name_key(only) == quest_name_key(test["quest"]):
            continue
        if quest_name_key(only) in by_quest:
            continue
        test["aliases"].append(only)

    related: dict[str, list[dict[str, str]]] = {}
    for page in pages:
        title = (page.get("title") or "").strip()
        links = parse_related_quest_wikitext(page.get("wikitext") or "")
        if title and links:
            related[title] = links

    # Item-page label → the one Plane of Sky test that lists that item.
    tests_by_item: dict[str, list[dict]] = defaultdict(list)
    for test in tests:
        keys = [item_name_key(test["reward"])]
        keys.extend(item_name_key(it["name"]) for it in test["items"])
        for key in keys:
            if key:
                tests_by_item[key].append(test)
    for item, links in related.items():
        owned = tests_by_item.get(item_name_key(item)) or []
        if len(owned) != 1:
            continue
        test = owned[0]
        for link in links:
            page_name = link["page"]
            skyish = quest_name_key(page_name) == "plane of sky" or page_name.lower().endswith("plane of sky tests")
            if not skyish:
                continue
            label = link["name"]
            if quest_name_key(label) == quest_name_key(test["quest"]):
                continue
            if quest_name_key(label) in by_quest:
                continue
            if any(quest_name_key(a) == quest_name_key(label) for a in test["aliases"]):
                continue
            test["aliases"].append(label)

    known = {quest_name_key(t["quest"]) for t in tests}
    known.update(quest_name_key(a) for t in tests for a in t["aliases"])
    known.update(quest_name_key(n) for n in category_titles)

    def resolves(name: str) -> bool:
        return quest_name_key(name) in known

    unresolved_links: list[tuple[str, str, str]] = []
    for item, links in related.items():
        for link in links:
            if resolves(link["name"]) or resolves(link["page"]):
                continue
            unresolved_links.append((item, link["name"], link["page"]))

    extra_records: list[dict] = []
    extra_keys: set[str] = set()
    probe_pages = sorted({page for _item, _name, page in unresolved_links})
    cats_by_page: dict[str, list[str]] = {}
    if probe_pages and not args.skip_category_probe:
        print(f"probe categories for {len(probe_pages)} unresolved pages")
        cats_by_page = page_categories(probe_pages)

    def add_extra(name: str, page: str, source: str) -> None:
        key = quest_name_key(name)
        if not key or key in known or key in extra_keys:
            return
        if key in item_keys and "quest" not in name.lower() and "test" not in name.lower():
            return
        extra_keys.add(key)
        known.add(key)
        extra_records.append({
            "name": name,
            "url": wiki_url(page or name),
            "source": source,
        })

    for item, name, page in unresolved_links:
        cats = cats_by_page.get(page) or cats_by_page.get(name) or []
        if any(c == "Quests" or c.endswith(" Quests") for c in cats):
            add_extra(name, page, "eqlwiki page categories include Quests")
            continue
        if quest_name_key(page) in item_keys or quest_name_key(name) in item_keys:
            continue
        if "quest" in name.lower() or "test" in name.lower() or "quest" in page.lower():
            add_extra(name, page, "eqlwiki item related-quest link")

    quest_records = [
        {
            "name": title,
            "url": wiki_url(title),
            "source": "eqlwiki Category:Quests",
        }
        for title in category_titles
    ]
    quest_records.extend(extra_records)

    pos_doc = {
        "license": "CC BY-SA",
        "attribution": (
            "Plane of Sky class tests transcribed from the EverQuest Legends Wiki "
            "(https://eqlwiki.com/Plane_of_Sky), used under CC BY-SA. Quest names, "
            "givers, trigger phrases, wind runes, required items, island tags, and "
            "reward items are copied from that page's class-test tables. "
            "Aliases are catalog spellings or item-page labels for the same reward "
            "or the same required item — not invented quests."
        ),
        "source_url": "https://eqlwiki.com/Plane_of_Sky",
        "fetched": "2026-09-26",
        "test_count": len(tests),
        "tests": tests,
    }
    names_doc = {
        "license": "CC BY-SA",
        "attribution": (
            "Quest titles from the EverQuest Legends Wiki Category:Quests "
            "(https://eqlwiki.com/Category:Quests) and from item-page related-quest "
            "links whose target is categorized as a quest, used under CC BY-SA. "
            "Names and URLs only — rewards, givers, and steps are not invented."
        ),
        "source_url": "https://eqlwiki.com/Category:Quests",
        "fetched": "2026-09-26",
        "quest_count": len(quest_records),
        "quests": quest_records,
    }
    links_doc = {
        "license": "CC BY-SA",
        "attribution": (
            "Top-level Related quests links from EverQuest Legends Wiki item pages "
            "in Category:Quest Items (https://eqlwiki.com/Category:Quest_Items), "
            "used under CC BY-SA. The piped label is the quest name; the page title "
            "is kept so section links such as Plane of Sky#Wizard Tests can fall "
            "back to a hub quest. Nested component and NPC links are not included."
        ),
        "source_url": "https://eqlwiki.com/Category:Quest_Items",
        "fetched": "2026-09-26",
        "item_count": len(related),
        "items": related,
    }

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "pos_class_tests.json").write_text(
        json.dumps(pos_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (DATA / "eqlwiki_quest_names.json").write_text(
        json.dumps(names_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (DATA / "eqlwiki_item_related_quests.json").write_text(
        json.dumps(links_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("wrote quest data files")
    return write_linkage_reports()


# Labels that still do not resolve. Reasons name the hub titles that were
# considered and rejected so a later pass does not "fix" them by guessing.
_UNRESOLVED_REASONS = {
    "Cazic Thule Disciple": (
        "Not an eqlwiki Category:Quests title and not a Plane of Sky class test. "
        "No Quest Hub row uses this name. Left unresolved."
    ),
    "Cazic Thule Initiate": (
        "Not an eqlwiki Category:Quests title and not a Plane of Sky class test. "
        "No Quest Hub row uses this name. Left unresolved."
    ),
    "Child of Innoruuk": (
        "Not in Category:Quests. Other Innoruuk quests are in the hub "
        "(Innoruuk Recommendation, Innoruuk Symbol Quests) but this title is not, "
        "so it was not aliased."
    ),
    "Dark One's Armor": (
        "Not in Category:Quests. Quest Hub has Guild Summons - Dark Ones, which is "
        "a different title, so the armor name was not turned into a quest."
    ),
    "Faydark Champions Long Sword": (
        "The related-quest link points at an item page. Quest Hub has "
        "Guild Summons - Faydark's Champions, a different title, so this was not aliased."
    ),
    "Fishing": (
        "The link target is the skill page Skill Fishing, not a quest. Left unresolved."
    ),
    "Fresh Baked Muffins": (
        "Ambiguous. Quest Hub has both Fresh Baked Muffins (Kaladim) and "
        "Fresh Baked Muffins (Qeynos). The link does not say which, so it was not guessed."
    ),
    "Guild Summons - Shrine of Bertoxxulous Cleric": (
        "Not in Category:Quests. The closest hub title is Guild Summons - Temple of "
        "Bertoxxulous Cleric (Temple, not Shrine). Other Shrine of Bertoxxulous "
        "classes are listed, but not Cleric. Not aliased."
    ),
    "Illegible Scroll": (
        "The link points at an item page. Quest Hub has Illegible Scrolls and "
        "Illegible Scrolls (Felwithe), which are plural and two different pages. Not guessed."
    ),
    "Magician Spells (Good Version)": (
        "Not in Category:Quests. Magician Spells (Good), Magician Spells (Evil), and "
        "Magician Spells (Evil Version) are separate hub pages, so dropping the word "
        "Version would be a guess."
    ),
    "McMannus Clan Dagger": (
        "The link points at an item page. McMannus Revenge and Ivan McMannus' Remains "
        "are different hub quests. Not aliased."
    ),
    "Nalla's Problem": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
    "Necromancer Spells": (
        "Ambiguous. Both Necromancer Spells (Cabilis) and Quest:Necromancer Spells "
        "fold to this label. Not guessed."
    ),
    "Necromancer Words": (
        "Ambiguous. Quest Hub has Necromancer Words - X`Ta Tempi, X`Ta Timpi, and "
        "X`Ta Tompi. The link does not say which."
    ),
    "Purple Headband": (
        "The related-quest link points at an item page, not a Category:Quests title. "
        "Left unresolved."
    ),
    "Scaled Curskins": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
    "Scarab Boots": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
    "Shackle of Bronze": (
        "The related-quest link points at an item page, not a Category:Quests title. "
        "Left unresolved."
    ),
    "Shackle of Rock": (
        "The related-quest link points at an item page, not a Category:Quests title. "
        "Left unresolved."
    ),
    "Shackle of Scale": (
        "Not in Category:Quests. Monk Shackle Quests is a different hub title. Not aliased."
    ),
    "Spirit of Golin": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
    "Spiritcharmer Final Job": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
    "The Cracking of the Icestar": (
        "Not in Category:Quests. The Icestar Dims, The Icestar Remembers, and "
        "Icestar's Eve Snowdrift Feast are different hub titles. Not aliased."
    ),
    "The Escaped Catman": (
        "Not in Category:Quests. Catman Alliance is a different hub title. Not aliased."
    ),
    "The Pirate Ship": (
        "Not in Category:Quests. Pirate Earrings is a different hub title. Not aliased."
    ),
    "The Summoning of Fear": (
        "Not in Category:Quests. The Summoning of Dread, Fright, and Terror are "
        "different quests. Fear was not aliased to any of them."
    ),
    "Trumpy's Skull": (
        "Not in Category:Quests. Trumpy's Head, Trumpy Irontoe, and Honey Mead for "
        "Trumpy are different titles. Not aliased."
    ),
    "Tunarean Tasks": (
        "Not in Category:Quests. Tunare quests in the hub use other titles "
        "(Friend of the Tunarean Court, Tunare Symbol Quests, and others). Not aliased."
    ),
    "Upgraded Pelts": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
    "What Happened Here?": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
    "Wolf Meat for Wista": (
        "Not in Category:Quests and not a Plane of Sky class test. No Quest Hub title "
        "matches this label. Left unresolved."
    ),
}
_TASKMASTER_REASON = (
    "Not in Category:Quests. Quest Hub has a single Taskmaster Earring page, not "
    "this race and gender title. The six earring links were not collapsed into that one page."
)
for _piece in (
    "Dwarf Female",
    "Dwarf Male",
    "High Elf Female",
    "High Elf Male",
    "Wood Elf Female",
    "Wood Elf Male",
):
    _UNRESOLVED_REASONS[f"Taskmaster Earring - {_piece}"] = _TASKMASTER_REASON


def _catalog_only_hub() -> dict[str, str]:
    """Quest titles from decoded catalog / flat files, before wiki rows are merged."""
    from app.item_catalog import _name_key
    from app.paths import decoded_dir
    from app.quest_hub import _add_quest
    import app.quest_guides as qg

    by_key: dict[str, dict] = {}
    decoded = decoded_dir()
    cat_path = decoded / "catalog.json"
    if cat_path.is_file():
        catalog = json.loads(cat_path.read_text(encoding="utf-8"))
        if isinstance(catalog, dict):
            for kind in (
                "tooltips",
                "focusItemTooltips",
                "clickyItemTooltips",
                "wornItemTooltips",
                "procItemTooltips",
            ):
                tip_map = catalog.get(kind) or {}
                if not isinstance(tip_map, dict):
                    continue
                for tip in tip_map.values():
                    if not isinstance(tip, dict):
                        continue
                    item = (tip.get("name") or "").strip() or None
                    for q in tip.get("rewardFromQuests") or []:
                        if isinstance(q, str):
                            _add_quest(by_key, q, item=item)
    for path in sorted(decoded.glob("flat_*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = (row.get("name") or "").strip() or None
            for fld in ("quest_source", "source", "quest_source_raw"):
                val = row.get(fld)
                if isinstance(val, str) and val.strip():
                    qn = qg.quest_name_from_source(val)
                    if qn:
                        _add_quest(by_key, qn, item=item)
    return {_name_key(row["name"]): row["name"] for row in by_key.values() if row.get("name")}


def _old_hub_hit(label: str, hub: dict[str, str]) -> str | None:
    """Match the pre-fix Item Search rule: exact catalog key, or a trailing Quests strip."""
    from app.item_catalog import _name_key

    if not label:
        return None
    key = _name_key(label)
    if key in hub:
        return hub[key]
    if key.endswith(" quests"):
        base = label
        for suffix in (" Quests", " Quest", " quests", " quest"):
            if label.endswith(suffix):
                base = label[: -len(suffix)].strip()
                break
        return hub.get(_name_key(base))
    return None


def write_linkage_reports() -> int:
    """Allowlist and audit using the same resolver Item Search uses."""
    from app.item_catalog import _name_key, _wiki_display_names
    from app.quest_hub import list_quests
    from app.quest_links import (
        clear_data_caches,
        pos_tests,
        quest_name_key,
        resolve_quest_label,
        resolve_quest_link,
    )

    list_quests.cache_clear()
    clear_data_caches()

    related = json.loads((DATA / "eqlwiki_item_related_quests.json").read_text(encoding="utf-8"))
    items = related.get("items") or {}
    old_hub = _catalog_only_hub()
    rows = list_quests()
    by_name = {row["name"]: row for row in rows}
    old_canons: set[str] = set()
    for name in old_hub.values():
        hit = resolve_quest_label(name, loose=False)
        if hit:
            old_canons.add(hit)
    item_names = set(_wiki_display_names())

    unresolved: dict[tuple[str, str], list[str]] = defaultdict(list)
    previously: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item, links in items.items():
        if not isinstance(links, list):
            continue
        for link in links:
            if not isinstance(link, dict):
                continue
            name = str(link.get("name") or "").strip()
            page = str(link.get("page") or "").strip()
            if not name and not page:
                continue
            shown_old = page or name
            if not _old_hub_hit(shown_old, old_hub):
                previously[(name, page)].append(item)
            if not resolve_quest_link(name, page):
                unresolved[(name, page)].append(item)

    allow_entries = []
    for (name, page), item_list in sorted(unresolved.items(), key=lambda kv: kv[0][0].lower()):
        reason = _UNRESOLVED_REASONS.get(name)
        if not reason:
            if _name_key(name) in item_names or _name_key(page) in item_names:
                reason = (
                    "eqlwiki related-quest link points at an item page, not a quest. "
                    "Left unresolved rather than adding an item name to Quest Hub."
                )
            else:
                reason = (
                    "Not in eqlwiki Category:Quests and not a Plane of Sky class test. "
                    "No Quest Hub title matches this label. Left unresolved."
                )
        allow_entries.append({
            "name": name,
            "page": page,
            "item_count": len(item_list),
            "items": item_list,
            "reason": reason,
        })

    cause_counts: Counter[str] = Counter()
    fixes = []
    for (name, page), item_list in sorted(previously.items(), key=lambda kv: kv[0][0].lower()):
        resolved = resolve_quest_link(name, page)
        if not resolved:
            cause = "still unresolved"
            fix = _UNRESOLVED_REASONS.get(name) or "Left unresolved. See the allowlist reason."
        else:
            row = by_name.get(resolved) or {}
            source = row.get("source") or "catalog"
            existed = resolved in old_canons
            page_differs = bool(page) and quest_name_key(page) != quest_name_key(name)
            spelling = quest_name_key(name) != quest_name_key(resolved)
            if page_differs and not _old_hub_hit(page, old_hub) and existed:
                cause = "parser used the wiki link title instead of the visible quest name"
                fix = (
                    f"Read the visible label. It resolves to {resolved}, "
                    "which was already in Quest Hub."
                )
            elif page_differs and not existed:
                cause = "parser used the wiki link title, and the quest was missing from Quest Hub"
                fix = f"Read the visible label and add {resolved} from eqlwiki ({source})."
            elif spelling and existed:
                cause = "quest title spelling differed from the Quest Hub name"
                fix = f"Resolve the label onto the existing hub title {resolved}."
            elif not existed:
                cause = "quest was missing from the catalog-only Quest Hub"
                fix = f"Added {resolved} from eqlwiki ({source})."
                if spelling:
                    fix += f" The item's label {name!r} is matched onto that title."
            else:
                cause = "quest title now matches a Quest Hub entry"
                fix = f"Resolves to {resolved}."
        cause_counts[cause] += len(item_list)
        fixes.append({
            "name": name,
            "page": page,
            "item_count": len(item_list),
            "items": item_list,
            "resolves_to": resolved,
            "cause": cause,
            "fix": fix,
        })

    pos_rows = []
    for test in pos_tests():
        quest = test["quest"]
        resolved = resolve_quest_label(quest, loose=False)
        existed = resolved in old_canons if resolved else False
        aliases = list(test.get("aliases") or [])
        if existed and aliases:
            cause = "catalog spelling differed from the Plane of Sky table"
            fix = f"Hub title is the wiki table name {quest}; catalog spelling kept as an alias."
        elif existed:
            cause = "already in the catalog Quest Hub"
            fix = "Visible test name already matched a hub quest. The page-title parser no longer replaces it with Plane of Sky."
        else:
            cause = "Plane of Sky class test was missing from Quest Hub"
            fix = "Added from the eqlwiki Plane of Sky class-test table (CC BY-SA)."
        pos_rows.append({
            "quest": quest,
            "class": test.get("class"),
            "giver": test.get("giver"),
            "keyword": test.get("keyword"),
            "reward": test.get("reward"),
            "aliases": aliases,
            "existed_in_catalog_hub": existed,
            "cause": cause,
            "fix": fix,
        })

    woven = next(t for t in pos_tests() if t["quest"] == "Wizard Test of Focus")
    summary = {
        "pos_tests": len(pos_rows),
        "catalog_only_hub_quests": len(old_hub),
        "quest_hub_after_fix": len(rows),
        "items_with_related_quests": len(items),
        "previously_unresolved_labels": len(fixes),
        "previously_unresolved_items": len({i for f in fixes for i in f["items"]}),
        "fixed_labels": sum(1 for f in fixes if f["resolves_to"]),
        "still_unresolved_labels": len(allow_entries),
        "cause_item_counts": dict(cause_counts),
        "woven_skull_cap": {
            "item": "Woven Skull Cap",
            "old_panel": "Plane of Sky · not in Quest Hub",
            "quest": woven["quest"],
            "giver": woven["giver"],
            "keyword": woven["keyword"],
            "reward": woven["reward"],
            "cause": "The related-quest link is Plane of Sky#Wizard Tests with visible text Wizard Test of Focus. Item Search stored the link title Plane of Sky.",
            "fix": "Store the visible label. Wizard Test of Focus was already a catalog quest (reward Al`Kabor's Cap of Binding) and is the wiki table name.",
        },
    }
    audit = {
        "summary": summary,
        "pos_tests": pos_rows,
        "previously_unresolved": fixes,
        "unresolved": allow_entries,
    }
    allow_path = ROOT / "backend" / "tests" / "fixtures" / "quest_linkage_allowlist.json"
    allow_path.parent.mkdir(parents=True, exist_ok=True)
    allow_path.write_text(
        json.dumps(
            {
                "note": (
                    "Item Search still lists these related-quest labels, and they do "
                    "not resolve to a Quest Hub entry. Each reason says why no quest "
                    "record was added. The regression test fails if this set drifts."
                ),
                "entries": allow_entries,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (DATA / "quest_linkage_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"wrote {allow_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
