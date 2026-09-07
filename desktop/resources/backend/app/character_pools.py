"""EQ Legends character pool math for Live Totals.

Source: eqlegendstools.com char-sheet runtime (verified working model).
Calibrated around level-50 sheet math — the same formulas their site uses for
HP / Mana / END / attrs / resists. We do not invent item stats; gear values
still come only from decoded JSON.

Key helpers mirrored from char-sheet-runtime (names kept close for audit):
- jo / Uo / Vo / q / x  → HP from STA + class HP factors
- _o / Ko / $ / I       → Mana from INT (caster) / WIS (priest)
- zo / O                → Endurance from STR/STA/DEX/AGI averages
- po / uo               → attribute soft-cap (510, Magician 520)
"""
from __future__ import annotations

from typing import Any

# Class HP factors (x) and base-HP lookup (q) from eqlegendstools char-sheet.
CLASS_HP_FACTOR: dict[str, int] = {
    "Warrior": 300,
    "Paladin": 288,
    "Shadow Knight": 288,
    "Ranger": 276,
    "Bard": 264,
    "Cleric": 264,
    "Beastlord": 255,
    "Berserker": 255,
    "Monk": 255,
    "Rogue": 255,
    "Shaman": 255,
    "Druid": 240,
    "Enchanter": 240,
    "Magician": 240,
    "Necromancer": 240,
    "Wizard": 240,
}
BASE_HP_BY_FACTOR: dict[int, int] = {
    300: 2705,
    288: 2670,
    276: 2634,
    264: 2599,
    255: 2573,
    240: 2528,
}

# Mana contributors: INT set ($) vs WIS set (I). Pure melee (w) → no mana pool.
MANA_INT_CLASSES = {
    "Bard", "Enchanter", "Magician", "Necromancer", "Wizard", "Shadow Knight",
}
MANA_WIS_CLASSES = {
    "Beastlord", "Cleric", "Druid", "Paladin", "Ranger", "Shaman",
}
NO_MANA_CLASSES = {"Berserker", "Rogue", "Warrior", "Monk"}

# Endurance class factors (O)
ENDURANCE_CLASS: dict[str, dict[str, float]] = {
    "Warrior": {"base": 900, "factor": 4.5},
    "Cleric": {"base": 456, "factor": 3.25},
    "Paladin": {"base": 652, "factor": 3.25},
    "Ranger": {"base": 652, "factor": 3.25},
    "Shadow Knight": {"base": 652, "factor": 3.25},
    "Druid": {"base": 456, "factor": 3.25},
    "Monk": {"base": 900, "factor": 4.5},
    "Bard": {"base": 554, "factor": 3.25},
    "Rogue": {"base": 900, "factor": 4.5},
    "Shaman": {"base": 456, "factor": 3.25},
    "Necromancer": {"base": 260, "factor": 1.25},
    "Wizard": {"base": 260, "factor": 1.25},
    "Magician": {"base": 260, "factor": 1.25},
    "Enchanter": {"base": 260, "factor": 1.25},
    "Beastlord": {"base": 652, "factor": 3.25},
    "Berserker": {"base": 995, "factor": 4.25},
}

# Natural Durability AA ranks → % HP increase (replacing ranks)
NATURAL_DURABILITY_PCT = {0: 0, 1: 2, 2: 5, 3: 10, 4: 12}

ATTR_KEYS = ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA")
RESIST_KEYS = ("SVF", "SVC", "SVM", "SVP", "SVD")

SOURCE_NOTE = (
    "Pools from eqlegendstools char-sheet working model (race + class allotments + "
    "STA/INT/WIS formulas). Gear stats still from decoded JSON only."
)


def attr_cap(classes: list[str]) -> int:
    """uo() — Magician raises soft-cap to 520; others 510."""
    return 520 if "Magician" in (classes or []) else 510


def clamp_attr(value: float, classes: list[str]) -> float:
    """po() — clamp a single attribute to the class soft-cap."""
    return float(min(attr_cap(classes), max(0, int(value or 0))))


def is_pure_melee(classes: list[str]) -> bool:
    """Er() — every selected class is a no-mana melee class."""
    cleaned = [c for c in (classes or []) if c]
    return bool(cleaned) and all(c in NO_MANA_CLASSES for c in cleaned)


