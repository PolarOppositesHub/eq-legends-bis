"""Alert rules over parsed log events.

Built-ins use lines the parser already classifies. Charm break stays off:
the owner's log has no charm-worn-off line, and SPEC §5.3 marks it unverified.
Raid roster lines are unverified. A raid-target rule matches a name the user
typed against a verified slain or died line.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from typing import Any

CHARM_NOTE = "Charm break is unverified. No matching line is in the log corpus, so this rule stays off."
RAID_NOTE = "Raid join lines are unverified. This matches a name you type against a slain or died line."

BUILTIN_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "builtin-slow",
        "name": "Slow landed",
        "enabled": True,
        "kind": "slow",
        "cooldown": 0,
        "sound": "speech",
        "builtin": True,
    },
    {
        "id": "builtin-death",
        "name": "You died",
        "enabled": True,
        "kind": "death",
        "cooldown": 0,
        "sound": "speech",
        "builtin": True,
    },
    {
        "id": "builtin-mez",
        "name": "Mez or pacify faded",
        "enabled": True,
        "kind": "spell_fade",
        "cooldown": 0,
        "sound": "speech",
        "builtin": True,
    },
    {
        "id": "builtin-raid-slain",
        "name": "Raid target slain",
        "enabled": True,
        "kind": "raid_slain",
        "names": [],
        "cooldown": 0,
        "sound": "speech",
        "builtin": True,
        "note": RAID_NOTE,
    },
    {
        "id": "builtin-charm",
        "name": "Charm break",
        "enabled": False,
        "kind": "charm_break",
        "cooldown": 0,
        "sound": "none",
        "builtin": True,
        "gated": True,
        "note": CHARM_NOTE,
    },
)


def default_rules() -> list[dict[str, Any]]:
    return [dict(row) for row in BUILTIN_RULES]


def match_rule(rule: dict[str, Any], event: Any, message: str) -> str | None:
    """Return the alert text, or None when the rule does not match this line."""
    if not rule.get("enabled"):
        return None
    if rule.get("gated"):
        return None
    kind = rule.get("kind")
    text = (message or getattr(event, "text", "") or "").strip()
    if kind == "regex":
        pattern = rule.get("pattern") or ""
        if not pattern or len(pattern) > 200:
            return None
        try:
            found = re.search(pattern, text)
        except re.error:
            return None
        return text if found else None
    if event is None:
        return None
    event_kind = getattr(event, "kind", None)
    if kind == "slow" and event_kind == "slow":
        return text or f"{getattr(event, 'target', '')}'s limbs move slower!"
    if kind == "death" and event_kind == "death" and _is_you(getattr(event, "target", None)):
        return text or "You died."
    if kind == "spell_fade" and event_kind == "spell_fade":
        return text
    if kind == "raid_slain":
        name = _dead_name(event)
        if not name or _is_you(name):
            return None
        wanted = {str(item).casefold() for item in (rule.get("names") or []) if str(item).strip()}
        if name.casefold() not in wanted:
            return None
        return text or f"{name} has been slain."
    if kind == "charm_break":
        return None
    return None


def share_encode(rules: list[dict[str, Any]]) -> str:
    payload = {
        "v": 1,
        "rules": [_public_rule(rule) for rule in rules if not rule.get("builtin")],
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def share_decode(text: str) -> list[dict[str, Any]]:
    try:
        raw = base64.b64decode((text or "").strip().encode("ascii"), validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("share string is not a rules paste") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("share string version is not 1")
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("share string has no rules")
    out = []
    for rule in rules:
        if isinstance(rule, dict) and rule.get("id") and rule.get("kind"):
            out.append(_public_rule(rule))
    return out


def cooldown_blocks(last_ts: str | None, now_ts: str | None, seconds: int) -> bool:
    if not seconds or not last_ts or not now_ts:
        return False
    try:
        last = datetime.strptime(last_ts[:19], "%Y-%m-%dT%H:%M:%S")
        now = datetime.strptime(now_ts[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return False
    return (now - last).total_seconds() < int(seconds)


def _public_rule(rule: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": str(rule.get("id") or ""),
        "name": str(rule.get("name") or "Alert"),
        "enabled": bool(rule.get("enabled", True)) and not rule.get("gated"),
        "kind": str(rule.get("kind") or ""),
        "cooldown": int(rule.get("cooldown") or 0),
        "sound": rule.get("sound") if rule.get("sound") in {"speech", "file", "none"} else "speech",
        "builtin": bool(rule.get("builtin")),
    }
    if rule.get("pattern"):
        out["pattern"] = str(rule["pattern"])[:200]
    if rule.get("names"):
        out["names"] = [str(name) for name in rule["names"] if str(name).strip()]
    if rule.get("sound_file"):
        out["sound_file"] = str(rule["sound_file"])[:500]
    if rule.get("note"):
        out["note"] = str(rule["note"])
    if rule.get("gated"):
        out["gated"] = True
        out["enabled"] = False
    return out


def _is_you(name: str | None) -> bool:
    return (name or "").strip().casefold() in {"you", "yourself"}


def _dead_name(event: Any) -> str | None:
    kind = getattr(event, "kind", None)
    if kind == "slain":
        return getattr(event, "target", None)
    if kind == "death":
        return getattr(event, "target", None)
    return None
