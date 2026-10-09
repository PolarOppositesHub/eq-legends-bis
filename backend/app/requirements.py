"""Requirement tracker: mote paths and Plane of Sky progress. SPEC §9.

Holdings come from the currency ledger. Turn-in items come from the
inventory names the caller already imported. Completed tests come from
an achievements dump, then from verified offer lines, then from a
manual tick. A manual tick wins.
"""
from __future__ import annotations

import re
from typing import Any

from .achievements import achievement_test_status
from .currencies import VOID_TOUCHED_NAME, get_book
from .item_names import names_match
from .quest_links import pos_tests
from .upgrade_path import copies_for_item, plan_upgrades

# SPEC §5.1. The same shape the log classifier already accepts.
_OFFER = re.compile(r"^You offered (?P<qty>[\d,]+) (?P<item>.+) to (?P<npc>.+)\.?$")
_LOG_PREFIX = re.compile(r"^\[[^\]]+\]\s*")


def parse_offer_line(line: str) -> dict[str, Any] | None:
    """One verified turn-in line, with or without the log timestamp prefix."""
    message = _LOG_PREFIX.sub("", (line or "").strip())
    match = _OFFER.match(message)
    if not match:
        return None
    qty_text = match.group("qty").replace(",", "")
    try:
        qty = int(qty_text)
    except ValueError:
        return None
    return {
        "qty": qty,
        "item": match.group("item").strip(),
        "npc": match.group("npc").strip().rstrip("."),
    }


def offers_from_text(text: str) -> list[dict[str, Any]]:
    found = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        parsed = parse_offer_line(line)
        if parsed is not None:
            found.append(parsed)
    return found


def merge_rune_counts(ledger: dict[str, int] | None, inventory: dict[str, int] | None) -> dict[str, int]:
    """Currencies totals win. An inventory count fills a rune the ledger has at 0."""
    out: dict[str, int] = {}
    for name, count in (ledger or {}).items():
        try:
            out[str(name)] = max(0, int(count))
        except (TypeError, ValueError):
            continue
    for name, count in (inventory or {}).items():
        try:
            extra = max(0, int(count))
        except (TypeError, ValueError):
            continue
        if extra > 0 and int(out.get(str(name)) or 0) == 0:
            out[str(name)] = extra
    return out


def ledger_holdings(character: str) -> dict[str, Any]:
    """Mote and Wind Rune totals from the 1.1.6 ledger. Empty when no character."""
    name = (character or "").strip()
    if not name:
        return {"character": "", "motes": {}, "void_touched": 0, "wind_runes": {}, "found": False}
    view = get_book().view(name)
    motes = {row["name"]: int(row.get("total") or 0) for row in view.get("motes") or []}
    runes = {row["name"]: int(row.get("total") or 0) for row in view.get("wind_runes") or []}
    void_row = view.get("void_touched") or {}
    return {
        "character": view.get("character") or name,
        "motes": motes,
        "void_touched": int(void_row.get("total") or 0),
        "wind_runes": runes,
        "found": True,
    }


def _owned_count(name: str, owned: list[dict[str, Any]]) -> int:
    total = 0
    for row in owned or []:
        raw = row.get("name") if isinstance(row, dict) else row
        if not raw or not names_match(str(raw), name):
            continue
        if isinstance(row, dict):
            try:
                total += max(1, int(row.get("count") or 1))
            except (TypeError, ValueError):
                total += 1
        else:
            total += 1
    return total