def _top_hp_factors(classes: list[str]) -> tuple[int, int]:
    """Vo() — top two class HP factors (duplicate if only one class)."""
    factors = sorted(
        (CLASS_HP_FACTOR[c] for c in (classes or []) if c in CLASS_HP_FACTOR),
        reverse=True,
    )
    if len(factors) >= 2:
        return factors[0], factors[1]
    if len(factors) == 1:
        return factors[0], factors[0]
    return 240, 240


def _sta_for_hp(sta: float) -> int:
    """STA soft-curve used inside Uo (≤255 full; beyond half-value)."""
    t = max(0, int(sta or 0))
    return t if t <= 255 else 255 + (t - 255) // 2


def hp_from_sta(sta: float, classes: list[str]) -> int:
    """jo() — base HP from STA + class HP factors."""
    top, second = _top_hp_factors(classes)
    base = BASE_HP_BY_FACTOR.get(top, BASE_HP_BY_FACTOR[240])
    contrib = _sta_for_hp(sta) * ((top + second) / 60.0)
    return int(round(base + contrib))


def _mana_attr_curve(stat: float) -> int:
    """Inner curve used by Ko() before 900+4.5× scaling."""
    t = max(0, int(stat or 0))
    if t <= 0:
        return 0
    if t <= 100:
        return t
    if t <= 200:
        return t + (3 * t - 300) // 2
    n = t - (t - 200) // 2
    return n + (3 * n - 300) // 2


def mana_from_attr(stat: float) -> int:
    """Ko() — mana contribution from one INT or WIS value."""
    return int(900 + 4.5 * _mana_attr_curve(stat)) // 1


def mana_from_int_wis(intel: float, wis: float, classes: list[str]) -> int:
    """_o() — up to two class mana contributions (INT and/or WIS sets)."""
    if is_pure_melee(classes):
        return 0
    parts: list[int] = []
    for c in classes or []:
        if c in MANA_INT_CLASSES:
            parts.append(mana_from_attr(intel))
        elif c in MANA_WIS_CLASSES:
            parts.append(mana_from_attr(wis))
        else:
            parts.append(0)
    parts.sort(reverse=True)
    return int(sum(parts[:2]))


def _endurance_avg_curve(avg: float) -> int:
    r = float(avg or 0)
    if r > 201:
        s = 352.5 + 1.25 * (r - 201)
    elif r > 100:
        s = 100 + 2.5 * (r - 100)
    else:
        s = r
    return int(s)


def endurance_from_attrs(
    strength: float,
    sta: float,
    dex: float,
    agi: float,
    classes: list[str],
) -> int:
    """zo() — endurance from STR/STA/DEX/AGI average + top two class factors."""
    avg = (float(strength or 0) + float(sta or 0) + float(dex or 0) + float(agi or 0)) / 4.0
    curved = _endurance_avg_curve(avg)
    scores: list[int] = []
    for c in classes or []:
        row = ENDURANCE_CLASS.get(c)
        if not row:
            continue
        scores.append(int(row["base"] + row["factor"] * curved))
    scores.sort(reverse=True)
    return int((scores[0] if scores else 0) + (scores[1] if len(scores) > 1 else 0))


