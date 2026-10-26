"""Merge a sourced item update into aggregate.json.

Stat keys are copied only when the catalog already knows them. Other tooltip
words stay in tooltipLines. Source conflicts are kept as text and not resolved.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def known_stat_keys() -> set[str]:
    from .class_roles import normalize_stat_key
    from .item_catalog import _TIP_STAT_MAP

    keys = set(_TIP_STAT_MAP.values())
    keys.add("DLY")
    for alias in ("Mana Regen", "HP Regen", "End Regen", "Haste"):
        mapped = normalize_stat_key(alias)
        if mapped:
            keys.add("Haste" if mapped == "HASTE" else mapped)
    return keys


def map_stat_key(key: str, known: set[str] | None = None) -> str | None:
    from .class_roles import normalize_stat_key
    from .item_catalog import _TIP_STAT_MAP

    raw = str(key or "").strip()
    if not raw:
        return None
    allowed = known if known is not None else known_stat_keys()
    upper = raw.upper()
    if upper in _TIP_STAT_MAP:
        mapped = _TIP_STAT_MAP[upper]
    else:
        mapped = normalize_stat_key(raw)
    if mapped == "HASTE":
        mapped = "Haste"
    if mapped in allowed:
        return mapped
    return None


def conflicts_from_notes(notes: str | None) -> list[str]:
    text = str(notes or "")
    at = text.find("CONFLICT:")
    if at < 0:
        return []
    line = text[at:].strip()
    return [line] if line else []


def _name_key(name: str) -> str:
    return " ".join(str(name or "").casefold().split())


def aggregate_row(source: dict[str, Any], order: int, known: set[str]) -> dict[str, Any]:
    """One aggregate row. Unmapped stat keys are left out of stats."""
    stats_in = source.get("stats") if isinstance(source.get("stats"), dict) else {}
    stats: dict[str, Any] = {}
    for key, value in stats_in.items():
        mapped = map_stat_key(str(key), known)
        if not mapped or value is None or value == "":
            continue
        stats[mapped] = value
    weapon = source.get("weapon") if isinstance(source.get("weapon"), dict) else {}
    notes = source.get("reviewNotes") or ""
    row = {
        "name": source.get("name"),
        "itemID": source.get("itemID"),
        "slots": source.get("slots") or [],
        "classes": source.get("classes") or [],
        "stats": stats,
        "special": source.get("special") or "",
        "source": source.get("source") or "",
        "flags": source.get("flags") or [],
        "sourceUrl": source.get("sourceUrl") or "",
        "zamUrl": source.get("zamUrl") or "",
        "dropsFrom": source.get("dropsFrom") or [],
        "rewardFromQuests": source.get("rewardFromQuests") or [],
        "tooltipLines": source.get("tooltipLines") or [],
        "sourceZone": source.get("sourceZone") or "",
        "sourceZoneUrl": source.get("sourceZoneUrl") or "",
        "sourceZones": source.get("sourceZones") or [],
        "sourceZoneUrls": source.get("sourceZoneUrls") or [],
        "reviewNotes": notes,
        "minLevel": source.get("minLevel"),
        "sourceDisplay": source.get("sourceDisplay") or "",
        "sourceHref": source.get("sourceHref") or "",
        "sourceKind": source.get("sourceKind") or "",
        "skill": source.get("skill") or "",
        "source_conflicts": conflicts_from_notes(notes),
        "__catalogOrder": order,
    }
    if weapon.get("ratio0") is not None and weapon.get("ratio0") != "":
        row["ratio_plus0"] = weapon.get("ratio0")
    if weapon.get("ratio10") is not None and weapon.get("ratio10") != "":
        row["ratio_plus10"] = weapon.get("ratio10")
    return row


def merge_item_update(aggregate_path: Path, items_path: Path) -> int:
    """Append items whose names are not already in the catalog. Returns added count."""
    if not aggregate_path.is_file() or not items_path.is_file():
        return 0
    rows = json.loads(aggregate_path.read_text(encoding="utf-8"))
    incoming = json.loads(items_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not isinstance(incoming, list):
        return 0
    have = {_name_key(row.get("name")) for row in rows if isinstance(row, dict)}
    order = max((int(row.get("__catalogOrder") or 0) for row in rows if isinstance(row, dict)), default=-1)
    known = known_stat_keys()
    added = 0
    for source in incoming:
        if not isinstance(source, dict):
            continue
        name = _name_key(source.get("name"))
        if not name or name in have:
            continue
        order += 1
        rows.append(aggregate_row(source, order, known))
        have.add(name)
        added += 1
    if added:
        aggregate_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return added
