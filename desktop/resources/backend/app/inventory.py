"""Parse EQ Legends Inventory.txt (/outputfile inventory) TSV — Location/Name/ID/Count/Slots."""
from __future__ import annotations

import re
from typing import Any

from . import engine

# Inventory Location → planner slot(s). Multi-slot locations consume in order.
LOCATION_TO_SLOTS: dict[str, list[str]] = {
    "HEAD": ["HEAD"],
    "FACE": ["FACE"],
    "EAR": ["EAR1", "EAR2"],
    "NECK": ["NECK"],
    "SHOULDERS": ["SHOULDERS"],
    "ARMS": ["ARMS"],
    "WRIST": ["WRIST"],
    "HANDS": ["HANDS"],
    "CHEST": ["CHEST"],
    "BACK": ["BACK"],
    "WAIST": ["WAIST"],
    "LEGS": ["LEGS"],
    "FEET": ["FEET"],
    "FINGERS": ["FINGER1", "FINGER2"],
    "FINGER": ["FINGER1", "FINGER2"],
    "PRIMARY": ["PRIMARY"],
    "SECONDARY": ["SECONDARY"],
    "RANGE": ["RANGE"],
    "RANGED": ["RANGE"],
    "AMMO": ["AMMO"],
}


def _strip_upgrade_suffix(name: str) -> tuple[str, int | None]:
    """'Raw-Hide Skullcap +2' → ('Raw-Hide Skullcap', 2). Trailing * (attuned) stripped."""
    n = (name or "").strip()
    if n.endswith("*"):
        n = n[:-1].strip()
    m = re.search(r"\s\+(\d+)\s*$", n)
    if not m:
        return n, None
    return n[: m.start()].strip(), int(m.group(1))


