"""Companion views over log lines and decoded data.

Durations, respawn seconds, map coordinates, exaltation ranks, and resist
caps are never filled in. A missing source stays unknown. User-entered
numbers are stored and labeled as such. Level and class numbers are keyed
by loadout, so swapping a trio does not reuse the other trio's entries.
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from datetime import datetime
from typing import Any, Callable, Iterable

from ..character_pools import RESIST_KEYS, compute_pools
from ..engine import scale_stats_to_level
from ..inventory import EXALTATION_SOCKET_LABELS
from ..races import class_stat_rows, race_bases
from ..version import __version__

PROFILE_KIND = "eq-legends-bis-profile"
PROFILE_VERSION = 1

BUFF_NOTE = (
    "A cast line does not start a timer. Slow, charm, and rune lines do. "
    "A worn-off line closes a matching spell. Duration is a number you enter "
    "for this class loadout, or the time between a start and a worn-off line "
    "already in your log. Anything else is unknown."
)
RESPAWN_NOTE = (
    "Respawn time is a number you enter. The log supplies the last kill and, "
    "when the kill sits inside a saved fight, the zone. Time between two kills "
    "is not a respawn."
)
MAP_NOTE = (
    "A map link or mob location is shown only when a zone-research file already "
    "has it. Otherwise it is unknown."
)
EXALTATION_NOTE = (
    "Sockets are the Slot7–10 labels already on the inventory import. Those role "
    "names are unconfirmed. Stats appear only when the catalog already has them. "
    "No best exaltation is chosen. A target you type is kept on this class loadout."
)
RESIST_NOTE = (
    "Resists are race saves from the decoded char sheet plus catalog stats on "
    "worn items, scaled with the existing upgrade curve. A missing item or race "
    "is unknown and is not added as 0. Resist cap is unknown. The Warrior +25 "
    "magic save and the max-AA bonus are the char-sheet pool formula, and only "
    "when that class or the AA switch is on for this loadout."
)
SHARE_NOTE = "Sign-in tokens are left out of an exported profile and out of a feedback zip."

_SECRET_KEY = re.compile(
    r"token|secret|password|authorization|credential|cookie|api_key|refresh",
    re.IGNORECASE,
)
_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_SECRET_ASSIGN = re.compile(
    r"(?i)(refresh_token|access_token|id_token|client_secret|authorization)"
    r"(['\"]?\s*[:=]\s*['\"]?)([^'\"\s,&]+)"
)
_EXALTATION_NAME = re.compile(r"(?i)\(Exaltation\)\s*$")
_LOG_NAMES = {
    "eq-api.log",
    "eq-api.log.1",
    "main.log",
    "main.log.1",
    "parser-stall.log",
}
_RESIST_GEAR = ("SVF", "SVC", "SVM", "SVP", "SVD", "SVV")
_SOCKET_LABELS = set(EXALTATION_SOCKET_LABELS.values())
_MAX_SECONDS = 7 * 24 * 3600


def loadout_key(classes: Iterable[str] | None, level: Any) -> str:
    """Identity of one 3-class loadout. Order is the order the user selected."""
    names = [str(name).strip() for name in (classes or []) if str(name).strip()]
    level_text = "unknown" if level is None or level == "" else str(int(level))
    if not names:
        return f"unknown classes @ {level_text}"
    return f"{' / '.join(names)} @ {level_text}"


def parse_user_seconds(value: Any) -> int | None:
    """A duration or respawn the user typed, in whole seconds. Blank clears it."""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("enter whole seconds")
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("enter whole seconds") from exc
    if seconds < 1 or seconds > _MAX_SECONDS:
        raise ValueError("enter seconds from 1 through 604800")
    return seconds


def _stamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _seconds_between(start: Any, end: Any) -> int | None:
    a = _stamp(start)
    b = _stamp(end)
    if a is None or b is None:
        return None
    if a.tzinfo is not None and b.tzinfo is None:
        return None
    if b.tzinfo is not None and a.tzinfo is None:
        return None
    return int((b - a).total_seconds())


def _fold(value: Any) -> str:
    return str(value or "").strip().casefold()


def _duration_for(durations: dict[str, Any] | None, name: str) -> int | None:
    if not isinstance(durations, dict):
        return None
    for key, value in durations.items():
        if _fold(key) == _fold(name):
            try:
                return parse_user_seconds(value)
            except ValueError:
                return None
    return None


def _effect_row(
    *,
    name: str,
    target: str,
    side: str,
    started: Any,
    source: str,
    amount: Any = None,
    spell: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "spell": spell,
        "target": target or None,
        "side": side,
        "started": started,
        "source": source,
        "amount": amount,
    }


def buff_timers(
    events: Iterable[dict[str, Any]],
    *,
    loadout: str,
    durations: dict[str, Any] | None = None,
    manual: Iterable[dict[str, Any]] | None = None,
    now: Any = None,
) -> dict[str, Any]:
    """Open and close timers from classified lines plus this loadout's numbers.

    ``durations`` is only the map for ``loadout``. Another loadout's numbers
    must not be passed in.
    """
    active: dict[tuple[str, str], dict[str, Any]] = {}
    recent: list[dict[str, Any]] = []

    def remember(row: dict[str, Any]) -> None:
        active[(_fold(row["name"]), _fold(row.get("target")))] = row

    def close_match(name: str, target: str, ended: Any, text: str) -> None:
        found = active.pop((_fold(name), _fold(target)), None)
        if found is None:
            recent.append({
                "name": name,
                "target": target or None,
                "started": None,
                "ended": ended,
                "observed_seconds": None,
                "remaining_text": "unknown",
                "note": text,
            })
            return
        observed = _seconds_between(found.get("started"), ended)
        recent.append({
            "name": found["name"],
            "target": found.get("target"),
            "started": found.get("started"),
            "ended": ended,
            "observed_seconds": observed,
            "remaining_text": "ended",
            "source": found.get("source"),
            "note": "Observed from your log." if observed is not None else "Ended. The start time was missing, so the length is unknown.",
        })

    timeline: list[tuple[str, str, int, dict[str, Any]]] = []
    for event in events or []:
        timeline.append(("log", str(event.get("ts") or ""), int(event.get("offset") or 0), event))
    for row in manual or []:
        if str(row.get("loadout") or "") != loadout:
            continue
        timeline.append(("manual", str(row.get("started") or ""), 0, row))
    timeline.sort(key=lambda item: (item[1], 0 if item[0] == "manual" else 1, item[2]))

    for origin, _ts, _offset, event in timeline:
        if origin == "manual":
            spell = str(event.get("spell") or "").strip()
            if not spell:
                continue
            target = str(event.get("target") or "You").strip() or "You"
            remember(_effect_row(
                name=spell,
                target=target,
                side="buff",
                started=event.get("started"),
                source="user",
                spell=spell,
            ))
            if event.get("duration_seconds") is not None:
                active[(_fold(spell), _fold(target))]["manual_duration"] = event.get("duration_seconds")
            continue
        kind = event.get("kind")
        ts = event.get("ts")
        if kind == "slow":
            target = event.get("target") or event.get("source") or ""
            remember(_effect_row(
                name="Slow",
                target=target,
                side="debuff",
                started=ts,
                source="log",
                spell=None,
            ))
        elif kind == "charm":
            remember(_effect_row(
                name="Charm",
                target=event.get("target") or "",
                side="debuff",
                started=ts,
                source="log",
                spell="Charm",
            ))
        elif kind == "rune":
            remember(_effect_row(
                name="Rune",
                target="You",
                side="buff",
                started=ts,
                source="log",
                amount=event.get("amount"),
            ))
        elif kind == "charm_break":
            target = str(event.get("target") or "").strip()
            if target:
                close_match("Charm", target, ts, "Charm break line.")
            else:
                charms = [key for key in list(active) if key[0] == "charm"]
                if len(charms) == 1:
                    row = active.pop(charms[0])
                    observed = _seconds_between(row.get("started"), ts)
                    recent.append({
                        "name": row["name"],
                        "target": row.get("target"),
                        "started": row.get("started"),
                        "ended": ts,
                        "observed_seconds": observed,
                        "remaining_text": "ended",
                        "source": row.get("source"),
                        "note": "Observed from your log.",
                    })
                else:
                    recent.append({
                        "name": "Charm",
                        "target": None,
                        "started": None,
                        "ended": ts,
                        "observed_seconds": None,
                        "remaining_text": "unknown",
                        "note": "The charm break line named no mob, so no open charm was closed.",
                    })
        elif kind == "spell_fade":
            spell = str(event.get("spell") or "").strip()
            target = str(event.get("target") or "").strip()
            if not spell:
                continue
            close_match(
                spell,
                target,
                ts,
                "The log shows this spell wore off. No matching start was tracked, so the duration is unknown.",
            )

    shown = []
    for row in active.values():
        manual_duration = row.pop("manual_duration", None)
        duration = None
        if manual_duration is not None:
            try:
                duration = parse_user_seconds(manual_duration)
            except ValueError:
                duration = None
        if duration is None:
            duration = _duration_for(durations, row["name"])
        elapsed = _seconds_between(row.get("started"), now)
        remaining = None if duration is None or elapsed is None else duration - elapsed
        shown.append({
            **row,
            "loadout": loadout,
            "duration_seconds": duration,
            "duration_source": None if duration is None else "user",
            "elapsed_seconds": elapsed,
            "remaining_seconds": remaining,
            "remaining_text": "unknown" if remaining is None else str(remaining),
        })
    shown.sort(key=lambda row: (str(row.get("started") or ""), row["name"]))
    return {
        "loadout": loadout,
        "active": shown,
        "recent": recent[-30:],
        "note": BUFF_NOTE,
    }


def respawn_key(zone: str | None, mob: str) -> str:
    return f"{_fold(zone)}\n{_fold(mob)}"


def respawn_timers(
    kills: Iterable[dict[str, Any]],
    user_seconds: dict[str, Any] | None = None,
    *,
    now: Any = None,
) -> dict[str, Any]:
    """Latest kill per zone and mob. Respawn seconds only when the user entered them."""
    latest: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    ordered = sorted(
        list(kills or []),
        key=lambda row: (str(row.get("ts") or ""), int(row.get("offset") or 0)),
    )
    for kill in ordered:
        mob = str(kill.get("mob") or "").strip()
        if not mob:
            continue
        zone = str(kill.get("zone") or "").strip()
        key = respawn_key(zone, mob)
        counts[key] = counts.get(key, 0) + 1
        latest[key] = {
            "zone": zone or None,
            "zone_text": zone or "unknown",
            "mob": mob,
            "last_kill": kill.get("ts"),
            "kills": counts[key],
        }
    rows = []
    entered = user_seconds if isinstance(user_seconds, dict) else {}
    for key, value in entered.items():
        if key in latest or not isinstance(value, dict):
            continue
        mob = str(value.get("mob") or "").strip()
        if not mob:
            continue
        zone = str(value.get("zone") or "").strip()
        latest[key] = {
            "zone": zone or None,
            "zone_text": zone or "unknown",
            "mob": mob,
            "last_kill": None,
            "kills": 0,
        }
    for key, row in latest.items():
        raw = None
        for item_key, value in entered.items():
            if item_key == key or _fold(item_key) == _fold(key):
                raw = value.get("seconds") if isinstance(value, dict) else value
                break
        seconds = None
        if raw is not None and raw != "":
            try:
                seconds = parse_user_seconds(raw)
            except ValueError:
                seconds = None
        elapsed = _seconds_between(row["last_kill"], now)
        remaining = None if seconds is None or elapsed is None else seconds - elapsed
        rows.append({
            **row,
            "respawn_seconds": seconds,
            "respawn_source": None if seconds is None else "user",
            "remaining_seconds": remaining,
            "remaining_text": "unknown" if remaining is None else str(remaining),
        })
    rows.sort(key=lambda row: (row["zone_text"], row["mob"].casefold()))
    return {"rows": rows, "note": RESPAWN_NOTE}


def map_rows(
    seen: Iterable[dict[str, Any]],
    lookup: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    """Zones from the log, enriched only by an existing zone-research file."""
    rows = []
    seen_names = set()
    for item in seen or []:
        name = str(item.get("zone") or "").strip()
        if not name or name.casefold() in seen_names:
            continue
        seen_names.add(name.casefold())
        detail = None
        try:
            detail = lookup(name)
        except Exception:
            detail = None
        overview = (detail or {}).get("overview") or {}
        map_url = str((detail or {}).get("map_url") or "").strip()
        mobs = []
        for mob in (detail or {}).get("mobs") or []:
            level = mob.get("level")
            level_known = level not in (None, "")
            coords = mob.get("coords")
            spawn_known = bool(mob.get("spawn_known"))
            mobs.append({
                "name": mob.get("name") or "",
                "level": level if level_known else None,
                "level_text": str(level) if level_known else "unknown",
                "coords": coords if coords else None,
                "location_text": "unknown" if not coords and not spawn_known else (mob.get("spawn_notes") or ""),
            })
        level_req = overview.get("level_requirement") or ""
        rows.append({
            "zone": (detail or {}).get("zone") or name,
            "seen": True,
            "last_ts": item.get("ts"),
            "instance": item.get("instance"),
            "map_url": map_url or None,
            "map_text": map_url or "unknown",
            "brief": overview.get("brief") or None,
            "level_requirement": level_req or None,
            "level_requirement_text": level_req or "unknown",
            "mobs": mobs,
            "research": bool(detail),
            "note": None if detail else "No zone file is on disk for this name. The map and mob locations are unknown.",
        })
    return {"zones": rows, "note": MAP_NOTE}


def _is_exaltation_row(row: dict[str, Any]) -> bool:
    name = str(row.get("name") or row.get("name_raw") or "")
    label = row.get("socket_label")
    if _EXALTATION_NAME.search(name):
        return True
    return bool(label) and str(label) in _SOCKET_LABELS


def exaltation_socket_key(row: dict[str, Any]) -> str:
    label = str(row.get("socket_label") or "loose")
    location = str(row.get("location_raw") or "")
    name = str(row.get("name") or row.get("name_raw") or "")
    return f"{location}|{label}|{name}"


def exaltation_plan(
    items: Iterable[dict[str, Any]],
    *,
    loadout: str,
    notes: dict[str, Any] | None = None,
    stat_lookup: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """List exaltation sockets and names. Stats only from ``stat_lookup``."""
    lookup = stat_lookup or (lambda _name: None)
    note_map = notes if isinstance(notes, dict) else {}
    rows = []
    for item in items or []:
        if not isinstance(item, dict) or not _is_exaltation_row(item):
            continue
        name = str(item.get("name") or item.get("name_raw") or "").strip()
        key = exaltation_socket_key(item)
        stats = lookup(name) if name else None
        if not isinstance(stats, dict) or not stats:
            stats = None
        target = ""
        for note_key, value in note_map.items():
            if note_key == key:
                target = str(value or "").strip()
                break
        target_stats = lookup(target) if target else None
        if not isinstance(target_stats, dict) or not target_stats:
            target_stats = None
        rows.append({
            "key": key,
            "loadout": loadout,
            "socket_label": item.get("socket_label") or "unknown",
            "location": item.get("location_raw") or "",
            "name": name or "unknown",
            "tier": item.get("tier"),
            "stats": stats,
            "stats_text": None if stats else "unknown",
            "target": target,
            "target_stats": target_stats,
            "target_stats_text": None if not target else (None if target_stats else "unknown"),
        })
    return {"loadout": loadout, "rows": rows, "note": EXALTATION_NOTE}


def resist_profile(
    *,
    loadout: str,
    classes: list[str],
    level: Any,
    race: str | None,
    worn: Iterable[dict[str, Any]],
    stat_lookup: Callable[[str], dict[str, Any] | None],
    assume_max_aas: bool = False,
) -> dict[str, Any]:
    """Resist parts for one loadout. Missing catalog rows and an unknown race stay unknown."""
    gear = {key: 0.0 for key in _RESIST_GEAR}
    unknown_items: list[str] = []
    used: list[dict[str, Any]] = []
    for row in worn or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        stats0 = stat_lookup(name)
        if not isinstance(stats0, dict) or not stats0:
            unknown_items.append(name)
            continue
        upgrade = row.get("upgrade")
        plus0 = upgrade is None or upgrade == ""
        try:
            upgrade_level = 0 if plus0 else max(0, min(10, int(upgrade)))
        except (TypeError, ValueError):
            plus0 = True
            upgrade_level = 0
        scaled = scale_stats_to_level(stats0, upgrade_level)
        part = {}
        for key in _RESIST_GEAR:
            if key in scaled and scaled[key] is not None:
                try:
                    part[key] = float(scaled[key])
                except (TypeError, ValueError):
                    continue
                gear[key] += part[key]
        used.append({
            "slot": row.get("slot") or "",
            "name": name,
            "upgrade": upgrade_level,
            "upgrade_note": "+0 catalog stats because this copy has no +N." if plus0 else None,
            "resists": part,
        })

    bases = race_bases(race) if race else {}
    race_known = bool(bases)
    race_part: dict[str, Any] = {}
    for key in RESIST_KEYS:
        race_part[key] = bases.get(key) if race_known else None
    race_part["SVV"] = None

    warrior = 25 if "Warrior" in (classes or []) else 0
    aa = None
    totals: dict[str, Any] = {}
    partial = bool(unknown_items)
    if race_known:
        pooled = compute_pools(
            classes=list(classes or []),
            race_attrs={key: bases.get(key, 0) for key in ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA")},
            race_resists={key: bases.get(key, 0) for key in RESIST_KEYS},
            class_stat_rows=class_stat_rows(list(classes or [])),
            gear_stats=dict(gear),
            buff_stats={},
            assume_max_aas=bool(assume_max_aas),
        )
        pool_totals = pooled.get("totals") or {}
        aa = (pooled.get("breakdown") or {}).get("resist_aa")
        for key in list(RESIST_KEYS) + ["SVV"]:
            totals[key] = pool_totals.get(key)
    else:
        aa = None
        for key in list(RESIST_KEYS) + ["SVV"]:
            totals[key] = None

    return {
        "loadout": loadout,
        "level": None if level is None or level == "" else int(level),
        "classes": list(classes or []),
        "race": race or None,
        "race_known": race_known,
        "race_resists": race_part,
        "gear": gear,
        "items": used,
        "unknown_items": unknown_items,
        "partial": partial,
        "warrior_svm": warrior,
        "warrior_note": "Warrior innate +25 SV Magic from the char-sheet pool." if warrior else None,
        "resist_aa": aa if assume_max_aas else 0,
        "resist_aa_note": (
            "Max-AA resist bonus from the char-sheet pool. This is an assumption you turned on, not a measured AA."
            if assume_max_aas else
            "Max-AA resist bonus is off, so it is not added."
        ),
        "totals": totals,
        "totals_text": "unknown" if not race_known else ("partial" if partial else None),
        "svv_note": "Racial SVV is not in the sourced race saves, so SVV here is gear only.",
        "cap": None,
        "cap_text": "unknown",
        "note": RESIST_NOTE,
    }


def empty_blob() -> dict[str, Any]:
    return {
        "durations": {},
        "respawns": {},
        "manual_buffs": [],
        "exaltation_notes": {},
        "resist_profiles": {},
    }


def normalize_blob(raw: Any) -> dict[str, Any]:
    base = empty_blob()
    if not isinstance(raw, dict):
        return base
    if isinstance(raw.get("durations"), dict):
        base["durations"] = raw["durations"]
    if isinstance(raw.get("respawns"), dict):
        base["respawns"] = raw["respawns"]
    if isinstance(raw.get("manual_buffs"), list):
        base["manual_buffs"] = [row for row in raw["manual_buffs"] if isinstance(row, dict)]
    if isinstance(raw.get("exaltation_notes"), dict):
        base["exaltation_notes"] = raw["exaltation_notes"]
    if isinstance(raw.get("resist_profiles"), dict):
        base["resist_profiles"] = raw["resist_profiles"]
    return base


def durations_for_loadout(blob: dict[str, Any], loadout: str) -> dict[str, Any]:
    raw = (blob.get("durations") or {}).get(loadout)
    return raw if isinstance(raw, dict) else {}


def set_duration(blob: dict[str, Any], loadout: str, spell: str, seconds: int | None) -> None:
    spell = spell.strip()
    if not spell:
        raise ValueError("spell name is required")
    if seconds is not None:
        seconds = parse_user_seconds(seconds)
    bucket = blob.setdefault("durations", {}).setdefault(loadout, {})
    if not isinstance(bucket, dict):
        bucket = {}
        blob["durations"][loadout] = bucket
    if seconds is None:
        for key in list(bucket):
            if _fold(key) == _fold(spell):
                del bucket[key]
        return
    bucket[spell] = seconds


def set_respawn(blob: dict[str, Any], zone: str, mob: str, seconds: int | None) -> None:
    mob = mob.strip()
    if not mob:
        raise ValueError("mob name is required")
    if seconds is not None:
        seconds = parse_user_seconds(seconds)
    key = respawn_key(zone, mob)
    respawns = blob.setdefault("respawns", {})
    if seconds is None:
        respawns.pop(key, None)
        return
    respawns[key] = {"zone": zone.strip(), "mob": mob, "seconds": seconds}


def respawn_seconds_map(blob: dict[str, Any]) -> dict[str, int]:
    out = {}
    for key, value in (blob.get("respawns") or {}).items():
        if isinstance(value, dict) and value.get("seconds") is not None:
            out[key] = int(value["seconds"])
        elif isinstance(value, int):
            out[key] = value
    return out


def redact(value: Any) -> Any:
    """Drop secret-shaped keys and bearer strings. Other values pass through."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if _SECRET_KEY.search(str(key)):
                continue
            out[str(key)] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if value.lower().startswith("bearer "):
            return ""
        return _SECRET_ASSIGN.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", value)
    return value


