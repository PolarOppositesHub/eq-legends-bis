"""Cheapest mote path for a BiS target. SPEC §9.1–9.3.

XP rules are the eqlwiki Item_Upgrade_System / Mote_Guide table already
stored on the currency ledger (SPEC §8.1):

- XP from +t to +(t+1) is 2^t.
- Cumulative XP to reach +T from +0 is 2^T − 1.
- A duplicate at +k adds 2^k XP. Gear merges have no tier cap.
- A mote adds its item XP only while the item's current tier is within
  that mote's "usable on" limit. Overflow carries.
- Void-Touched Potential advances one tier and ignores progress.

Item XP values are read from the ledger table. This module does not
invent a second mote table. Void-Touched is assigned to the highest
remaining tier gaps first, across items, one gap at a time.
"""
from __future__ import annotations

from typing import Any

from .currencies import VOID_TOUCHED_NAME, _MOTE_META, condense_preview
from .inventory import MOTE_GRADES, _parse_item_name

# Rank N is usable while the item is at + (N-1) or below.
# Rank 1 is "+0" only. Rank 10 is "≤ +9". SPEC §8.1.
_XP_BY_GRADE: dict[int, int] = {}
_NAME_BY_GRADE: dict[int, str] = {}
_LIMIT_BY_GRADE: dict[int, int] = {}
for _grade, _name in MOTE_GRADES:
    _meta = _MOTE_META[_name]
    _XP_BY_GRADE[_grade] = int(_meta["item_xp"])
    _NAME_BY_GRADE[_grade] = _name
    _LIMIT_BY_GRADE[_grade] = _grade - 1


def mote_item_xp(grade: int) -> int:
    return _XP_BY_GRADE[grade]


def tier_step_xp(tier: int) -> int:
    """XP required to leave +tier for the next tier. 2^tier."""
    if tier < 0:
        raise ValueError("tier must be >= 0")
    return 1 << tier


def cumulative_xp(tier: int) -> int:
    """XP to reach +tier from +0 with no progress. 2^tier − 1."""
    if tier < 0:
        raise ValueError("tier must be >= 0")
    if tier == 0:
        return 0
    return (1 << tier) - 1


def duplicate_xp(tier: int) -> int:
    """XP gained by merging a duplicate that is already at +tier."""
    return tier_step_xp(tier)


def xp_still_needed(current: int, target: int, progress: int) -> int:
    """cumulative(target) − cumulative(current) − progress, floored at 0."""
    current = _clamp_tier(current)
    target = _clamp_tier(target)
    progress = max(0, int(progress))
    if target <= current:
        return 0
    return max(0, cumulative_xp(target) - cumulative_xp(current) - progress)


def legal_grades(tier: int) -> list[int]:
    """Lowest grade first. A grade is legal when tier <= its usable-on limit."""
    return [grade for grade in range(1, 11) if tier <= _LIMIT_BY_GRADE[grade]]


def apply_xp(tier: int, progress: int, xp: int, cap: int) -> tuple[int, int, int]:
    """Spend ``xp`` toward ``cap``. Returns tier, progress, unused xp."""
    tier = _clamp_tier(tier)
    cap = _clamp_tier(cap)
    progress = max(0, int(progress))
    left = max(0, int(xp))
    while left > 0 and tier < cap:
        need = tier_step_xp(tier) - progress
        if need < 0:
            need = 0
        if left >= need:
            left -= need
            tier += 1
            progress = 0
        else:
            progress += left
            left = 0
    return tier, progress, left