def _offered_qty(offers: list[dict[str, Any]], npc: str, item: str) -> int:
    total = 0
    for offer in offers or []:
        if not names_match(str(offer.get("npc") or ""), npc):
            continue
        if not names_match(str(offer.get("item") or ""), item):
            continue
        try:
            total += int(offer.get("qty") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _log_complete(test: dict[str, Any], offers: list[dict[str, Any]]) -> bool:
    giver = test.get("giver") or ""
    if not giver:
        return False
    for rune in test.get("runes") or []:
        if _offered_qty(offers, giver, rune) < 1:
            return False
    for item in test.get("items") or []:
        item_name = item.get("name") if isinstance(item, dict) else str(item)
        if _offered_qty(offers, giver, item_name) < 1:
            return False
    pieces = list(test.get("runes") or []) + [
        (item.get("name") if isinstance(item, dict) else str(item))
        for item in (test.get("items") or [])
    ]
    return bool(pieces)


def plane_of_sky(
    *,
    achievements_text: str = "",
    offers: list[dict[str, Any]] | None = None,
    owned: list[dict[str, Any]] | None = None,
    wind_runes: dict[str, int] | None = None,
    manual: dict[str, str] | None = None,
    ignored: list[str] | None = None,
    goal_classes: list[str] | None = None,
    linked_names: list[str] | None = None,
) -> dict[str, Any]:
    """Have/need for every sourced Plane of Sky test, plus closest classes."""
    tests = pos_tests()
    parsed = achievement_test_status(achievements_text) if (achievements_text or "").strip() else {
        "classes": [], "done": {}, "unmatched": [],
    }
    granted = {row["class"]: row for row in parsed.get("classes") or [] if row.get("granted")}
    achievement_done = parsed.get("done") or {}
    ignore = {name.strip() for name in (ignored or []) if name and str(name).strip()}
    manual_map = manual or {}
    runes = wind_runes or {}
    goals = [name.strip() for name in (goal_classes or []) if name and str(name).strip()]
    links = [name for name in (linked_names or []) if name]

    classes: dict[str, dict[str, Any]] = {}
    rows = []
    for test in tests:
        class_name = test.get("class") or ""
        quest = test.get("quest") or ""
        bucket = classes.setdefault(class_name, {
            "class": class_name,
            "total": 0,
            "done": 0,
            "remaining": 0,
            "ignored": 0,
            "granted": class_name in granted,
            "granted_reason": (granted.get(class_name) or {}).get("granted_reason"),
            "token_unverified": bool((granted.get(class_name) or {}).get("token_unverified")),
            "goal": class_name in goals,
        })
        manual_flag = (manual_map.get(quest) or "").strip().lower()
        ignored_test = quest in ignore
        source = None
        complete = False
        if manual_flag in {"done", "not_done"}:
            complete = manual_flag == "done"
            source = "manual"
        elif quest in achievement_done and class_name not in granted:
            complete = True
            source = "achievement"
        elif _log_complete(test, offers or []):
            complete = True
            source = "log"
        if ignored_test:
            bucket["ignored"] += 1
        else:
            bucket["total"] += 1
            if complete:
                bucket["done"] += 1
            else:
                bucket["remaining"] += 1

        rune_rows = []
        for rune in test.get("runes") or []:
            try:
                have = int(runes.get(rune) or 0)
            except (TypeError, ValueError):
                have = 0
            rune_rows.append({
                "name": rune,
                "need": 1,
                "have": have,
                "met": have >= 1,
            })
        item_rows = []
        for item in test.get("items") or []:
            item_name = item.get("name") if isinstance(item, dict) else str(item)
            tag = item.get("tag") if isinstance(item, dict) else ""
            have = _owned_count(item_name, owned or [])
            item_rows.append({
                "name": item_name,
                "tag": tag or "",
                "need": 1,
                "have": have,
                "met": have >= 1,
            })
        linked = [name for name in links if names_match(name, test.get("reward") or "")]
        rows.append({
            "class": class_name,
            "quest": quest,
            "giver": test.get("giver") or "",
            "reward": test.get("reward") or "",
            "keyword": test.get("keyword") or "",
            "runes": rune_rows,
            "items": item_rows,
            "done": complete,
            "source": source,
            "ignored": ignored_test,
            "linked_bis": linked,
            "granted_class": class_name in granted,
        })

    class_rows = list(classes.values())
    for row in class_rows:
        row["closest_rank"] = row["remaining"]
    class_rows.sort(key=lambda row: (row["remaining"], row["class"].casefold()))
    return {
        "test_count": len(tests),
        "attribution": "Plane of Sky class tests from the EverQuest Legends Wiki (https://eqlwiki.com/Plane_of_Sky), CC BY-SA.",
        "classes": class_rows,
        "tests": rows,
        "unmatched_achievements": parsed.get("unmatched") or [],
        "granted_note": (
            "A completed autocomplete or bypass component means Unlocked (granted). "
            "Obtain rows on that class are not counted as turn-ins. "
            "Whether a Primary Class Unlock Token is what completes the bypass line is UNVERIFIED."
        ),
        "locked_note": "A status letter other than I or C is UNVERIFIED and is not treated as complete.",
    }


def build_upgrade_plan(
    items: list[dict[str, Any]],
    copies: list[dict[str, Any]],
    *,
    character: str = "",
    holdings: dict[str, int] | None = None,
    void_touched: int | None = None,
) -> dict[str, Any]:
    ledger = ledger_holdings(character) if character and holdings is None else None
    mote_counts = holdings
    vt = void_touched
    if ledger is not None:
        mote_counts = ledger["motes"]
        vt = ledger["void_touched"]
    if mote_counts is None:
        mote_counts = {}
    if vt is None:
        vt = 0
    planned_items = []
    for raw in items or []:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        prefer = raw.get("current_tier")
        try:
            prefer_tier = int(prefer) if prefer is not None and prefer != "" else None
        except (TypeError, ValueError):
            prefer_tier = None
        info = copies_for_item(name, copies or [], prefer_tier)
        planned_items.append({**raw, "name": name, "copy_info": info})
    plan = plan_upgrades(planned_items, mote_counts, vt)
    plan["character"] = (character or "").strip()
    plan["ledger"] = bool(ledger and ledger.get("found"))
    if not plan["character"]:
        plan["holdings_note"] = "No character is selected, so held motes are 0."
    elif not plan["ledger"] and holdings is None:
        plan["holdings_note"] = "This character has no currency ledger yet, so held motes are 0."
    else:
        plan["holdings_note"] = "Held motes and Void-Touched Potential are the Currencies totals (bags + storage)."
    return plan
