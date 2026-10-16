"""Tracking dashboards composed from parser rows already stored.

Drop rates, pace, and notable loot use those rows plus catalogs already in
the repo (BiS lists, Plane of Sky tests, eqlwiki quest links, spell buffs).
A missing percent, stat, mob level, or lockout stays unknown. Nothing here
invents a log line or a formula the currencies ledger does not already use.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from typing import Any, Iterable

from ..currencies import weekly_reset
from ..inventory import _MOTE_GRADE_BY_NAME

MULTI_CLASS_CAVEAT = (
    "Level follows each class loadout. Swapping classes can drop the level, "
    "for example 50 then 10. Both readings are kept. This is not one character level."
)

_RAID_KINDS = frozenset({"raid", "mini_boss", "named"})
_XP_HONESTY = (
    "The log records an experience percent, not raw experience points. "
    "Pace is levels of progress. A line with no percent is left out of the sum."
)


def name_key(value: str | None) -> str:
    return " ".join(str(value or "").casefold().split())


def drop_rate(loots: int, kills: int) -> float | None:
    """Your loot lines divided by your kills. No kills means unknown, not zero."""
    if kills <= 0:
        return None
    if loots < 0:
        return None
    return loots / kills


def drop_rates(loots_by_mob: dict[str, int], kills_by_mob: dict[str, int]) -> list[dict[str, Any]]:
    """Per-mob rates. Keys are display names; matching is case-insensitive."""
    order: list[str] = []
    loots: dict[str, int] = {}
    kills: dict[str, int] = {}
    labels: dict[str, str] = {}
    for source, bucket in ((loots_by_mob, loots), (kills_by_mob, kills)):
        for raw, count in source.items():
            key = name_key(raw)
            if not key:
                continue
            labels.setdefault(key, str(raw).strip())
            bucket[key] = bucket.get(key, 0) + int(count)
            if key not in order:
                order.append(key)
    rows = []
    for key in order:
        loot_n = int(loots.get(key) or 0)
        kill_n = int(kills.get(key) or 0)
        rate = drop_rate(loot_n, kill_n)
        rows.append({
            "mob": labels[key],
            "loots": loot_n,
            "kills": kill_n,
            "rate": rate,
            "rate_text": "unknown" if rate is None else f"{loot_n} / {kill_n}",
        })
    rows.sort(key=lambda row: (-row["kills"], row["mob"].casefold()))
    return rows


def mote_grade(item: str | None) -> int | None:
    if not item:
        return None
    return _MOTE_GRADE_BY_NAME.get(item.strip())


def item_key(value: str | None) -> str:
    """Same folding the quest hub uses for item names."""
    from ..quest_links import item_name_key

    return item_name_key(value or "")


def notable_reasons(
    item: str | None,
    *,
    bis_keys: Iterable[str],
    wish_keys: Iterable[str],
    pos_keys: Iterable[str],
    mote_min_grade: int | None,
    is_mote: bool = False,
) -> list[str]:
    """BiS, wish list, mote at or above the chosen grade, or a Plane of Sky item."""
    key = item_key(item)
    if not key:
        return []
    reasons: list[str] = []
    if key in set(bis_keys):
        reasons.append("bis")
    if key in set(wish_keys):
        reasons.append("wish")
    grade = mote_grade(item) if is_mote or mote_grade(item) is not None else None
    if grade is not None and mote_min_grade is not None and grade >= int(mote_min_grade):
        reasons.append("mote")
    if key in set(pos_keys):
        reasons.append("pos")
    return reasons


def toast_for_event(
    event,
    *,
    live: bool,
    bis_keys: Iterable[str],
    wish_keys: Iterable[str],
    pos_keys: Iterable[str],
    mote_min_grade: int | None,
) -> dict[str, Any] | None:
    """One live toast. A replay passes live=False and always gets nothing."""
    if not live or event is None:
        return None
    kind = getattr(event, "kind", None) or (event.get("kind") if isinstance(event, dict) else None)
    if kind == "level":
        level = getattr(event, "level", None) if not isinstance(event, dict) else event.get("level")
        if level is None:
            return None
        return {"kind": "level", "level": int(level), "live": True}
    if kind != "loot":
        return None
    item = getattr(event, "item", None) if not isinstance(event, dict) else event.get("item")
    extra = getattr(event, "extra", None) if not isinstance(event, dict) else (event.get("extra") or {})
    flagged = bool((extra or {}).get("is_mote")) or mote_grade(item) is not None
    reasons = notable_reasons(
        item,
        bis_keys=bis_keys,
        wish_keys=wish_keys,
        pos_keys=pos_keys,
        mote_min_grade=mote_min_grade,
        is_mote=flagged,
    )
    if not reasons or not item:
        return None
    return {"kind": "loot", "item": item, "reasons": reasons, "live": True}


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _pct(value: Any) -> float | None:
    """A missing percent stays missing. Zero is a real logged 0, not a stand-in."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _expand_classes(classes: Iterable[str] | str | None) -> list[str]:
    from ..item_catalog import _CLASS_TOKEN_TO_NAME

    if classes is None:
        return []
    if isinstance(classes, str):
        parts = [part.strip() for part in classes.replace(",", "/").split("/") if part.strip()]
    else:
        parts = []
        for item in classes:
            parts.extend(_expand_classes(item) if isinstance(item, str) and "/" in item else [str(item).strip()])
        return [part for part in parts if part]
    out: list[str] = []
    for part in parts:
        full = _CLASS_TOKEN_TO_NAME.get(part.upper())
        out.append(full or part)
    return out


