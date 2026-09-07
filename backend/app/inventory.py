"""Parse EQ Legends Inventory.txt (/outputfile inventory) TSV — Location/Name/ID/Count/Slots."""
from __future__ import annotations

import re
from typing import Any

from . import engine
from . import item_catalog as item_catalog_mod
from . import quest_guides
from . import scoring as sc
from . import zones as zones_mod

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


def _catalog_has_name(name: str) -> bool:
    # Never let catalog/image I/O break Inventory.txt import (worked as TSV-only in 1.0.3).
    try:
        return item_catalog_mod.name_in_catalog(name)
    except Exception:
        return False


_BINARY_HINT = re.compile(
    r"(This program cannot be run in DOS mode|\x00MZ|^\x7fELF|^\x89PNG)",
    re.I | re.M,
)
_INVENTORY_HELP = (
    "Use Inventory.txt from in-game /outputfile inventory "
    "(not inventory.exe or other binaries)."
)


def looks_like_binary_inventory(text: str) -> bool:
    """True when payload looks like a PE/ELF/binary dump rather than Inventory.txt TSV."""
    if text is None:
        return False
    sample = text[:4096]
    if "\x00" in sample:
        return True
    if sample.startswith("MZ") or sample.startswith("\x7fELF"):
        return True
    if _BINARY_HINT.search(sample):
        return True
    # High ratio of non-text bytes in the sample
    if sample:
        weird = sum(1 for ch in sample if ord(ch) < 9 or (14 <= ord(ch) < 32 and ch not in "\t\n\r"))
        if weird / max(1, len(sample)) > 0.08:
            return True
    return False


def parse_inventory_tsv(text: str) -> dict[str, Any]:
    """Parse Inventory.txt body. Returns worn equipment mapped to planner slots.

    Every non-empty inventory line is retained in `all_items` even when not in the
    catalog or not mappable to a planner slot (flagged unmatched / skipped).
    Raises ValueError when the payload looks like a binary/.exe file.
    """
    if looks_like_binary_inventory(text or ""):
        raise ValueError(_INVENTORY_HELP)

    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines:
        return {
            "equipment": {}, "rows": [], "worn": [], "all_items": [],
            "unmatched": [], "skipped": [], "warnings": ["Empty file"],
        }

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
    all_items: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
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

        base_name, upg = _strip_upgrade_suffix(name)
        in_catalog = bool(base_name) and _catalog_has_name(base_name)
        entry = {
            "location": location,
            "name": name,
            "base_name": base_name,
            "upgrade_from_name": upg,
            "id": item_id,
            "count": count,
            "slots": slots_col,
            "in_catalog": in_catalog,
            "unmatched": not in_catalog and bool(base_name) and base_name.lower() != "empty",
        }

        # Nested aug/bag slots: Head-Slot2, General 1-Slot1, Any Slot-Slot7
        if "-" in location and re.search(r"-Slot\d+$", location, re.I):
            entry["reason"] = "nested/aug slot"
            entry["planner_slot"] = None
            skipped.append(entry)
            all_items.append(entry)
            continue
        if location.lower().startswith("general ") or location.lower().startswith("bank"):
            entry["reason"] = "bag/bank"
            entry["planner_slot"] = None
            skipped.append(entry)
            all_items.append(entry)
            if entry["unmatched"]:
                unmatched.append(entry)
            continue
        if location.lower() in ("any slot", "keyring", "augmentation", "charm"):
            entry["reason"] = "non-planner worn"
            entry["planner_slot"] = None
            skipped.append(entry)
            all_items.append(entry)
            if entry["unmatched"]:
                unmatched.append(entry)
            continue
        if not name or name.lower() == "empty":
            entry["reason"] = "empty"
            entry["planner_slot"] = None
            skipped.append(entry)
            all_items.append(entry)
            continue

        loc_key = location.upper().strip()
        targets = LOCATION_TO_SLOTS.get(loc_key)
        if not targets:
            entry["reason"] = "unknown location"
            entry["planner_slot"] = None
            skipped.append(entry)
            all_items.append(entry)
            if entry["unmatched"]:
                unmatched.append(entry)
            continue

        idx = slot_counts.get(loc_key, 0)
        if idx >= len(targets):
            entry["reason"] = "extra duplicate location"
            entry["planner_slot"] = None
            skipped.append(entry)
            all_items.append(entry)
            if entry["unmatched"]:
                unmatched.append(entry)
            continue
        planner_slot = targets[idx]
        slot_counts[loc_key] = idx + 1

        entry["planner_slot"] = planner_slot
        entry["reason"] = None if in_catalog else "not in item DB (shown anyway)"
        worn.append(entry)
        all_items.append(entry)
        equipment[planner_slot] = base_name  # catalog/pool match without +N
        if upg is not None:
            upgrade_hints[planner_slot] = upg
        if entry["unmatched"]:
            unmatched.append(entry)

    return {
        "equipment": equipment,
        "upgrade_hints": upgrade_hints,
        "worn": worn,
        "all_items": all_items[:500],
        "unmatched": unmatched[:200],
        "unmatched_count": len(unmatched),
        "skipped": skipped[:200],
        "skipped_count": len(skipped),
        "warnings": [],
        "note": (
            "Parsed Inventory.txt TSV (Location/Name/ID/Count/Slots). "
            "Every line is retained in all_items. Unmatched (not in item DB) still listed "
            "with names from the file — no invented stats. "
            "Nested *-SlotN / bags / bank tagged in skipped but still visible in all_items."
        ),
    }