def parse_inventory_tsv(text: str) -> dict[str, Any]:
    """Parse Inventory.txt body. Returns worn equipment mapped to planner slots."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines:
        return {"equipment": {}, "rows": [], "worn": [], "skipped": [], "warnings": ["Empty file"]}

    # Find header
    start = 0
    for i, line in enumerate(lines[:20]):
        cols = line.split("\t")
        if cols and cols[0].strip().lower() == "location" and any(
            c.strip().lower() == "name" for c in cols
        ):
            start = i + 1
            break

    worn: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    slot_counts: dict[str, int] = {}
    equipment: dict[str, str] = {}
    upgrade_hints: dict[str, int] = {}

    for line in lines[start:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        location = (cols[0] or "").strip()
        name = (cols[1] or "").strip() if len(cols) > 1 else ""
        item_id = (cols[2] or "").strip() if len(cols) > 2 else ""
        count = (cols[3] or "").strip() if len(cols) > 3 else ""
        slots_col = (cols[4] or "").strip() if len(cols) > 4 else ""

        # Nested aug/bag slots: Head-Slot2, General 1-Slot1, Any Slot-Slot7
        if "-" in location and re.search(r"-Slot\d+$", location, re.I):
            skipped.append({"location": location, "name": name, "reason": "nested/aug slot"})
            continue
        if location.lower().startswith("general ") or location.lower().startswith("bank"):
            skipped.append({"location": location, "name": name, "reason": "bag/bank"})
            continue
        if location.lower() in ("any slot", "keyring", "augmentation", "charm"):
            skipped.append({"location": location, "name": name, "reason": "non-planner worn"})
            continue
        if not name or name.lower() == "empty" or item_id == "0":
            skipped.append({"location": location, "name": name or "Empty", "reason": "empty"})
            continue

        loc_key = location.upper().strip()
        targets = LOCATION_TO_SLOTS.get(loc_key)
        if not targets:
            skipped.append({"location": location, "name": name, "reason": "unknown location"})
            continue

        idx = slot_counts.get(loc_key, 0)
        if idx >= len(targets):
            skipped.append({"location": location, "name": name, "reason": "extra duplicate location"})
            continue
        planner_slot = targets[idx]
        slot_counts[loc_key] = idx + 1

        base_name, upg = _strip_upgrade_suffix(name)
        worn.append({
            "location": location,
            "planner_slot": planner_slot,
            "name": name,
            "base_name": base_name,
            "upgrade_from_name": upg,
            "id": item_id,
            "count": count,
            "slots": slots_col,
        })
        equipment[planner_slot] = base_name  # catalog/pool match without +N
        if upg is not None:
            upgrade_hints[planner_slot] = upg

    return {
        "equipment": equipment,
        "upgrade_hints": upgrade_hints,
        "worn": worn,
        "skipped": skipped[:200],
        "skipped_count": len(skipped),
        "warnings": [],
        "note": (
            "Parsed Inventory.txt TSV (Location/Name/ID/Count/Slots). "
            "Nested *-SlotN, bags, bank, Any Slot skipped. "
            "Item names stripped of +N for catalog match; upgrade_hints retained from dump."
        ),
    }


def suggest_upgrades(
    classes: list[str],
    equipment: dict[str, str],
    *,
    upgrade: int = 10,
    character_level: int = 50,
    prefer_ranged_damage: bool = True,
    alts: int = 3,
) -> dict[str, Any]:
    """Compare current equipment vs BiS/pool; prioritize missing or worse slots."""
    if not classes:
        return {"suggestions": [], "bis": None, "error": "Select at least one class"}

    bis = engine.recommend_bis(
        classes,
        mode="priority",
        priority_stat="HP",
        alts=alts,
        upgrade=upgrade,
        prefer_ranged_damage=prefer_ranged_damage,
        character_level=character_level,
    )
    suggestions: list[dict[str, Any]] = []
    eq_norm = {str(k).upper(): v for k, v in (equipment or {}).items() if v}

    for row in bis.get("slots") or []:
        slot = row["slot"]
        bis_name = (row.get("name") or "").strip()
        current = (eq_norm.get(slot) or "").strip()
        if not bis_name:
            continue
        if not current:
            suggestions.append({
                "slot": slot,
                "priority": 100,
                "reason": "missing BiS (slot empty)",
                "current": None,
                "suggested": bis_name,
                "suggested_url": row.get("url") or "",
                "suggested_zone": row.get("zone") or "",
                "suggested_ratio": row.get("ratio_at_upgrade"),
                "suggested_why": row.get("why") or "",
            })
            continue
        if current.lower() == bis_name.lower():
            continue
        # Compare ratios when both weapons; else treat as worse-than-BiS gap
        cur_ratio = None
        # look up current in alts or pool via items_for_slot
        try:
            pool_items = engine.items_for_slot(
                classes, slot=slot, upgrade=upgrade, prefer_ranged_damage=prefer_ranged_damage
            )
        except Exception:
            pool_items = []
        cur_item = next((it for it in pool_items if (it.get("name") or "").lower() == current.lower()), None)
        bis_ratio = row.get("ratio_at_upgrade")
        if cur_item:
            cur_ratio = cur_item.get("ratio_at_upgrade")
        worse = False
        reason = "not current BiS"
        if bis_ratio is not None and cur_ratio is not None:
            if float(cur_ratio) + 1e-9 < float(bis_ratio):
                worse = True
                reason = f"worse ratio ({float(cur_ratio):.4f} < BiS {float(bis_ratio):.4f})"
            else:
                # equal/better ratio but different item — still note BiS alternate
                reason = f"differs from BiS (yours ratio {float(cur_ratio):.4f})"
                worse = float(cur_ratio) + 1e-9 < float(bis_ratio)
        else:
            # stat heuristic: compare HP+AC on upgrade stats if present
            bis_stats = row.get("stats_at_upgrade") or row.get("stats_plus10") or {}
            cur_stats = (cur_item or {}).get("stats_at_upgrade") or (cur_item or {}).get("stats_plus10") or {}
            bis_score = float(bis_stats.get("HP") or 0) + 2 * float(bis_stats.get("AC") or 0)
            cur_score = float(cur_stats.get("HP") or 0) + 2 * float(cur_stats.get("AC") or 0)
            if cur_score + 1e-9 < bis_score:
                worse = True
                reason = f"worse HP/AC proxy ({cur_score:.0f} < BiS {bis_score:.0f})"
            else:
                reason = "differs from recommended BiS"

        if worse or current.lower() != bis_name.lower():
            pri = 80 if not current else (70 if worse else 40)
            if bis_ratio is not None and cur_ratio is not None and worse:
                pri = 90
            suggestions.append({
                "slot": slot,
                "priority": pri,
                "reason": reason,
                "current": current,
                "current_ratio": cur_ratio,
                "suggested": bis_name,
                "suggested_url": row.get("url") or "",
                "suggested_zone": row.get("zone") or "",
                "suggested_ratio": bis_ratio,
                "suggested_why": row.get("why") or "",
            })

    suggestions.sort(key=lambda s: (-s["priority"], s["slot"]))
    return {
        "suggestions": suggestions,
        "bis_summary": {
            "classes": bis.get("classes"),
            "upgrade": bis.get("upgrade"),
            "character_level": bis.get("character_level"),
            "pool_size": bis.get("pool_size"),
        },
        "equipment": eq_norm,
        "note": "Upgrade-first vs current BiS/pool at selected upgrade. Missing slots ranked highest.",
    }