def combine_race_class_attrs(race_attrs: dict[str, Any], class_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Race bases + creation allotments from every selected class (EQLT multi-class)."""
    out = {k: float(race_attrs.get(k) or 0) for k in ATTR_KEYS}
    for row in class_rows or []:
        for k in ATTR_KEYS:
            out[k] = out.get(k, 0.0) + float(row.get(k) or 0)
    return out


def apply_natural_durability(hp: float, rank: int = 4) -> int:
    pct = NATURAL_DURABILITY_PCT.get(max(0, min(4, int(rank))), 0)
    return int(hp * (1 + pct / 100.0))


def compute_pools(
    *,
    classes: list[str],
    race_attrs: dict[str, Any],
    race_resists: dict[str, Any],
    class_stat_rows: list[dict[str, Any]],
    gear_stats: dict[str, float],
    buff_stats: dict[str, float] | None = None,
    assume_max_aas: bool = True,
) -> dict[str, Any]:
    """Return live totals breakdown matching eqlegendstools char-sheet pooling."""
    buff_stats = dict(buff_stats or {})
    cleaned = [c for c in (classes or []) if c]

    base_attrs = combine_race_class_attrs(race_attrs, class_stat_rows)
    gear_attrs = {k: float(gear_stats.get(k) or 0) for k in ATTR_KEYS}
    buff_attrs = {k: float(buff_stats.get(k) or 0) for k in ATTR_KEYS}

    # AA: Innate Eminence +2/rank to all attrs; Improved Familiar (Wizard) +200 mana +25 resists
    eminence = 2 * (5 if assume_max_aas else 0)
    familiar = 1 if (assume_max_aas and "Wizard" in cleaned) else 0
    familiar_mana = 200 * familiar
    resist_aa = 2 * (5 if assume_max_aas else 0) + 25 * familiar
    nat_dur = 4 if assume_max_aas else 0

    # N = capped race+class only; B = race+class+gear (pre-buff); E = final capped
    n_raw = dict(base_attrs)
    b_raw = {k: base_attrs[k] + gear_attrs[k] for k in ATTR_KEYS}
    e_raw = {
        k: base_attrs[k] + gear_attrs[k] + buff_attrs[k] + eminence
        for k in ATTR_KEYS
    }
    n_cap = {k: clamp_attr(n_raw[k], cleaned) for k in ATTR_KEYS}
    b_cap = {k: clamp_attr(b_raw[k], cleaned) for k in ATTR_KEYS}
    e_cap = {k: clamp_attr(e_raw[k], cleaned) for k in ATTR_KEYS}

    # HP
    hp_base = hp_from_sta(e_cap["STA"], cleaned)
    gear_hp = float(gear_stats.get("HP") or 0)
    buff_hp = float(buff_stats.get("HP") or 0)
    hp = apply_natural_durability(hp_base + gear_hp + buff_hp, nat_dur)

    # Mana
    if is_pure_melee(cleaned):
        mana = 0
    else:
        mana_base = mana_from_int_wis(e_cap["INT"], e_cap["WIS"], cleaned)
        mana = int(mana_base + float(gear_stats.get("MANA") or 0) + float(buff_stats.get("MANA") or 0) + familiar_mana)

    # Endurance
    end_base = endurance_from_attrs(e_cap["STR"], e_cap["STA"], e_cap["DEX"], e_cap["AGI"], cleaned)
    endurance = int(end_base + float(gear_stats.get("END") or 0) + float(buff_stats.get("END") or 0))

    # Resists — Warrior innate +25 SVM in EQLT sheet
    resists: dict[str, float] = {}
    for k in RESIST_KEYS:
        resists[k] = (
            float(race_resists.get(k) or 0)
            + float(gear_stats.get(k) or 0)
            + float(buff_stats.get(k) or 0)
            + resist_aa
        )
    if "Warrior" in cleaned:
        resists["SVM"] = resists.get("SVM", 0) + 25
    resists["SVV"] = float(gear_stats.get("SVV") or 0) + float(buff_stats.get("SVV") or 0)

    ac = float(gear_stats.get("AC") or 0) + float(buff_stats.get("AC") or 0)
    atk = float(gear_stats.get("ATK") or 0) + float(buff_stats.get("ATK") or 0)

    totals = {
        **{k: e_cap[k] for k in ATTR_KEYS},
        "HP": hp,
        "MANA": mana,
        "END": endurance,
        "AC": ac,
        "ATK": atk,
        **resists,
        "HP_REGEN": float(gear_stats.get("HP_REGEN") or 0) + float(buff_stats.get("HP_REGEN") or 0),
        "MANA_REGEN": float(gear_stats.get("MANA_REGEN") or 0) + float(buff_stats.get("MANA_REGEN") or 0),
        "END_REGEN": float(gear_stats.get("END_REGEN") or 0) + float(buff_stats.get("END_REGEN") or 0),
    }

    return {
        "totals": totals,
        "attrs_uncapped": e_raw,
        "attrs_race_class": n_cap,
        "attrs_with_gear": b_cap,
        "breakdown": {
            "hp_base_from_sta": hp_base,
            "gear_hp": gear_hp,
            "buff_hp": buff_hp,
            "natural_durability_rank": nat_dur,
            "mana_from_int_wis": 0 if is_pure_melee(cleaned) else mana_from_int_wis(e_cap["INT"], e_cap["WIS"], cleaned),
            "familiar_mana": familiar_mana,
            "endurance_from_attrs": end_base,
            "eminence": eminence,
            "resist_aa": resist_aa,
        },
        "source": SOURCE_NOTE,
        "assume_max_aas": assume_max_aas,
    }