def _stat_delta(worn_stats: dict, bis_stats: dict) -> list[dict[str, Any]]:
    keys = [
        "AC", "HP", "MANA", "END", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA",
        "Haste", "DMG", "DLY", "HP_REGEN", "MANA_REGEN", "END_REGEN",
        "SVF", "SVC", "SVM", "SVP", "SVD",
    ]
    out = []
    for k in keys:
        a = float(worn_stats.get(k) or 0)
        b = float(bis_stats.get(k) or 0)
        d = b - a
        if abs(d) < 1e-9:
            continue
        out.append({"stat": k, "worn": a, "bis": b, "delta": d})
    return out


def _slot_importance(slot: str) -> int:
    """Tie-break order when priorities match — weapons/chest before jewelry."""
    order = [
        "CHEST", "PRIMARY", "SECONDARY", "LEGS", "HEAD", "ARMS", "HANDS", "FEET",
        "BACK", "SHOULDERS", "WAIST", "FACE", "NECK", "WRIST", "EAR1", "EAR2",
        "FINGER1", "FINGER2", "RANGE", "AMMO",
    ]
    try:
        return len(order) - order.index(slot)
    except ValueError:
        return 0


def _enrich_obtain(row: dict[str, Any], *, fetch_quest: bool = True) -> dict[str, Any]:
    """Attach zone/mob/quest obtain path for a BiS suggestion target.

    Degrades gracefully when quest wiki / zone research is unavailable — never raises.
    """
    name = (row.get("name") or "").strip()
    try:
        cat = item_catalog_mod.get_item_by_name(name) if name else None
    except Exception:
        cat = None
    base = {
        "zone": row.get("zone") or (cat or {}).get("zone") or "",
        "drops_mobs": row.get("drops_mobs") or (cat or {}).get("drops_mobs") or "",
        "quest_source": row.get("quest_source") or (cat or {}).get("quest_source") or (cat or {}).get("source") or "",
        "url": row.get("url") or (cat or {}).get("url") or "",
        "name": name,
    }
    try:
        obtain = quest_guides.obtain_path_for_item({**(cat or {}), **base}, fetch_quest=fetch_quest)
    except Exception:
        obtain = {
            "how": "unknown",
            "zone": base.get("zone") or "",
            "drops_mobs": base.get("drops_mobs") or "",
            "quest_source": base.get("quest_source") or "",
            "quest_name": None,
            "quest_guide": None,
            "item_url": base.get("url") or "",
            "error": "obtain path unavailable",
        }
    # Zone research summary (mobs with levels when available) — never invent
    zone_detail = None
    if obtain.get("zone"):
        try:
            zone_detail = zones_mod.zone_detail_for_item(obtain["zone"], obtain.get("drops_mobs") or "")
        except Exception:
            zone_detail = None
    return {
        **obtain,
        "zone_detail": {
            "found": bool((zone_detail or {}).get("found")),
            "zone": (zone_detail or {}).get("zone") or obtain.get("zone"),
            "drop_mobs": (zone_detail or {}).get("drop_mobs") or [],
            "level_requirement": ((zone_detail or {}).get("overview") or {}).get("level_requirement")
            or (zone_detail or {}).get("level_requirement"),
            "walkthrough_urls": (zone_detail or {}).get("walkthrough_urls") or [],
            "map_url": (zone_detail or {}).get("map_url"),
            "message": (zone_detail or {}).get("message") or "",
        } if obtain.get("zone") else None,
    }