def level_history(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One segment per loadout. A lower level, or a new class trio, starts another."""
    ordered = sorted(
        (row for row in rows if isinstance(row, dict)),
        key=lambda row: (_as_dt(row.get("ts")) or datetime.min, int(row.get("offset") or 0)),
    )
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def start(row: dict[str, Any]) -> None:
        nonlocal current
        level = row.get("level")
        current = {
            "classes": row.get("classes") or None,
            "start_ts": row.get("ts"),
            "end_ts": row.get("ts"),
            "start_level": level,
            "end_level": level,
            "levels": [level] if level is not None else [],
        }
        segments.append(current)

    for row in ordered:
        evidence = row.get("evidence")
        if evidence == "ability" or (row.get("level") is None and row.get("ability_points")):
            continue
        level = row.get("level")
        classes = row.get("classes") or None
        if current is None:
            start(row)
            continue
        dropped = (
            level is not None
            and current.get("end_level") is not None
            and int(level) < int(current["end_level"])
        )
        class_change = bool(classes and current.get("classes") and classes != current["classes"])
        if dropped or class_change:
            start(row)
            continue
        if classes and not current.get("classes"):
            current["classes"] = classes
        if level is not None:
            current["levels"].append(level)
            current["end_level"] = level
        current["end_ts"] = row.get("ts")
    for segment in segments:
        if not segment.get("classes"):
            segment["classes_note"] = "Classes are unknown until a /who line for this loadout."
    return segments


def _pace(points: list[tuple[datetime, float]]) -> float | None:
    if len(points) < 2:
        return None
    points = sorted(points, key=lambda item: item[0])
    hours = (points[-1][0] - points[0][0]).total_seconds() / 3600.0
    if hours <= 0:
        return None
    total = sum(value for _, value in points)
    return total / hours


def leveling_summary(
    xp_rows: Iterable[dict[str, Any]],
    level_rows: Iterable[dict[str, Any]],
    *,
    classes: Iterable[str] | str | None = None,
    level: int | None = None,
    spells: Iterable[dict[str, Any]] | None = None,
    zone: str | None = None,
    zone_level: str | None = None,
) -> dict[str, Any]:
    """XP per hour as levels of progress, time to level, and AA pace.

    Percent-less experience lines increment nothing. They do not count as 0.
    """
    xp = [row for row in xp_rows if isinstance(row, dict)]
    levels = [row for row in level_rows if isinstance(row, dict)]
    defined: list[tuple[datetime, float]] = []
    missing = 0
    for row in xp:
        pct = _pct(row.get("pct"))
        when = _as_dt(row.get("ts"))
        if pct is None:
            missing += 1
            continue
        if when is None:
            continue
        defined.append((when, pct))

    levels_per_hour = None
    if defined:
        pace = _pace([(when, pct / 100.0) for when, pct in defined])
        levels_per_hour = pace

    level_lines = [
        row for row in levels
        if row.get("level") is not None and row.get("evidence") != "ability"
    ]
    level_lines.sort(key=lambda row: (_as_dt(row.get("ts")) or datetime.min, int(row.get("offset") or 0)))
    last_level_at = _as_dt(level_lines[-1].get("ts")) if level_lines else None
    since = [(when, pct) for when, pct in defined if last_level_at is None or when >= last_level_at]
    missing_since = 0
    for row in xp:
        when = _as_dt(row.get("ts"))
        if _pct(row.get("pct")) is not None or when is None:
            continue
        if last_level_at is None or when >= last_level_at:
            missing_since += 1
    bar_known = missing_since == 0
    progress_pct = sum(pct for _, pct in since) if bar_known else None
    hours_to_level = None
    if bar_known and progress_pct is not None and levels_per_hour and levels_per_hour > 0:
        if progress_pct >= 100:
            hours_to_level = 0.0
        else:
            hours_to_level = ((100.0 - progress_pct) / 100.0) / levels_per_hour

    aa_points: list[tuple[datetime, float]] = []
    aa_total = None
    for row in levels:
        gained = row.get("ability_points")
        if row.get("ability_total") is not None:
            aa_total = row.get("ability_total")
        if not gained:
            continue
        when = _as_dt(row.get("ts"))
        if when is None:
            continue
        aa_points.append((when, float(gained)))
    aa_per_hour = _pace(aa_points)

    selected = _expand_classes(classes)
    current_level = level
    if current_level is None and level_lines:
        current_level = level_lines[-1].get("level")

    return {
        "caveat": MULTI_CLASS_CAVEAT,
        "honesty": _XP_HONESTY,
        "levels_per_hour": levels_per_hour,
        "progress_pct": progress_pct,
        "bar_known": bar_known,
        "hours_to_level": hours_to_level,
        "xp_lines": len(xp),
        "xp_lines_without_percent": missing,
        "aa_per_hour": aa_per_hour,
        "aa_total": aa_total,
        "aa_note": "Ability points are the gained amounts on the log lines. The total is the last 'you now have' number.",
        "history": level_history(levels),
        "new_at_level": spells_new_at_level(spells or [], selected, current_level),
        "classes": selected,
        "level": current_level,
        "zone_band": {
            "zone": zone or None,
            "level_requirement": zone_level or None,
            "status": "sourced" if zone_level else "unknown",
            "note": None if zone_level else "No sourced level band for this zone is in the app data.",
        },
    }


def spells_new_at_level(
    buffs: Iterable[dict[str, Any]],
    classes: Iterable[str],
    level: int | None,
) -> list[dict[str, Any]]:
    """Spells whose sourced cast level equals this level. Unsourced rows are omitted."""
    if level is None:
        return []
    try:
        want_level = int(level)
    except (TypeError, ValueError):
        return []
    selected = {name.casefold(): name for name in classes if name}
    if not selected:
        return []
    found: list[dict[str, Any]] = []
    for buff in buffs:
        if not isinstance(buff, dict):
            continue
        by = buff.get("levels_by_class") or {}
        source = buff.get("level_source")
        if not by and not source:
            continue
        name = buff.get("name") or ""
        if not name:
            continue
        if isinstance(by, dict) and by:
            for raw_class, raw_level in by.items():
                label = str(raw_class).strip()
                if label.casefold() not in selected:
                    continue
                try:
                    cast_at = int(raw_level)
                except (TypeError, ValueError):
                    continue
                if cast_at != want_level:
                    continue
                found.append({
                    "name": name,
                    "class": selected[label.casefold()],
                    "level": cast_at,
                    "source": source or "levels_by_class",
                })
            continue
        if not source or buff.get("level") is None:
            continue
        try:
            cast_at = int(buff.get("level"))
        except (TypeError, ValueError):
            continue
        if cast_at != want_level:
            continue
        for class_name in buff.get("classes") or []:
            label = str(class_name).strip()
            if label.casefold() not in selected:
                continue
            found.append({
                "name": name,
                "class": selected[label.casefold()],
                "level": cast_at,
                "source": source,
            })
    found.sort(key=lambda row: (row["class"], row["name"]))
    return found


def lockout_week(now: datetime) -> dict[str, Any]:
    """The currencies Tuesday reset. Other raid lockouts are not inferred from it."""
    reset = weekly_reset(now)
    return {
        "source": "currencies.weekly_reset",
        "note": (
            "Same Tuesday 8:00 AM Pacific reset as Void-Touched Potential, shown in Central time. "
            "eqlwiki does not state a lockout for every raid. Any other lockout stays UNVERIFIED until you enter it."
        ),
        "last_reset": reset["last_reset"].isoformat(),
        "next_reset": reset["next_reset"].isoformat(),
        "countdown_label": reset["countdown_label"],
        "ct_clock": reset["ct_clock"],
    }


def _in_fight(when: datetime | None, fight: dict[str, Any]) -> bool:
    if when is None:
        return False
    start = _as_dt(fight.get("start_ts"))
    end = _as_dt(fight.get("end_ts"))
    if start is None:
        return False
    if end is None:
        return bool(fight.get("open")) and when >= start
    return start <= when <= end


def raid_kills(
    slain: Iterable[dict[str, Any]],
    fights: Iterable[dict[str, Any]],
    mobs_by_key: dict[str, dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """Named, mini-boss, and raid kills. Difficulty is the instance tier already on the fight."""
    fight_rows = [row for row in fights if isinstance(row, dict)]
    kills = []
    for row in slain:
        if not isinstance(row, dict):
            continue
        mob = str(row.get("mob") or row.get("target") or "").strip()
        key = name_key(mob)
        info = mobs_by_key.get(key)
        if not info:
            continue
        kinds = [kind for kind in (info.get("kinds") or []) if kind in _RAID_KINDS]
        if not kinds:
            continue
        when = _as_dt(row.get("ts"))
        match = None
        for fight in fight_rows:
            targets = [name_key(name) for name in (fight.get("targets") or [])]
            if key not in targets and targets:
                continue
            if _in_fight(when, fight):
                match = fight
                break
        if match is None:
            for fight in fight_rows:
                if _in_fight(when, fight):
                    match = fight
                    break
        instance = (match or {}).get("instance") if match else None
        tier = None
        if isinstance(instance, dict):
            tier = instance.get("tier") or None
        kills.append({
            "ts": row.get("ts"),
            "mob": info.get("name") or mob,
            "kinds": kinds,
            "zone": (match or {}).get("zone") or None,
            "instance": instance if isinstance(instance, dict) else None,
            "difficulty": tier or "unknown",
        })
    kills.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
    return {"lockout_week": lockout_week(now), "kills": kills}


def curve_from_timeline(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not payload.get("available"):
        reason = (payload or {}).get("reason") or "No DPS curve is stored for this fight."
        return {"available": False, "buckets": [], "bin_seconds": None, "reason": reason}
    buckets = []
    for row in payload.get("buckets") or []:
        if not isinstance(row, dict):
            continue
        buckets.append({"t": row.get("t"), "you": int(row.get("you") or 0)})
    return {
        "available": True,
        "bin_seconds": payload.get("bin_seconds"),
        "buckets": buckets,
        "reason": None,
    }


def overview_cards(
    *,
    fight: dict[str, Any] | None,
    targets_alive: list[str],
    targets_dead: list[str],
    recent_loots: list[dict[str, Any]],
    recent_kills: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    leveling: dict[str, Any],
) -> dict[str, Any]:
    open_fight = bool(fight and fight.get("open"))
    current = targets_alive if open_fight else []
    return {
        "current_mob": {
            "names": current,
            "status": "fighting" if current else ("between fights" if fight else "no fight yet"),
            "last_targets": targets_dead if open_fight else (targets_alive + targets_dead),
            "zone": (fight or {}).get("zone") or None,
            "open": open_fight,
        },
        "dps": {
            "fight_id": (fight or {}).get("id"),
            "your_dps": (fight or {}).get("your_dps") if fight else None,
            "your_damage": (fight or {}).get("your_damage") if fight else None,
            "duration_seconds": (fight or {}).get("duration_seconds") if fight else None,
            "zone": (fight or {}).get("zone") or None,
            "targets": (fight or {}).get("targets") or [],
        },
        "leveling": {
            "levels_per_hour": leveling.get("levels_per_hour"),
            "hours_to_level": leveling.get("hours_to_level"),
            "level": leveling.get("level"),
            "classes": leveling.get("classes") or [],
            "caveat": leveling.get("caveat"),
            "bar_known": leveling.get("bar_known"),
        },
        "recent_loots": recent_loots,
        "recent_kills": recent_kills,
        "zones": zones,
    }


@lru_cache(maxsize=1)
def bis_name_keys() -> frozenset[str]:
    """Item names that appear on a decoded per-class BiS list."""
    from ..paths import decoded_dir

    keys: set[str] = set()
    root = decoded_dir()
    if not root.exists():
        return frozenset()
    for path in root.glob("bis_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = data if isinstance(data, list) else []
        for row in rows:
            if isinstance(row, dict) and row.get("name"):
                keys.add(item_key(row["name"]))
    return frozenset(keys)


@lru_cache(maxsize=1)
def pos_item_keys() -> frozenset[str]:
    from ..quest_links import item_name_key, pos_tests

    keys: set[str] = set()
    for test in pos_tests():
        reward = test.get("reward") or ""
        if item_name_key(reward):
            keys.add(item_name_key(reward))
        for item in test.get("items") or []:
            raw = item.get("name") if isinstance(item, dict) else item
            if item_name_key(raw):
                keys.add(item_name_key(raw))
    return frozenset(keys)


def _pos_key(name: str | None) -> str:
    from ..quest_links import item_name_key

    return item_name_key(name or "")


def quest_flags_for(name: str | None) -> list[dict[str, str]]:
    from ..quest_links import pos_quests_for_item, related_links_for_item

    flags: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in related_links_for_item(name or ""):
        quest = (link.get("name") or "").strip()
        if not quest or quest.casefold() in seen:
            continue
        seen.add(quest.casefold())
        flags.append({"quest": quest, "source": "eqlwiki"})
    for quest in pos_quests_for_item(name or ""):
        if quest.casefold() in seen:
            continue
        seen.add(quest.casefold())
        flags.append({"quest": quest, "source": "plane of sky"})
    return flags


def item_knowledge(name: str | None) -> dict[str, Any]:
    """Catalog stats when the name is already decoded. Otherwise unknown."""
    label = (name or "").strip()
    flags = quest_flags_for(label) if label else []
    if not label:
        return {"name": None, "known": False, "stats": None, "quests": [], "note": "unknown"}
    row = None
    try:
        from ..item_catalog import get_item_by_name

        row = get_item_by_name(label, enrich=False)
    except Exception:
        row = None
    stats = None
    display = label
    slot = None
    if isinstance(row, dict):
        display = row.get("name") or label
        slot = row.get("slot") or None
        raw_stats = row.get("stats_plus0") or {}
        if isinstance(raw_stats, dict) and raw_stats:
            stats = raw_stats
    return {
        "name": display,
        "known": stats is not None,
        "stats": stats,
        "slot": slot,
        "quests": flags,
        "note": None if stats is not None else "No sourced stats for this name.",
    }


def annotate_loot_row(
    row: dict[str, Any],
    *,
    bis_keys: Iterable[str],
    wish_keys: Iterable[str],
    pos_keys: Iterable[str],
    favourite_keys: Iterable[str],
    mote_min_grade: int | None,
    knowledge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = row.get("item")
    reasons = notable_reasons(
        item,
        bis_keys=bis_keys,
        wish_keys=wish_keys,
        pos_keys=pos_keys,
        mote_min_grade=mote_min_grade,
        is_mote=bool(row.get("is_mote")),
    )
    if knowledge is None:
        info = item_knowledge(item) if item else {
            "name": None,
            "known": False,
            "stats": None,
            "quests": [],
            "note": "unknown",
        }
    else:
        info = knowledge
    payload = dict(row)
    payload["notable"] = reasons
    payload["favourite"] = item_key(item) in set(favourite_keys) if item else False
    payload["knowledge"] = info
    return payload


def mob_index_by_key() -> dict[str, dict[str, Any]]:
    from ..mob_hub import list_mobs

    out: dict[str, dict[str, Any]] = {}
    for row in list_mobs():
        key = name_key(row.get("name"))
        if key:
            out[key] = row
    return out


def zone_level_requirement(zone: str | None) -> str | None:
    """Sourced zone level text only. A missing research file stays unknown."""
    if not zone:
        return None
    try:
        from .. import zones as zones_mod
    except Exception:
        return None
    loader = getattr(zones_mod, "zone_detail", None)
    if not callable(loader):
        return None
    try:
        detail = loader(zone)
    except Exception:
        return None
    if not isinstance(detail, dict):
        return None
    overview = detail.get("overview") if isinstance(detail.get("overview"), dict) else {}
    raw = overview.get("level_requirement") or detail.get("level_requirement") or ""
    text = str(raw).strip()
    return text or None


def parse_mote_grade_setting(raw: str | None) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        grade = int(str(raw).strip())
    except ValueError:
        return None
    if grade < 1 or grade > 10:
        return None
    return grade