def cheapest_motes(
    tier: int,
    progress: int,
    target: int,
    *,
    skip_tiers: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Unconstrained cheapest motes. Lowest legal grade at each tier.

    ``skip_tiers`` are crossed with Void-Touched instead of motes.
    """
    tier = _clamp_tier(tier)
    target = _clamp_tier(target)
    progress = max(0, int(progress))
    skip = skip_tiers or set()
    counts: dict[int, int] = {}
    guard = 0
    while tier < target and guard < 64:
        guard += 1
        if tier in skip:
            tier += 1
            progress = 0
            continue
        grades = legal_grades(tier)
        if not grades:
            break
        grade = grades[0]
        xp = _XP_BY_GRADE[grade]
        need = tier_step_xp(tier) - progress
        if need < 1:
            tier += 1
            progress = 0
            continue
        count = (need + xp - 1) // xp
        counts[grade] = counts.get(grade, 0) + count
        gained = count * xp
        tier, progress, _unused = apply_xp(tier, progress, gained, target)
    return _count_rows(counts)


def _count_rows(counts: dict[int, int]) -> list[dict[str, Any]]:
    rows = []
    for grade in range(1, 11):
        count = int(counts.get(grade) or 0)
        if count <= 0:
            continue
        rows.append({
            "grade": grade,
            "name": _NAME_BY_GRADE[grade],
            "count": count,
            "item_xp": _XP_BY_GRADE[grade],
            "total_item_xp": count * _XP_BY_GRADE[grade],
        })
    return rows


def _clamp_tier(value: Any) -> int:
    try:
        tier = int(value)
    except (TypeError, ValueError):
        tier = 0
    return max(0, min(10, tier))


def _split_copy(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = str(raw.get("name") or "").strip()
    if not name or name.casefold() == "empty":
        return None
    base, parsed, _star = _parse_item_name(name)
    if not base or base.casefold() == "empty":
        return None
    tier = raw.get("tier")
    if tier is None:
        tier = parsed
    else:
        try:
            tier = int(tier)
        except (TypeError, ValueError):
            tier = parsed
    try:
        count = int(raw.get("count") if raw.get("count") is not None else 1)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        return None
    return {"name": base, "tier": tier, "count": count, "tier_known": tier is not None}


def copies_for_item(
    name: str,
    copies: list[dict[str, Any]],
    prefer_tier: int | None = None,
) -> dict[str, Any]:
    """One explicit +N copy is the item being upgraded. The rest are duplicates.

    With no preferred tier, the highest +N is the one being upgraded.
    A copy whose export has no +N is listed and is not given +0 XP.
    """
    from .item_names import names_match

    known: list[tuple[int, int]] = []
    unknown = 0
    for raw in copies or []:
        parsed = _split_copy(raw)
        if parsed is None or not names_match(parsed["name"], name):
            continue
        if parsed["tier_known"]:
            known.append((int(parsed["tier"]), int(parsed["count"])))
        else:
            unknown += int(parsed["count"])
    if not known and unknown <= 0:
        return {
            "owned": False,
            "current_tier": None,
            "tier_known": False,
            "duplicates": [],
            "duplicate_xp": 0,
            "unknown_tier_copies": 0,
        }
    if not known:
        return {
            "owned": True,
            "current_tier": None,
            "tier_known": False,
            "duplicates": [],
            "duplicate_xp": 0,
            "unknown_tier_copies": unknown,
        }
    pools: dict[int, int] = {}
    for tier, count in known:
        pools[tier] = pools.get(tier, 0) + count
    if prefer_tier is not None and pools.get(int(prefer_tier), 0) > 0:
        current = int(prefer_tier)
    else:
        current = max(pools)
    pools[current] -= 1
    duplicates: list[dict[str, Any]] = []
    xp = 0
    for tier in sorted(pools):
        count = pools[tier]
        if count <= 0:
            continue
        gained = duplicate_xp(tier) * count
        duplicates.append({"tier": tier, "count": count, "xp": gained})
        xp += gained
    return {
        "owned": True,
        "current_tier": current,
        "tier_known": True,
        "duplicates": duplicates,
        "duplicate_xp": xp,
        "unknown_tier_copies": unknown,
    }


def _assign_void_touched(steps: list[tuple[str, int]], available: int) -> dict[str, set[int]]:
    """Give each Void-Touched to the highest remaining tier gap.

    One gap per item before a second gap on the same item, because every
    item's highest gap outranks the next-lower gap.
    """
    assigned: dict[str, set[int]] = {}
    left = max(0, int(available))
    pool = sorted(steps, key=lambda pair: (-pair[1], pair[0]))
    used: set[tuple[str, int]] = set()
    while left > 0 and len(used) < len(pool):
        pick = None
        for item_id, tier in pool:
            if (item_id, tier) in used:
                continue
            pick = (item_id, tier)
            break
        if pick is None:
            break
        used.add(pick)
        assigned.setdefault(pick[0], set()).add(pick[1])
        left -= 1
    return assigned


def _shortfall_hint(grade: int, count: int, remaining: dict[int, int]) -> str | None:
    if grade <= 1 or count <= 0:
        return f"Farm {_NAME_BY_GRADE[grade]} × {count}."
    preview = condense_preview(grade - 1)
    farm = f"Farm {_NAME_BY_GRADE[grade]} × {count}."
    if preview is None:
        return farm
    src = preview["from"]
    held = int(remaining.get(grade - 1) or 0)
    need_src = count * 2
    loss = preview.get("warning")
    step = preview["note"]
    if held >= need_src:
        extra = f" Or condense {need_src} × {src} (you hold {held}). {step}"
    elif held > 0:
        extra = f" Condensing needs {need_src} × {src}; you hold {held}. {step}"
    else:
        extra = f" Condense would take 2 × {src} per mote. {step}"
    if loss:
        extra = f"{extra} {loss}"
    return farm + extra


def plan_upgrades(
    items: list[dict[str, Any]],
    holdings: dict[str, int] | None,
    void_touched: int,
) -> dict[str, Any]:
    """Plan every item against one shared mote pool and one Void-Touched pool."""
    held_by_grade: dict[int, int] = {grade: 0 for grade in range(1, 11)}
    for grade, name in MOTE_GRADES:
        raw = 0
        if holdings:
            if name in holdings:
                raw = holdings[name]
            elif str(grade) in holdings:
                raw = holdings[str(grade)]
        try:
            held_by_grade[grade] = max(0, int(raw))
        except (TypeError, ValueError):
            held_by_grade[grade] = 0
    try:
        vt_pool = max(0, int(void_touched))
    except (TypeError, ValueError):
        vt_pool = 0

    prepared: list[dict[str, Any]] = []
    for index, raw in enumerate(items or []):
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        item_id = str(raw.get("id") or f"{index}:{name}")
        target = _clamp_tier(raw.get("target_tier", 10))
        manual_tier = raw.get("current_tier")
        copy_info = raw.get("copy_info")
        if not isinstance(copy_info, dict):
            copy_info = {"owned": False, "current_tier": None, "tier_known": False,
                         "duplicates": [], "duplicate_xp": 0, "unknown_tier_copies": 0}
        tier_known = bool(copy_info.get("tier_known"))
        if manual_tier is not None and manual_tier != "":
            current = _clamp_tier(manual_tier)
            tier_known = True
            tier_source = "manual"
        elif tier_known and copy_info.get("current_tier") is not None:
            current = _clamp_tier(copy_info.get("current_tier"))
            tier_source = "inventory"
        elif copy_info.get("owned"):
            current = 0
            tier_known = False
            tier_source = "unknown"
        else:
            current = 0
            tier_source = "not_owned"
        try:
            progress = max(0, int(raw.get("progress") or 0))
        except (TypeError, ValueError):
            progress = 0
        step = tier_step_xp(current) if current < 10 else 0
        if step and progress >= step:
            progress = step - 1
        dup_xp = int(copy_info.get("duplicate_xp") or 0) if tier_source != "not_owned" else 0
        before = xp_still_needed(current, target, progress)
        after_tier, after_progress, _left = apply_xp(current, progress, dup_xp, target)
        prepared.append({
            "id": item_id,
            "name": name,
            "slot": raw.get("slot") or "",
            "score": raw.get("score"),
            "owned": bool(copy_info.get("owned")) or tier_source == "manual",
            "tier_source": tier_source,
            "tier_known": tier_known or tier_source in {"manual", "inventory", "not_owned"},
            "start_tier": current,
            "progress": progress,
            "target_tier": target,
            "xp_needed": before,
            "duplicates": copy_info.get("duplicates") or [],
            "duplicate_xp": dup_xp,
            "unknown_tier_copies": int(copy_info.get("unknown_tier_copies") or 0),
            "after_tier": after_tier,
            "after_progress": after_progress,
            "progress_note": (
                "Intra-tier progress is not in the inventory export. It is 0 until you set it."
                if not raw.get("progress") else None
            ),
        })

    steps: list[tuple[str, int]] = []
    for row in prepared:
        # No +N on the export is not +0, so that item does not spend motes.
        if row["tier_source"] == "unknown":
            continue
        tier = row["after_tier"]
        while tier < row["target_tier"]:
            steps.append((row["id"], tier))
            tier += 1
    assigned = _assign_void_touched(steps, vt_pool)

    pool = dict(held_by_grade)
    vt_left = vt_pool
    climbs: dict[str, dict[str, Any]] = {}
    for row in prepared:
        climbs[row["id"]] = {
            "tier": row["after_tier"],
            "progress": row["after_progress"],
            "spent": {grade: 0 for grade in range(1, 11)},
            "vt_tiers": [],
            "stalled": row["tier_source"] == "unknown",
        }

    guard = 0
    while guard < 8000:
        guard += 1
        active = []
        for row in prepared:
            climb = climbs[row["id"]]
            if climb["stalled"] or climb["tier"] >= row["target_tier"]:
                continue
            active.append(row)
        if not active:
            break
        lowest = min(climbs[row["id"]]["tier"] for row in active)
        moved = False
        for row in active:
            climb = climbs[row["id"]]
            if climb["tier"] != lowest:
                continue
            tier = climb["tier"]
            if tier in assigned.get(row["id"], set()) and vt_left > 0:
                climb["tier"] = tier + 1
                climb["progress"] = 0
                climb["vt_tiers"].append(tier)
                vt_left -= 1
                moved = True
                continue
            grades = [grade for grade in legal_grades(tier) if pool.get(grade, 0) > 0]
            if not grades:
                climb["stalled"] = True
                continue
            grade = grades[0]
            pool[grade] -= 1
            climb["spent"][grade] += 1
            nxt, prog, _unused = apply_xp(tier, climb["progress"], _XP_BY_GRADE[grade], row["target_tier"])
            climb["tier"] = nxt
            climb["progress"] = prog
            moved = True
        if not moved:
            break

    results = []
    missing_totals: dict[int, int] = {}
    mote_totals: dict[int, int] = {}
    held_totals: dict[int, int] = {}
    vt_used = 0
    for row in prepared:
        climb = climbs[row["id"]]
        skip = set(assigned.get(row["id"], set()))
        if row["tier_source"] == "unknown":
            unconstrained = []
        else:
            unconstrained = cheapest_motes(row["after_tier"], row["after_progress"], row["target_tier"])
        for entry in unconstrained:
            mote_totals[entry["grade"]] = mote_totals.get(entry["grade"], 0) + entry["count"]
        if row["tier_source"] == "unknown":
            missing = []
        else:
            missing = cheapest_motes(
                climb["tier"], climb["progress"], row["target_tier"], skip_tiers=skip,
            )
        # Held motes already crossed some tiers. Missing is only the rest,
        # and Void-Touched gaps are not listed as mote shortfalls.
        for entry in missing:
            if climb["tier"] >= row["target_tier"]:
                break
            missing_totals[entry["grade"]] = missing_totals.get(entry["grade"], 0) + entry["count"]
            entry["hint"] = _shortfall_hint(entry["grade"], entry["count"], pool)
        if climb["tier"] >= row["target_tier"]:
            missing = []
        spent_rows = _count_rows(climb["spent"])
        for entry in spent_rows:
            held_totals[entry["grade"]] = held_totals.get(entry["grade"], 0) + entry["count"]
        vt_rows = [
            {"tier": tier, "to_tier": tier + 1, "name": VOID_TOUCHED_NAME}
            for tier in climb["vt_tiers"]
        ]
        vt_used += len(vt_rows)
        planned_vt = [
            {"tier": tier, "to_tier": tier + 1, "name": VOID_TOUCHED_NAME}
            for tier in sorted(skip)
        ]
        mote_count = sum(entry["count"] for entry in unconstrained)
        score = row["score"]
        score_per_mote = None
        try:
            if score is not None and mote_count > 0:
                score_per_mote = round(float(score) / mote_count, 4)
        except (TypeError, ValueError):
            score_per_mote = None
        tier_note = None
        if row["tier_source"] == "unknown":
            tier_note = (
                "The inventory export has this item with no +N. "
                "That is not counted as +0. Set the current tier to plan the path."
            )
        elif row["tier_source"] == "not_owned":
            tier_note = "You do not hold this item. The path is the cost from +0 once you have it."
        elif row["unknown_tier_copies"]:
            tier_note = (
                f"{row['unknown_tier_copies']} other "
                f"{'copy has' if row['unknown_tier_copies'] == 1 else 'copies have'} no +N, "
                "so they are not counted as duplicate XP."
            )
        infinite_only = (
            row["after_tier"] == 9
            and row["target_tier"] == 10
            and row["after_progress"] == 0
        )
        results.append({
            **{key: row[key] for key in (
                "id", "name", "slot", "score", "owned", "tier_source", "start_tier",
                "progress", "target_tier", "xp_needed", "duplicates", "duplicate_xp",
                "unknown_tier_copies", "progress_note",
            )},
            "tier_note": tier_note,
            "tier_after_duplicates": row["after_tier"],
            "progress_after_duplicates": row["after_progress"],
            "xp_after_duplicates": xp_still_needed(row["after_tier"], row["target_tier"], row["after_progress"]),
            "motes": unconstrained,
            "mote_count": mote_count,
            "held_motes": spent_rows,
            "void_touched": vt_rows,
            "void_touched_planned": planned_vt,
            "missing": missing if row["tier_source"] != "unknown" else [],
            "path_ready": row["tier_source"] != "unknown",
            "score_per_mote": score_per_mote,
            "high_tier_note": (
                "+9 to +10 at 0 progress is 512 XP. The only legal mote is "
                "Mote of Infinite Potential, or 1 Void-Touched Potential."
                if infinite_only else None
            ),
            "reached": climb["tier"] >= row["target_tier"] and row["tier_source"] != "unknown",
            "reached_tier": climb["tier"],
        })

    def _sort_key(row: dict[str, Any]) -> tuple:
        score = row.get("score_per_mote")
        return (score is None, -(score or 0), str(row.get("slot") or ""), str(row.get("name") or ""))

    return {
        "items": results,
        "by_score_per_mote": sorted(results, key=_sort_key),
        "totals": {
            "xp_needed": sum(int(row["xp_needed"]) for row in results),
            "motes": _count_rows(mote_totals),
            "held_motes": _count_rows(held_totals),
            "missing": _count_rows(missing_totals),
            "void_touched_used": vt_used,
            "void_touched_held": vt_pool,
            "void_touched_unused": max(0, vt_pool - vt_used),
        },
        "holdings": [
            {"grade": grade, "name": _NAME_BY_GRADE[grade], "count": held_by_grade[grade]}
            for grade in range(1, 11)
        ],
        "rules": (
            "XP from +t to +(t+1) is 2^t. Cumulative XP to +T is 2^T − 1. "
            "A duplicate at +k adds 2^k XP. Mote item XP is the Currencies table. "
            "The lowest legal grade is spent first. Void-Touched Potential is reserved "
            "for the highest remaining tier gap across these items."
        ),
        "damage_note": (
            "Stat scaling at +N uses the engine's scale_stats_to_level. "
            "eqlwiki says weapon damage grows 5% per tier and eqlegendstools uses 10%. "
            "This path does not recompute weapon damage; the Best in Slot score is the engine score already on that slot."
        ),
    }