def suggest_upgrades(
    classes: list[str],
    equipment: dict[str, str],
    *,
    upgrade: int = 10,
    character_level: int = 50,
    prefer_ranged_damage: bool = True,
    alts: int = 3,
    mode: str = "ai",
    priority_stat: str = "HP",
    primary_stats: list[str] | None = None,
    secondary_stats: list[str] | None = None,
    tertiary_stats: list[str] | None = None,
    maximize_hp_regen: bool = False,
    fetch_quest_guides: bool = True,
) -> dict[str, Any]:
    """Compare current equipment vs BiS list for the trio; prioritize closing BiS gaps."""
    if not classes:
        return {"suggestions": [], "bis": None, "error": "Select at least one class"}

    bis = engine.recommend_bis(
        classes,
        mode=mode or "ai",
        priority_stat=priority_stat or "HP",
        alts=alts,
        upgrade=upgrade,
        prefer_ranged_damage=prefer_ranged_damage,
        character_level=character_level,
        primary_stats=primary_stats,
        secondary_stats=secondary_stats,
        tertiary_stats=tertiary_stats,
        maximize_hp_regen=maximize_hp_regen,
    )
    suggestions: list[dict[str, Any]] = []
    equipment_compare: list[dict[str, Any]] = []
    eq_norm = {str(k).upper(): v for k, v in (equipment or {}).items() if v}

    for row in bis.get("slots") or []:
        slot = row["slot"]
        bis_name = (row.get("name") or "").strip()
        current = (eq_norm.get(slot) or "").strip()
        bis_stats = row.get("stats_at_upgrade") or row.get("stats_plus10") or {}
        bis_alts = [{"name": bis_name, "why": row.get("why"), "url": row.get("url") or ""}]
        for a in row.get("alts") or []:
            if a.get("name"):
                bis_alts.append({
                    "name": a["name"],
                    "why": a.get("why"),
                    "url": a.get("url") or "",
                    "stats_at_upgrade": a.get("stats_at_upgrade") or a.get("stats_plus10") or {},
                })

        cur_item = None
        cur_stats: dict[str, Any] = {}
        if current:
            try:
                pool_items = engine.items_for_slot(
                    classes, slot=slot, upgrade=upgrade, prefer_ranged_damage=prefer_ranged_damage
                )
            except Exception:
                pool_items = []
            cur_item = next(
                (it for it in pool_items if (it.get("name") or "").lower() == current.lower()),
                None,
            )
            if cur_item:
                cur_stats = cur_item.get("stats_at_upgrade") or cur_item.get("stats_plus10") or {}
            else:
                # Unmatched worn item — name only, no invented stats
                cat = item_catalog_mod.get_item_by_name(current)
                if cat:
                    cur_stats = cat.get("stats_plus10") or cat.get("stats_plus0") or {}

        deltas = _stat_delta(cur_stats, bis_stats) if bis_name else []
        equipment_compare.append({
            "slot": slot,
            "worn": {
                "name": current or None,
                "in_catalog": bool(cur_item) or (bool(current) and _catalog_has_name(current)),
                "stats": cur_stats,
                "url": (cur_item or {}).get("url") or "",
                "image_url": f"/api/item-image?name={current}" if current else "",
            },
            "bis_options": bis_alts,
            "selected_bis": bis_name or None,
            "deltas": deltas,
        })

        if not bis_name:
            continue
        if current and current.lower() == bis_name.lower():
            continue

        positive_gap = sum(d["delta"] for d in deltas if d["delta"] > 0)
        negative_gap = sum(-d["delta"] for d in deltas if d["delta"] < 0)
        net_gap = positive_gap - negative_gap

        if not current:
            pri = 100
            reason = "missing BiS (slot empty) — upgrade to BiS list pick"
        else:
            worse = net_gap > 1e-9
            reason = (
                f"not current BiS — replace with {bis_name}"
                + (f" (net BiS gain ~{net_gap:.0f})" if deltas else "")
            )
            # Finer priority: empty=100, large gap=90-99, unmatched=85, small/neutral=50-70
            if not cur_item and not _catalog_has_name(current):
                pri = 85
                reason = f"worn item unmatched in DB; BiS list recommends {bis_name}"
            elif worse:
                pri = min(99, 90 + int(min(9, max(0, net_gap) // 20)))
            else:
                pri = 55

        obtain = _enrich_obtain(row, fetch_quest=fetch_quest_guides)
        how_bits = []
        if obtain.get("how") == "drop" and (obtain.get("zone") or obtain.get("drops_mobs")):
            how_bits.append(
                "Drop"
                + (f" in {obtain['zone']}" if obtain.get("zone") else "")
                + (f" from {obtain['drops_mobs']}" if obtain.get("drops_mobs") else "")
            )
        elif obtain.get("how") == "quest" and obtain.get("quest_name"):
            how_bits.append(f"Quest: {obtain['quest_name']}")
        elif obtain.get("zone"):
            how_bits.append(f"Zone: {obtain['zone']}")
        if how_bits:
            reason = f"{reason} · {' · '.join(how_bits)}"

        suggestions.append({
            "slot": slot,
            "priority": pri,
            "rank_score": pri * 1000 + _slot_importance(slot) * 10 + max(0, int(net_gap)),
            "reason": reason,
            "current": current or None,
            "suggested": bis_name,
            "suggested_url": row.get("url") or obtain.get("item_url") or "",
            "suggested_zone": obtain.get("zone") or row.get("zone") or "",
            "suggested_drops_mobs": obtain.get("drops_mobs") or "",
            "suggested_quest_source": obtain.get("quest_source") or "",
            "suggested_quest_name": obtain.get("quest_name"),
            "suggested_ratio": row.get("ratio_at_upgrade"),
            "suggested_why": row.get("why") or "",
            "suggested_image_url": f"/api/item-image?name={bis_name}" if bis_name else "",
            "deltas": deltas,
            "obtain": obtain,
        })

    suggestions.sort(key=lambda s: (-s.get("rank_score", 0), -s["priority"], s["slot"]))
    # Stable 1-based display rank
    for i, s in enumerate(suggestions, start=1):
        s["rank"] = i

    return {
        "suggestions": suggestions,
        "equipment_compare": equipment_compare,
        "bis_summary": {
            "classes": bis.get("classes"),
            "mode": bis.get("mode"),
            "upgrade": bis.get("upgrade"),
            "character_level": bis.get("character_level"),
            "pool_size": bis.get("pool_size"),
        },
        "equipment": eq_norm,
        "note": (
            "Upgrade Priority list is ordered by importance (empty slots first, then largest "
            "BiS gaps). Each entry includes how to get the item: zone + drop mobs and/or quest "
            "name with steps from eqlwiki when available — never invented."
        ),
    }
