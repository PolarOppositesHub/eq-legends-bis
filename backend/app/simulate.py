"""Build simulator totals + single-worn-haste enforcement/warnings."""
from __future__ import annotations

import math
import sys
from pathlib import Path

from .races import race_bases
from .scoring import PLANNER_SLOTS, item_haste, num

TOTAL_KEYS = [
    "AC", "HP", "MANA", "END", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA",
    "SVF", "SVC", "SVM", "SVP", "SVD", "SVV", "ATK", "DMG",
]

# Reuse site scale formula from decode_local when available
_scale = None
_scaled_dmg = None
try:
    from .paths import ensure_vendor_on_path
    ensure_vendor_on_path()
    from decode_local import scale_item_stat as _scale  # type: ignore
    import build_xlsx as _bx  # type: ignore
    _scaled_dmg = _bx.scaled_dmg
except Exception:
    pass

SCALABLE = {
    "AC", "HP", "MANA", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA", "END", "ATK",
    "SVM", "SVF", "SVC", "SVD", "SVP", "SVV",
}


def _fallback_scale(base, level: int):
    try:
        o = float(base or 0)
    except (TypeError, ValueError):
        return 0.0
    if not o or not level:
        return float(o)
    a = math.floor(o * (1 + level / 10))
    if o > 0:
        return float(max(a, o + level))
    if o < -10:
        return float(math.ceil(o * max(0, 10 - level) / 10))
    return float(min(0, o + level))


def scale_stats(stats0: dict, level: int) -> dict:
    level = max(0, min(10, int(level)))
    if level == 0:
        return {k: num(v) for k, v in (stats0 or {}).items()}
    out = {}
    for k, v in (stats0 or {}).items():
        if k == "DMG":
            if _scaled_dmg is not None:
                out[k] = float(_scaled_dmg(v, level))
            else:
                out[k] = float(math.floor(float(v) * (1 + level / 10)))
        elif k in ("DLY", "FIRE_DMG", "COLD_DMG", "Haste"):
            out[k] = num(v)
        elif k in SCALABLE:
            if _scale is not None:
                out[k] = float(_scale(v, level))
            else:
                out[k] = _fallback_scale(v, level)
        else:
            out[k] = num(v) if not isinstance(v, str) else v
    return out


def simulate_loadout(
    equipped: dict[str, dict | None],
    *,
    race: str | None = None,
    upgrade: int = 10,
) -> dict:
    """Sum gear (+ race bases). Only highest worn haste counts; warn on multiples."""
    upgrade = max(0, min(10, int(upgrade)))

    bases = race_bases(race)
    totals = {k: float(bases.get(k, 0) or 0) for k in TOTAL_KEYS}
    for k in ("HP", "MANA", "END", "AC"):
        if k not in bases:
            totals[k] = 0.0

    haste_items: list[dict] = []
    slots_out: dict[str, dict] = {}
    weapons: list[dict] = []

    for slot in PLANNER_SLOTS:
        raw = equipped.get(slot) if equipped else None
        if not raw or not raw.get("name"):
            slots_out[slot] = {"slot": slot, "name": "", "haste": 0, "stats": {}}
            continue

        s0 = dict(raw.get("stats_plus0") or {})
        s10 = dict(raw.get("stats_plus10") or {})
        if not s0 and isinstance(raw.get("item"), dict):
            s0 = dict(raw["item"].get("stats_plus0") or {})
            s10 = dict(raw["item"].get("stats_plus10") or {})

        if upgrade >= 10 and s10:
            stats = dict(s10)
        elif upgrade == 0 and s0:
            stats = {k: num(v) for k, v in s0.items()}
        elif s0:
            stats = scale_stats(s0, upgrade)
        else:
            stats = dict(s10)

        h = item_haste(raw) if ("stats_plus0" in raw or "stats_plus10" in raw) else num(stats.get("Haste"))
        if h <= 0 and isinstance(raw.get("item"), dict):
            h = item_haste(raw["item"])
        if h <= 0:
            h = num(stats.get("Haste"))

        ratio = raw.get("ratio_plus10") if upgrade >= 10 else raw.get("ratio_plus0")
        if ratio is None:
            ratio = raw.get("ratio10") if upgrade >= 10 else raw.get("ratio0")
        dmg = num(stats.get("DMG"))
        dly = num(stats.get("DLY"))
        if dmg and dly:
            ratio = round(dmg / dly, 4)

        entry = {
            "slot": slot,
            "name": raw.get("name") or "",
            "haste": h,
            "stats": stats,
            "url": raw.get("url") or "",
            "is_weapon": bool(raw.get("is_weapon")),
            "ratio10": raw.get("ratio_plus10", raw.get("ratio10")),
            "ratio": ratio,
        }
        slots_out[slot] = entry
        if h > 0:
            haste_items.append({"slot": slot, "name": entry["name"], "haste": h})
        if entry["is_weapon"] and ratio is not None:
            weapons.append({"slot": slot, "name": entry["name"], "ratio": ratio, "dmg": dmg, "dly": dly})
        for k in TOTAL_KEYS:
            if k == "Haste":
                continue
            totals[k] = totals.get(k, 0) + num(stats.get(k))

    warnings: list[str] = []
    applied_haste = 0.0
    if haste_items:
        haste_items.sort(key=lambda x: (-x["haste"], x["slot"]))
        best = haste_items[0]
        applied_haste = float(best["haste"])
        if len(haste_items) > 1:
            others = ", ".join(
                f"{h['name']} (+{int(h['haste'])}% @ {h['slot']})" for h in haste_items[1:]
            )
            warnings.append(
                f"Multiple worn haste items equipped. Only highest counts: "
                f"{best['name']} (+{int(best['haste'])}% @ {best['slot']}). Ignored: {others}."
            )

    totals_int = {
        k: int(round(v)) if abs(v - round(v)) < 1e-6 else round(v, 2)
        for k, v in totals.items()
    }
    totals_int["Haste"] = int(applied_haste)
    haste_warning = warnings[0] if warnings else None
    race_note = (
        "Attr bases from eqlwiki Character Races. "
        "HP/Mana/Endurance/AC/resist racial bases treated as 0 (gear-only) unless noted."
    )
    return {
        "race": race or "",
        "race_bases": bases,
        "race_note": race_note,
        "upgrade": upgrade,
        "slots": slots_out,
        "equipped": {s: v for s, v in slots_out.items() if v.get("name")},
        "totals": totals_int,
        "weapons": weapons,
        "haste": {
            "applied": int(applied_haste),
            "applied_pct": int(applied_haste),
            "items": haste_items,
            "rule": "ONLY ONE worn haste item counts (highest %). Spell/focus haste is not worn haste.",
        },
        "haste_applied": int(applied_haste),
        "haste_pieces": haste_items,
        "haste_warning": haste_warning,
        "warnings": warnings,
    }
