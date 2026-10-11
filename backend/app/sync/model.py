"""Append-only sync events and the replay that turns them into state.

An event is ``{id, ts, device_id, source, type, payload}``. State is the
replay sorted by ``(ts, device_id, id)``. Merging two devices is the union
of those ids. An event already in the log is never rewritten.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

SOURCES = {"log", "manual", "import"}

# Same sources the currency ledger adds into a count after the winning set.
STORAGE_SOURCES = {"manual", "log_loot", "log_given", "log_offer"}

SETTING_GROUPS = (
    "upgrade_progress",
    "upgrade_tier",
    "pos_manual",
    "pos_ignored",
    "achievements",
)


def new_id() -> str:
    return uuid.uuid4().hex


def log_event_id(character: str, raw_line: str, line_ts: str, device_id: str) -> str:
    """Same device and the same log line collapse to one id."""
    text = f"{character}\n{raw_line}\n{line_ts}\n{device_id}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sort_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("ts") or ""),
        str(event.get("device_id") or ""),
        str(event.get("id") or ""),
    )


def union_events(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Union by id. The first copy of an id wins; later copies are ignored."""
    found: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for group in groups:
        for event in group or []:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("id") or "")
            if not event_id:
                continue
            if event_id in found:
                continue
            found[event_id] = event
            order.append(event_id)
    return [found[event_id] for event_id in order]


def sorted_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=sort_key)


def make_event(
    *,
    event_id: str,
    ts: str,
    device_id: str,
    source: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if source not in SOURCES:
        raise ValueError("source must be log, manual, or import")
    return {
        "id": event_id,
        "ts": ts,
        "device_id": device_id,
        "source": source,
        "type": event_type,
        "payload": payload,
    }


def encode_jsonl(events: list[dict[str, Any]]) -> str:
    lines = [
        json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        for event in sorted_events(events)
    ]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def decode_jsonl(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("id"):
            events.append(item)
    return events


def _entry_of(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    entry = payload.get("entry")
    if isinstance(entry, dict):
        return entry
    return payload if isinstance(payload, dict) else {}


def project_character(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay one character. Older sets stay in history; the newest set is the count."""
    ordered = sorted_events(events)
    reverted: set[str] = set()
    for event in ordered:
        if event.get("type") != "currency_revert":
            continue
        target = str((event.get("payload") or {}).get("entry_id") or "")
        if target:
            reverted.add(target)

    history: list[dict[str, Any]] = []
    anchors: dict[str, dict[str, Any]] = {}
    deltas: dict[str, list[dict[str, Any]]] = {}
    for event in ordered:
        if event.get("type") != "currency":
            continue
        entry = dict(_entry_of(event))
        entry_id = str(entry.get("id") or event.get("id") or "")
        entry["id"] = entry_id
        entry["ts"] = str(entry.get("ts") or event.get("ts") or "")
        if entry_id in reverted:
            entry["reverted"] = True
        history.append(entry)
        if entry.get("reverted"):
            continue
        currency = str(entry.get("currency") or "")
        if not currency:
            continue
        if entry.get("anchor"):
            anchors[currency] = entry
            deltas[currency] = []
            continue
        if currency not in anchors:
            continue
        if entry.get("autosold"):
            continue
        if str(entry.get("source") or "") not in STORAGE_SOURCES:
            continue
        deltas.setdefault(currency, []).append(entry)

    counts: dict[str, int] = {}
    for currency, anchor in anchors.items():
        total = int(anchor.get("count") if anchor.get("count") is not None else anchor.get("delta") or 0)
        for entry in deltas.get(currency) or []:
            total += int(entry.get("delta") or 0)
        counts[currency] = total

    wishes: dict[str, tuple[str, bool]] = {}
    for event in ordered:
        if event.get("type") != "wish":
            continue
        payload = event.get("payload") or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        wishes[name.casefold()] = (name, bool(payload.get("pinned")))
    wish_names = [name for name, pinned in wishes.values() if pinned]

    identity = None
    for event in ordered:
        if event.get("type") != "parser_identity":
            continue
        payload = event.get("payload") or {}
        identity = {
            "classes": payload.get("classes"),
            "level": payload.get("level"),
            "cleared": bool(payload.get("cleared")),
            "ts": event.get("ts") or "",
            "device_id": event.get("device_id") or "",
        }

    settings_raw: dict[tuple[str, str], Any] = {}
    for event in ordered:
        if event.get("type") != "character_setting":
            continue
        payload = event.get("payload") or {}
        group = str(payload.get("group") or "")
        if group not in SETTING_GROUPS:
            continue
        item = str(payload.get("item") or "")
        settings_raw[(group, item)] = payload.get("value")

    settings: dict[str, Any] = {group: {} for group in SETTING_GROUPS}
    settings["pos_ignored"] = []
    settings["achievements"] = ""
    ignored: list[str] = []
    for (group, item), value in settings_raw.items():
        if group == "pos_ignored":
            if item and value:
                ignored.append(item)
            continue
        if group == "achievements":
            settings["achievements"] = "" if value is None else str(value)
            continue
        if item:
            settings[group][item] = value
    settings["pos_ignored"] = ignored

    sections: dict[str, dict[str, Any]] = {}
    section_events = [event for event in ordered if event.get("type") == "inventory_section"]
    for event in section_events:
        section = str((event.get("payload") or {}).get("section") or "")
        if section:
            sections[section] = event

    return {
        "currency_history": history,
        "currency_counts": counts,
        "wishes": wish_names,
        "identity": identity,
        "settings": settings,
        "sections": {key: event.get("payload") or {} for key, event in sections.items()},
        "section_events": section_events,
        "events": ordered,
    }


def project_all(by_character: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "characters": {
            character: project_character(events)
            for character, events in by_character.items()
        }
    }