def export_profile(blob: dict[str, Any], ui: dict[str, Any] | None, character: str) -> dict[str, Any]:
    clean = normalize_blob(blob)
    return redact({
        "v": PROFILE_VERSION,
        "kind": PROFILE_KIND,
        "app": __version__,
        "character": character,
        "durations": clean["durations"],
        "respawns": clean["respawns"],
        "manual_buffs": clean["manual_buffs"],
        "exaltation_notes": clean["exaltation_notes"],
        "resist_profiles": clean["resist_profiles"],
        "ui": ui or {},
        "note": SHARE_NOTE,
    })


def import_profile(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("profile is not a JSON object")
    if payload.get("v") != PROFILE_VERSION or payload.get("kind") != PROFILE_KIND:
        raise ValueError("not an EQ Legends BiS profile")
    clean = redact(payload)
    return normalize_blob({
        "durations": clean.get("durations"),
        "respawns": clean.get("respawns"),
        "manual_buffs": clean.get("manual_buffs"),
        "exaltation_notes": clean.get("exaltation_notes"),
        "resist_profiles": clean.get("resist_profiles"),
    }) | {"ui": clean.get("ui") if isinstance(clean.get("ui"), dict) else {}}


def merge_profile(blob: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Union by key. A null duration or respawn in the file clears that one entry."""
    base = normalize_blob(blob)
    extra = normalize_blob(incoming)
    for loadout, spells in (extra.get("durations") or {}).items():
        if not isinstance(spells, dict):
            continue
        for spell, seconds in spells.items():
            set_duration(base, str(loadout), str(spell), None if seconds is None else parse_user_seconds(seconds))
    for key, value in (extra.get("respawns") or {}).items():
        if isinstance(value, dict):
            zone = str(value.get("zone") or "")
            mob = str(value.get("mob") or "")
            seconds = value.get("seconds")
        else:
            zone, _, mob = str(key).partition("\n")
            seconds = value
        if not mob:
            continue
        set_respawn(base, zone, mob, None if seconds is None else parse_user_seconds(seconds))
    notes = base.setdefault("exaltation_notes", {})
    for loadout, rows in (extra.get("exaltation_notes") or {}).items():
        if isinstance(rows, dict):
            bucket = notes.setdefault(str(loadout), {})
            if isinstance(bucket, dict):
                bucket.update({str(k): ("" if v is None else str(v)) for k, v in rows.items()})
    profiles = base.setdefault("resist_profiles", {})
    for loadout, rows in (extra.get("resist_profiles") or {}).items():
        if isinstance(rows, list):
            profiles[str(loadout)] = redact(rows)
    manuals = list(base.get("manual_buffs") or [])
    seen = {str(row.get("id")) for row in manuals if row.get("id")}
    for row in extra.get("manual_buffs") or []:
        if row.get("id") and str(row["id"]) in seen:
            continue
        manuals.append(redact(row))
    base["manual_buffs"] = manuals
    return base


def scrub_log_text(text: str) -> str:
    cleaned = _BEARER.sub("Bearer [redacted]", text or "")
    return _SECRET_ASSIGN.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", cleaned)


def safe_log_name(name: str) -> str | None:
    base = str(name or "").replace("\\", "/").split("/")[-1]
    if base in _LOG_NAMES:
        return base
    return None


def perf_readout() -> dict[str, Any]:
    """Process measurements. A unit we cannot name stays unknown."""
    out: dict[str, Any] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "pid": None,
        "rss_bytes": None,
        "rss_text": "unknown",
    }
    try:
        import os
        out["pid"] = os.getpid()
    except Exception:
        out["pid"] = None
    try:
        import resource
        raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform.startswith("linux"):
            out["rss_bytes"] = raw * 1024
            out["rss_text"] = str(out["rss_bytes"])
            out["rss_unit"] = "linux ru_maxrss kilobytes, stored as bytes"
        elif sys.platform == "darwin":
            out["rss_bytes"] = raw
            out["rss_text"] = str(raw)
            out["rss_unit"] = "darwin ru_maxrss bytes"
        else:
            out["rss_raw"] = raw
            out["rss_text"] = "unknown"
            out["rss_unit"] = "unknown on this platform"
    except Exception:
        out["rss_text"] = "unknown"
    return out


def feedback_zip(
    settings: dict[str, Any] | None,
    files: Iterable[tuple[str, bytes]] | None = None,
    perf: dict[str, Any] | None = None,
) -> bytes:
    """Zip redacted settings and allowlisted logs. Other files are skipped."""
    payload = redact(settings or {})
    snapshot = perf if isinstance(perf, dict) else perf_readout()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("settings.json", json.dumps(payload, indent=2, default=str))
        archive.writestr("perf.json", json.dumps(redact(snapshot), indent=2, default=str))
        archive.writestr(
            "README.txt",
            "EQ Legends BiS feedback bundle. Sign-in tokens are left out. "
            "Only eq-api.log, main.log, and parser-stall.log are included.\n",
        )
        for name, data in files or []:
            safe = safe_log_name(name)
            if not safe:
                continue
            text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
            archive.writestr(f"logs/{safe}", scrub_log_text(text))
    return buffer.getvalue()
