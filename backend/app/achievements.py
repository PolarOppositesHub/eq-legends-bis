"""Parse an /outputfile achievements dump. SPEC §9.4.

Verified shape, from a real achievements export:

- CRLF, tab-indented three-level tree.
- A category line has no tab and no status.
- An achievement line is ``I`` or ``C``, a tab, then the name.
- A component line is ``I`` or ``C``, a tab, a tab, then the text,
  with an optional fourth field such as ``n/m``.
- ``C`` is complete. ``I`` is incomplete.

Whether Locked uses its own letter is UNVERIFIED. Any other status
letter is kept and labeled unverified. It is not treated as complete.

Under ``Untapped Potential: Classes`` / ``Primary Class Unlock - <Class>``,
an ``Obtain <Reward>`` component maps to a Plane of Sky test by reward
name. A trailing period is part of the component format and is stripped
once. A name that does not match a reward stays unmatched.

If the autocomplete component or the bypass component is ``C``, the class
is Unlocked (granted). Obtain rows are then not counted as turn-ins.
The token case (bypass complete because of a Primary Class Unlock Token)
is UNVERIFIED.
"""
from __future__ import annotations

import re
from typing import Any

from .item_names import names_match
from .quest_links import pos_tests

_OBTAIN = re.compile(r"(?i)^obtain\s+(.+?)\.?\s*$")
_AUTO = "this achievement will autocomplete"
_BYPASS = "this achievement can be bypassed"
_BYPASS_TYPO = "this achievement can by bypassed"
_CLASS_PREFIX = "Primary Class Unlock - "
_CLASS_CATEGORY = "Untapped Potential: Classes"


def parse_achievements(text: str) -> dict[str, Any]:
    """Parse the tree. Never guesses a status letter."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    categories: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    achievement: dict[str, Any] | None = None
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if "\t" not in line:
            current = {"name": line.strip(), "line": line_no, "achievements": []}
            categories.append(current)
            achievement = None
            continue
        parts = line.split("\t")
        status = parts[0].strip()
        verified = status in {"I", "C"}
        complete = status == "C"
        if current is None:
            current = {"name": "", "line": line_no, "achievements": []}
            categories.append(current)
        # Achievement rows have the name in the second field.
        # Component rows leave that field empty and put text in the third.
        if len(parts) >= 2 and parts[1].strip() and (len(parts) < 3 or not parts[2].strip()):
            achievement = {
                "status": status,
                "status_verified": verified,
                "complete": complete if verified else False,
                "name": parts[1].strip(),
                "line": line_no,
                "components": [],
            }
            current["achievements"].append(achievement)
            continue
        text_part = parts[2].strip() if len(parts) >= 3 else ""
        progress = parts[3].strip() if len(parts) >= 4 else ""
        component = {
            "status": status,
            "status_verified": verified,
            "complete": complete if verified else False,
            "text": text_part,
            "progress": progress or None,
            "line": line_no,
            "kind": _component_kind(text_part),
        }
        if achievement is None:
            achievement = {
                "status": "",
                "status_verified": False,
                "complete": False,
                "name": "",
                "line": line_no,
                "components": [],
            }
            current["achievements"].append(achievement)
        achievement["components"].append(component)
    return {"categories": categories, "line_count": len(lines)}


def _component_kind(text: str) -> str:
    folded = (text or "").strip().casefold()
    if folded.startswith("obtain "):
        return "obtain"
    if folded.startswith(_AUTO):
        return "autocomplete"
    if folded.startswith(_BYPASS) or folded.startswith(_BYPASS_TYPO):
        return "bypass"
    return "other"


def obtain_reward(text: str) -> str:
    match = _OBTAIN.match((text or "").strip())
    if not match:
        return ""
    return match.group(1).strip()


def class_unlocks(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Primary Class Unlock achievements, with granted detection."""
    out = []
    for category in tree.get("categories") or []:
        if (category.get("name") or "") != _CLASS_CATEGORY:
            continue
        for achievement in category.get("achievements") or []:
            name = achievement.get("name") or ""
            if not name.startswith(_CLASS_PREFIX):
                continue
            class_name = name[len(_CLASS_PREFIX):].strip()
            obtains = []
            autocomplete = None
            bypass = None
            for component in achievement.get("components") or []:
                kind = component.get("kind")
                if kind == "obtain":
                    obtains.append({
                        "reward": obtain_reward(component.get("text") or ""),
                        "text": component.get("text") or "",
                        "complete": bool(component.get("complete")),
                        "status": component.get("status") or "",
                        "status_verified": bool(component.get("status_verified")),
                        "line": component.get("line"),
                    })
                elif kind == "autocomplete":
                    autocomplete = component
                elif kind == "bypass":
                    bypass = component
            auto_c = bool(autocomplete and autocomplete.get("complete"))
            bypass_c = bool(bypass and bypass.get("complete"))
            granted = auto_c or bypass_c
            reason = None
            unverified = False
            if auto_c and bypass_c:
                reason = "autocomplete_and_bypass"
                unverified = True
            elif auto_c:
                reason = "autocomplete"
            elif bypass_c:
                reason = "bypass"
                unverified = True
            out.append({
                "class": class_name,
                "achievement": name,
                "achievement_complete": bool(achievement.get("complete")),
                "granted": granted,
                "granted_reason": reason,
                "token_unverified": unverified and bypass_c,
                "obtains": obtains,
            })
    return out


def _reward_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for test in pos_tests():
        names = [test.get("reward") or ""]
        names.extend(test.get("aliases") or [])
        for raw in names:
            key = (raw or "").strip().casefold()
            if key and key not in index:
                index[key] = test
    return index


def match_obtain_to_test(reward: str, index: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Exact reward or alias match. No fuzzy spelling."""
    key = (reward or "").strip().casefold()
    if not key:
        return None
    table = index if index is not None else _reward_index()
    found = table.get(key)
    if found is not None:
        return found
    for candidate, test in table.items():
        if names_match(candidate, reward):
            return test
    return None


def achievement_test_status(text: str) -> dict[str, Any]:
    """Which PoS tests the achievements file marks done, and which classes are granted."""
    tree = parse_achievements(text)
    index = _reward_index()
    done: dict[str, str] = {}
    unmatched: list[dict[str, Any]] = []
    classes = []
    for unlock in class_unlocks(tree):
        classes.append({
            "class": unlock["class"],
            "granted": unlock["granted"],
            "granted_reason": unlock["granted_reason"],
            "token_unverified": unlock["token_unverified"],
            "achievement_complete": unlock["achievement_complete"],
        })
        if unlock["granted"]:
            continue
        for obtain in unlock["obtains"]:
            if not obtain.get("status_verified"):
                unmatched.append({
                    "class": unlock["class"],
                    "text": obtain.get("text") or "",
                    "reason": f"Status {obtain.get('status') or 'blank'!r} is UNVERIFIED. Only I and C are verified.",
                })
                continue
            test = match_obtain_to_test(obtain.get("reward") or "", index)
            if test is None:
                unmatched.append({
                    "class": unlock["class"],
                    "text": obtain.get("text") or "",
                    "reason": "This Obtain line does not match a Plane of Sky reward name.",
                })
                continue
            if obtain.get("complete"):
                done[test["quest"]] = "achievement"
    return {
        "classes": classes,
        "done": done,
        "unmatched": unmatched,
    }
