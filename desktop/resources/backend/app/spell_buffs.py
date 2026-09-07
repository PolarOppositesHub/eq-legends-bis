"""Spell buff catalog + Quick Buff (Cast Buffs) for Live Totals.

Source: eqlegendstools.com char-sheet `spellBuffs` bundle (decoded alongside
raceStats). Buff effects are taken from that verified catalog — never invented.

Quick Buff mirrors their `qt()`: among buffs castable by any selected trio
class, keep the highest stacking.priority per group (and respect excludes /
redundantWhenAvailable).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import APP_ROOT, app_root

SOURCE = {
    "url": "https://eqlegendstools.com/char-sheet/",
    "title": "EQ Legends Tools spellBuffs",
    "note": (
        "Buff lines are the max versions published in the eqlegendstools "
        "char-sheet catalog. Quick Buff picks the highest stacking priority "
        "per group among buffs your selected classes can cast."
    ),
}


def _buffs_json() -> Path:
    for c in (
        APP_ROOT / "data" / "spell_buffs.json",
        app_root() / "resources" / "data" / "spell_buffs.json",
        app_root() / "data" / "spell_buffs.json",
    ):
        if c.exists():
            return c
    return APP_ROOT / "data" / "spell_buffs.json"


@lru_cache(maxsize=1)
def load_spell_buffs() -> dict[str, Any]:
    path = _buffs_json()
    if not path.exists():
        return {"source": SOURCE, "buffs": [], "verified": False}
    data = json.loads(path.read_text())
    return {
        "source": {**SOURCE, **({k: data.get(k) for k in ("source", "verified", "schemaVersion") if k in data})},
        "buffs": list(data.get("buffs") or []),
        "verified": bool(data.get("verified", True)),
    }


def available_buffs(classes: list[str]) -> list[dict[str, Any]]:
    """Buffs any selected class can cast (Ht), minus redundant endure lines."""
    selected = {c for c in (classes or []) if c}
    if not selected:
        return []
    rows = load_spell_buffs().get("buffs") or []
    usable = [
        b for b in rows
        if selected.intersection(set(b.get("classes") or []))
    ]
    ids = {b["id"] for b in usable}
    groups_present = {
        (b.get("stacking") or {}).get("group")
        for b in usable
        if (b.get("stacking") or {}).get("group")
    }
    out = []
    for b in usable:
        st = b.get("stacking") or {}
        red = st.get("redundantWhenAvailable")
        if red and red in groups_present:
            # Hide Endure X when a Resist line in that group is available.
            continue
        out.append(b)
    return out


def _priority(buff: dict[str, Any]) -> int:
    return int((buff.get("stacking") or {}).get("priority") or 0)


def _group(buff: dict[str, Any]) -> str | None:
    return (buff.get("stacking") or {}).get("group")


def quick_buff_ids(classes: list[str]) -> list[str]:
    """qt() — highest-priority non-conflicting set for the trio."""
    candidates = sorted(
        available_buffs(classes),
        key=lambda b: (-_priority(b), b.get("name") or ""),
    )
    chosen: list[dict[str, Any]] = []
    for buff in candidates:
        # Skip if a higher-priority same-group buff already chosen
        g = _group(buff)
        if g and any(_group(c) == g for c in chosen):
            continue
        excludes = set((buff.get("stacking") or {}).get("excludes") or [])
        if any(
            buff["id"] in set((c.get("stacking") or {}).get("excludes") or [])
            or c["id"] in excludes
            for c in chosen
        ):
            continue
        chosen.append(buff)
    return [b["id"] for b in chosen]


def buffs_by_ids(ids: list[str], classes: list[str] | None = None) -> list[dict[str, Any]]:
    allow = {b["id"]: b for b in available_buffs(classes or [])} if classes is not None else {
        b["id"]: b for b in (load_spell_buffs().get("buffs") or [])
    }
    out = []
    for i in ids or []:
        b = allow.get(i)
        if b:
            out.append(b)
    return out


def aggregate_buff_effects(buffs: list[dict[str, Any]]) -> dict[str, float]:
    """Vt() — sum effects; Haste takes max."""
    stats: dict[str, float] = {}
    haste = 0.0
    for b in buffs or []:
        for k, v in (b.get("effects") or {}).items():
            if k == "HASTE":
                haste = max(haste, float(v or 0))
                continue
            stats[k] = stats.get(k, 0.0) + float(v or 0)
    if haste:
        stats["HASTE"] = haste
    return stats


def cast_buffs_payload(
    classes: list[str],
    *,
    mode: str = "off",
    active_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    mode:
      - off: no buffs
      - quick: auto max-priority set for trio classes
      - manual: use active_ids (filtered to available)
    """
    avail = available_buffs(classes)
    mode_n = (mode or "off").strip().lower()
    if mode_n in ("quick", "auto", "max", "on", "true", "1"):
        ids = quick_buff_ids(classes)
        mode_n = "quick"
    elif mode_n in ("manual", "custom"):
        ids = [i for i in (active_ids or []) if i]
        mode_n = "manual"
    else:
        ids = []
        mode_n = "off"

    active = buffs_by_ids(ids, classes)
    # For manual, drop ids that aren't available / conflict by re-running priority filter lightly
    if mode_n == "manual":
        # Keep user order but drop lower-priority same-group collisions
        pruned: list[dict[str, Any]] = []
        for b in sorted(active, key=lambda x: (-_priority(x), x.get("name") or "")):
            g = _group(b)
            if g and any(_group(c) == g for c in pruned):
                continue
            pruned.append(b)
        active = pruned
        ids = [b["id"] for b in active]

    effects = aggregate_buff_effects(active)
    return {
        "mode": mode_n,
        "available": [
            {
                "id": b["id"],
                "name": b["name"],
                "classes": b.get("classes") or [],
                "effects": b.get("effects") or {},
                "tooltip": b.get("tooltip") or "",
                "stacking": b.get("stacking") or {},
            }
            for b in sorted(avail, key=lambda x: x.get("name") or "")
        ],
        "active_ids": ids,
        "active": [
            {
                "id": b["id"],
                "name": b["name"],
                "classes": b.get("classes") or [],
                "effects": b.get("effects") or {},
                "tooltip": b.get("tooltip") or "",
            }
            for b in active
        ],
        "effects": effects,
        "source": SOURCE,
    }
