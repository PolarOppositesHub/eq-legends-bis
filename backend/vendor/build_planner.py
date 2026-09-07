#!/usr/bin/env python3
"""Rebuild EQ_Legends_BiS.xlsx with interactive Stat planner for any 1–3 of 16 classes."""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import build_xlsx as bx


import os
from pathlib import Path as _Path

def _resolve_root():
    for key in ("EQ_LEGENDS_ROOT", "EQ_APP_ROOT"):
        v = os.environ.get(key)
        if v and _Path(v).exists():
            return _Path(v)
    here = _Path(__file__).resolve().parent
    # vendor copy lives in backend/vendor; decoded may be sibling data
    for cand in (
        here,
        here.parent.parent / "data",
        _Path("/workspace/eq-legends"),
    ):
        if (cand / "decoded").exists() or (cand / "build_planner.py").exists():
            # Prefer real legends tree when present
            pass
    if (_Path("/workspace/eq-legends") / "decoded").exists():
        return _Path("/workspace/eq-legends")
    # Packaged: EQ_LEGENDS_DATA parent or resources
    data = os.environ.get("EQ_LEGENDS_DATA")
    if data:
        return _Path(data).parent if _Path(data).name == "decoded" else _Path(data)
    return here

def _resolve_out(root):
    data = os.environ.get("EQ_LEGENDS_DATA")
    if data and _Path(data).exists():
        return _Path(data)
    if (root / "decoded").exists():
        return root / "decoded"
    # backend/vendor -> ../../data/decoded
    app_data = _Path(__file__).resolve().parents[2] / "data" / "decoded"
    if app_data.exists():
        return app_data
    return root / "decoded"

ROOT = _resolve_root()
OUT = _resolve_out(ROOT)
XLSX = ROOT / "EQ_Legends_BiS.xlsx"
XLSX_FIXED = ROOT / "EQ_Legends_BiS_fixed.xlsx"
VERIFY = ROOT / "planner_verify.json"

# Default planner trio; overridden in main() from Class selector / DEFAULT_TRIO
TARGET = tuple(bx.DEFAULT_TRIO)
TARGET_SET = set(TARGET)
ALL_CLASSES = bx.ALL_CLASSES

# Planner equipment slots (display order). FINGER/EAR get two distinct picks.
PLANNER_SLOTS = [
    "HEAD", "FACE", "EAR1", "EAR2", "NECK", "SHOULDERS", "ARMS", "WRIST",
    "HANDS", "CHEST", "BACK", "WAIST", "LEGS", "FEET",
    "FINGER1", "FINGER2", "PRIMARY", "SECONDARY", "RANGE", "AMMO",
]

# Base pool slot -> which planner slots it can fill
SLOT_ALIASES = {
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
    "FINGER": ["FINGER1", "FINGER2"],
    "PRIMARY": ["PRIMARY"],
    "SECONDARY": ["SECONDARY"],
    "RANGE": ["RANGE"],
    "AMMO": ["AMMO"],
}

WEAPON_SLOTS = {"PRIMARY", "SECONDARY", "RANGE", "AMMO"}

ATTR_KEYS = ["AC", "HP", "MANA", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA"]
RESIST_KEYS = ["SVF", "SVC", "SVM", "SVP", "SVD", "SVV"]
OTHER_SCORE_KEYS = ATTR_KEYS + RESIST_KEYS  # for secondary / max-all (excl END special)

PRIORITY_STATS = [
    ("AC", "AC"),
    ("HP", "HP"),
    ("MANA", "Mana"),
    ("END", "END"),
    ("STR", "STR"),
    ("STA", "STA"),
    ("AGI", "AGI"),
    ("DEX", "DEX"),
    ("WIS", "WIS"),
    ("INT", "INT"),
    ("CHA", "CHA"),
    ("SVF", "SV Fire"),
    ("SVC", "SV Cold"),
    ("SVM", "SV Magic"),
    ("SVP", "SV Poison"),
    ("SVD", "SV Disease"),
]

PRIORITY_LABELS = [lab for _, lab in PRIORITY_STATS]
LABEL_TO_KEY = {lab: key for key, lab in PRIORITY_STATS}
KEY_TO_LABEL = {key: lab for key, lab in PRIORITY_STATS}

TIP_STAT_PAT = re.compile(
    r"(AC|HP|MANA|END|STR|STA|AGI|DEX|WIS|INT|CHA|ATK|DMG|Haste|"
    r"SV FIRE|SV COLD|SV MAGIC|SV POISON|SV DISEASE|SV VOID|"
    r"FIRE DMG|COLD DMG)\s*:\s*\+?(-?\d+)",
    re.I,
)
TIP_DLY_PAT = re.compile(r"Atk Delay:\s*(\d+)", re.I)
TIP_STAT_MAP = {
    "AC": "AC", "HP": "HP", "MANA": "MANA", "END": "END",
    "STR": "STR", "STA": "STA", "AGI": "AGI", "DEX": "DEX",
    "WIS": "WIS", "INT": "INT", "CHA": "CHA", "ATK": "ATK",
    "DMG": "DMG", "HASTE": "Haste",
    "SV FIRE": "SVF", "SV COLD": "SVC", "SV MAGIC": "SVM",
    "SV POISON": "SVP", "SV DISEASE": "SVD", "SV VOID": "SVV",
    "FIRE DMG": "FIRE_DMG", "COLD DMG": "COLD_DMG",
}

HEADER_FILL = bx.HEADER_FILL
HEADER_FONT = bx.HEADER_FONT
THIN = bx.THIN
SELECT_FILL = PatternFill("solid", fgColor="FFF2CC")
ALT_FILL = PatternFill("solid", fgColor="E2EFDA")
NOTE_FILL = PatternFill("solid", fgColor="DDEBF7")


def parse_tip_stats(tip: dict | None) -> dict:
    if not tip:
        return {}
    stats: dict = {}
    for line in tip.get("lines") or []:
        s = str(line)
        for m in TIP_STAT_PAT.finditer(s):
            raw = m.group(1).upper()
            key = TIP_STAT_MAP.get(raw)
            if key:
                stats[key] = int(m.group(2))
        m2 = TIP_DLY_PAT.search(s)
        if m2:
            stats["DLY"] = int(m2.group(1))
    return stats


def scale_item_stat(base, level: int = 10):
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


def scale_stats_plus10(stats0: dict) -> dict:
    out = {}
    for k, v in (stats0 or {}).items():
        if k == "DMG":
            try:
                out[k] = float(math.floor(float(v) * 2))  # level 10
            except (TypeError, ValueError):
                continue
        elif k == "DLY" or k in ("FIRE_DMG", "COLD_DMG", "Haste"):
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
        elif k in bx.STAT_COLS or k in {
            "AC", "HP", "MANA", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA",
            "END", "ATK", "SVM", "SVF", "SVC", "SVD", "SVP", "SVV",
        }:
            # use known scalable set
            from decode_local import SCALABLE_STATS
            if k in SCALABLE_STATS or k in {
                "AC", "HP", "MANA", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA",
                "END", "ATK", "SVM", "SVF", "SVC", "SVD", "SVP", "SVV",
            }:
                out[k] = scale_item_stat(v, 10)
            else:
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    pass
        else:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                pass
    return out


def num(v, default=0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def positive(v: float) -> float:
    return v if v > 0 else 0.0

def item_haste(item: dict) -> float:
    """Worn haste percent from +10/+0 stats (does not scale)."""
    s10 = item.get("stats_plus10") or {}
    s0 = item.get("stats_plus0") or {}
    h = s10.get("Haste")
    if h is None:
        h = s0.get("Haste")
    return num(h)


def haste_bonus(item: dict) -> float:
    """Soft score contribution for individual-item ranking (display/prefer haste)."""
    h = item_haste(item)
    return h * 2.0 if h > 0 else 0.0



def expand_slots(slot_field) -> list[str]:
    """Map raw slot string / list to planner slot names."""
    if isinstance(slot_field, list):
        parts = [str(s).strip().upper() for s in slot_field if s]
    else:
        parts = [p.strip().upper() for p in str(slot_field or "").split("/") if p.strip()]
    out = []
    for p in parts:
        out.extend(SLOT_ALIASES.get(p, []))
    # dedupe preserve order
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def base_slots_from_item(item: dict) -> list[str]:
    slots = item.get("slots")
    if slots:
        return [str(s).strip().upper() for s in slots if s]
    slot = str(item.get("slot") or "")
    return [p.strip().upper() for p in slot.split("/") if p.strip()]


def usable_by_tri(classes) -> bool:
    if not classes:
        return False
    cl = {str(c) for c in classes}
    if "ALL" in cl:
        return True
    return bool(cl & TARGET_SET)


def tri_class_count(classes) -> int:
    if not classes:
        return 0
    cl = {str(c) for c in classes}
    if "ALL" in cl:
        return 3
    return len(cl & TARGET_SET)


def bis_overlap(bis_for) -> int:
    if not bis_for:
        return 0
    return len(set(bis_for) & TARGET_SET)


def is_weapon_item(item: dict) -> bool:
    if item.get("is_weapon"):
        return True
    bases = set(base_slots_from_item(item))
    if bases & {"PRIMARY", "SECONDARY", "RANGE", "AMMO"} and (
        item.get("ratio_plus10") is not None
        or num((item.get("stats_plus0") or {}).get("DMG")) > 0
        or num((item.get("stats_plus10") or {}).get("DMG")) > 0
    ):
        # AMMO with DMG counts; PRIMARY without DMG (tomes) are gear-like — not weapon-ratio
        if "AMMO" in bases and "PRIMARY" not in bases and "SECONDARY" not in bases and "RANGE" not in bases:
            return True  # ammo still scored with ratio if present
        if item.get("ratio_plus10") is not None or (
            num((item.get("stats_plus0") or {}).get("DMG")) > 0
            and num((item.get("stats_plus0") or {}).get("DLY")) > 0
        ):
            return True
    return bool(item.get("is_weapon"))


def other_positive_sum(s10: dict, exclude_key: str | None = None) -> float:
    total = 0.0
    for k in OTHER_SCORE_KEYS:
        if exclude_key and k == exclude_key:
            continue
        total += positive(num(s10.get(k)))
    # END if present and not the priority
    if exclude_key != "END":
        total += positive(num(s10.get("END")))
    return total


def max_all_stat_sum(s10: dict) -> float:
    """Weighted non-weapon bang-for-buck on +10 stats."""
    hp = num(s10.get("HP"))
    mana = num(s10.get("MANA"))
    ac = num(s10.get("AC"))
    attrs = sum(num(s10.get(k)) for k in ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA"))
    resists = sum(num(s10.get(k)) for k in RESIST_KEYS)
    end = num(s10.get("END"))
    return hp * 1.0 + mana * 1.0 + ac * 2.0 + attrs * 1.5 + resists * 1.0 + end * 0.5


def score_priority(item: dict, stat_key: str) -> tuple[float, float, str]:
    """Return (score, priority_value, why). Haste shown/boosted per-item; loadout caps at one haste."""
    s10 = item.get("stats_plus10") or {}
    pval = num(s10.get(stat_key))
    hb = haste_bonus(item)
    weapon = item.get("is_weapon") and item.get("ratio_plus10") is not None
    if weapon:
        ratio10 = num(item.get("ratio_plus10"))
        other = other_positive_sum(s10, exclude_key=stat_key)
        score = ratio10 * 10000.0 + pval * 10.0 + 0.15 * other + hb
        why = "best ratio"
        return score, pval, why  # priority val stays the priority stat
    other = other_positive_sum(s10, exclude_key=stat_key)
    score = pval * 100.0 + 0.15 * other + hb
    why = f"highest {KEY_TO_LABEL.get(stat_key, stat_key)}"
    return score, pval, why


def score_max_all(item: dict) -> tuple[float, float, str]:
    s10 = item.get("stats_plus10") or {}
    weapon = item.get("is_weapon") and item.get("ratio_plus10") is not None
    bang = max_all_stat_sum(s10)
    hb = haste_bonus(item)
    if weapon:
        ratio10 = num(item.get("ratio_plus10"))
        score = ratio10 * 10000.0 + 0.2 * bang + hb
        return score, bang, "best ratio"
    return bang + hb, bang, "best total score"


def prefer_multi_class(ranked: list[dict], within_pct: float = 0.05) -> list[dict]:
    """Among near-tied top scores, prefer higher bis_overlap / tri class count."""
    if not ranked:
        return ranked
    # re-sort with soft preference: if score within 5% of best, boost by bis_overlap
    best = ranked[0]["score"]
    if best <= 0:
        return ranked

    def key(r):
        close = 1 if r["score"] >= best * (1 - within_pct) else 0
        return (
            close * r.get("bis_overlap", 0),
            close * r.get("tri_classes", 0),
            r["score"],
            r.get("name", ""),
        )

    # Stable: keep score primary, but among top band prefer multi-class
    out = list(ranked)
    top_band = [r for r in out if r["score"] >= best * (1 - within_pct)]
    rest = [r for r in out if r["score"] < best * (1 - within_pct)]
    top_band.sort(
        key=lambda r: (-r.get("bis_overlap", 0), -r.get("tri_classes", 0), -r["score"], r["name"])
    )
    return top_band + rest


def build_item_pool(merged, catalog, slug_map) -> list[dict]:
    tips_by_name = bx.build_tooltip_by_name(catalog)
    pool: dict[str, dict] = {}

    def upsert(item: dict):
        name = item.get("name") or ""
        if not name or str(name).strip().lower() == "none":
            return
        if bx.is_broken_weapon_row(item):
            return
        key = name.strip().lower()
        existing = pool.get(key)
        if existing is None:
            pool[key] = item
            return
        # merge: prefer richer stats, higher bis_overlap, keep weapon flags
        for fld in ("zone", "drops_mobs", "quest_source", "url", "level", "effect", "classes_str"):
            if not existing.get(fld) and item.get(fld):
                existing[fld] = item[fld]
        if item.get("bis_overlap", 0) > existing.get("bis_overlap", 0):
            existing["bis_overlap"] = item["bis_overlap"]
            existing["bis_for"] = item.get("bis_for") or existing.get("bis_for")
            existing["bis_for_str"] = item.get("bis_for_str") or existing.get("bis_for_str")
        # merge stats_plus10 (take max per key)
        s_old = dict(existing.get("stats_plus10") or {})
        s_new = item.get("stats_plus10") or {}
        for k, v in s_new.items():
            if k not in s_old or abs(num(v)) > abs(num(s_old.get(k))):
                s_old[k] = v
        existing["stats_plus10"] = s_old
        s0_old = dict(existing.get("stats_plus0") or {})
        for k, v in (item.get("stats_plus0") or {}).items():
            if k not in s0_old:
                s0_old[k] = v
        existing["stats_plus0"] = s0_old
        if item.get("ratio_plus10") is not None:
            existing["ratio_plus10"] = item["ratio_plus10"]
            existing["ratio_plus0"] = item.get("ratio_plus0")
            existing["is_weapon"] = True
        if item.get("oneHanded") and not existing.get("oneHanded"):
            existing["oneHanded"] = item.get("oneHanded")
        if item.get("hand") and not existing.get("hand"):
            existing["hand"] = item.get("hand")
        if item.get("offhandUsable") and not existing.get("offhandUsable"):
            existing["offhandUsable"] = item.get("offhandUsable")
        # union planner slots
        slots = list(dict.fromkeys((existing.get("planner_slots") or []) + (item.get("planner_slots") or [])))
        existing["planner_slots"] = slots
        if item.get("tri_classes", 0) > existing.get("tri_classes", 0):
            existing["tri_classes"] = item["tri_classes"]
            existing["classes"] = item.get("classes") or existing.get("classes")
            existing["classes_str"] = item.get("classes_str") or existing.get("classes_str")

    # Gear from merged BiS (already PAL/MNK/WIZ BiS union)
    for r in bx.filter_gear_rows(merged):
        classes = r.get("classes") or []
        if not usable_by_tri(classes):
            continue
        s0 = dict(r.get("stats_plus0") or {})
        s10 = dict(r.get("stats_plus10") or {})
        if not s10 and s0:
            s10 = scale_stats_plus10(s0)
        bases = base_slots_from_item(r)
        planner_slots = []
        for b in bases:
            planner_slots.extend(SLOT_ALIASES.get(b, []))
        planner_slots = list(dict.fromkeys(planner_slots))
        if not planner_slots:
            continue
        item = {
            "name": r.get("name"),
            "itemID": r.get("itemID"),
            "slot": r.get("slot"),
            "slots": bases,
            "planner_slots": planner_slots,
            "classes": classes,
            "classes_str": r.get("classes_str") or ", ".join(classes),
            "bis_for": r.get("bis_for") or [],
            "bis_for_str": r.get("bis_for_str") or "",
            "bis_overlap": bis_overlap(r.get("bis_for")),
            "tri_classes": tri_class_count(classes),
            "zone": r.get("zone") or "",
            "drops_mobs": r.get("drops_mobs") or "",
            "quest_source": r.get("quest_source") or "",
            "level": r.get("level"),
            "effect": r.get("effect") or "",
            "url": r.get("url") or bx.item_url(r.get("name") or "", slug_map),
            "stats_plus0": s0,
            "stats_plus10": s10,
            "ratio_plus0": r.get("ratio_plus0"),
            "ratio_plus10": r.get("ratio_plus10"),
            "is_weapon": False,
        }
        # mark as weapon if has proper dmg/dly ratio
        if item["ratio_plus10"] is not None or (
            num(s0.get("DMG")) > 0 and num(s0.get("DLY")) > 0
        ):
            if item["ratio_plus10"] is None:
                dmg10 = bx.scaled_dmg(s0.get("DMG"), 10)
                item["ratio_plus0"] = bx.ratio(s0.get("DMG"), s0.get("DLY"))
                item["ratio_plus10"] = bx.ratio(dmg10, s0.get("DLY"))
            item["is_weapon"] = True
        upsert(item)

    # Catalog weapons usable by any of the three
    for w in catalog.get("weapons") or []:
        classes = list(w.get("classNames") or [])
        if not usable_by_tri(classes):
            continue
        name = w.get("weaponName") or ""
        if not name:
            continue
        tip = tips_by_name.get(name)
        tip_stats = parse_tip_stats(tip)
        dmg0 = w.get("dmg")
        dly = w.get("dly") if w.get("dly") is not None else tip_stats.get("DLY")
        if dmg0 is None and tip_stats.get("DMG") is not None:
            dmg0 = tip_stats.get("DMG")
        dmg10 = bx.scaled_dmg(dmg0, 10) if dmg0 is not None else None
        s0 = {k: v for k, v in tip_stats.items() if k not in ("DMG", "DLY")}
        if dmg0 is not None:
            s0["DMG"] = dmg0
        if dly is not None:
            s0["DLY"] = dly
        s10 = scale_stats_plus10(s0)
        if dmg10 is not None:
            s10["DMG"] = dmg10
        if dly is not None:
            s10["DLY"] = float(dly)
        bases = [str(s).strip().upper() for s in (w.get("slots") or [])]
        planner_slots = []
        for b in bases:
            planner_slots.extend(SLOT_ALIASES.get(b, []))
        planner_slots = list(dict.fromkeys(planner_slots))
        zone = w.get("sourceZone") or ""
        if not zone:
            locs = []
            for e in w.get("dropsFromEntries") or []:
                if isinstance(e, dict) and e.get("location"):
                    locs.append(str(e["location"]))
            zone = ", ".join(dict.fromkeys(locs))
            if not zone:
                zone = (w.get("sourceDisplay") or "").strip()
        item = {
            "name": name,
            "itemID": w.get("itemID"),
            "slot": " / ".join(bases),
            "slots": bases,
            "planner_slots": planner_slots,
            "classes": classes,
            "classes_str": ", ".join(classes),
            "bis_for": [],
            "bis_for_str": "",
            "bis_overlap": 0,
            "tri_classes": tri_class_count(classes),
            "zone": zone,
            "drops_mobs": bx.format_drops(w),
            "quest_source": bx.format_quest(w) or (w.get("source") or ""),
            "level": w.get("minLevel"),
            "effect": bx.extract_effect_from_tip(tip),
            "url": bx.item_url(name, slug_map),
            "stats_plus0": s0,
            "stats_plus10": s10,
            "ratio_plus0": bx.ratio(dmg0, dly),
            "ratio_plus10": bx.ratio(dmg10, dly),
            "is_weapon": True,
            "oneHanded": (w.get("oneHanded") or "").strip(),
            "hand": bx.handedness(w),
            "offhandUsable": (w.get("offhandUsable") or "").strip(),
        }
        upsert(item)

    return list(pool.values())


def rank_for_slot(pool: list[dict], planner_slot: str, mode: str, stat_key: str | None) -> list[dict]:
    """Return ranked item dicts with score fields for a planner slot."""
    candidates = []
    base_needed = planner_slot
    if planner_slot in ("EAR1", "EAR2"):
        match_slots = {"EAR1", "EAR2"}
    elif planner_slot in ("FINGER1", "FINGER2"):
        match_slots = {"FINGER1", "FINGER2"}
    else:
        match_slots = {planner_slot}

    for item in pool:
        pslots = set(item.get("planner_slots") or [])
        if not (pslots & match_slots):
            continue
        if mode == "priority":
            score, pval, why = score_priority(item, stat_key or "INT")
        else:
            score, pval, why = score_max_all(item)
        # For weapons in priority mode, why stays "best ratio" unless no ratio
        if item.get("is_weapon") and item.get("ratio_plus10") is not None:
            why = "best ratio" if mode == "max" or True else why
            if mode == "priority":
                why = "best ratio"
        candidates.append(
            {
                "name": item["name"],
                "score": score,
                "pval": pval,
                "why": why,
                "zone": item.get("zone") or "",
                "drops_mobs": item.get("drops_mobs") or "",
                "classes_str": item.get("classes_str") or "",
                "ratio10": item.get("ratio_plus10"),
                "url": item.get("url") or "",
                "bis_overlap": item.get("bis_overlap", 0),
                "tri_classes": item.get("tri_classes", 0),
                "is_weapon": item.get("is_weapon", False),
                "stats_plus10": item.get("stats_plus10") or {},
                "planner_slots": item.get("planner_slots") or [],
                "item": item,
            }
        )

    candidates.sort(key=lambda r: (-r["score"], -r["bis_overlap"], r["name"]))
    candidates = prefer_multi_class(candidates, 0.05)
    return candidates


def pick_loadout(pool: list[dict], mode: str, stat_key: str | None) -> dict[str, dict]:
    """Pick one item per planner slot; FINGER/EAR get distinct items.

    Haste rule: ONLY ONE worn-haste item in the full loadout. Prefer the single
    highest Haste% piece (tie-break by normal score); other haste pieces are
    excluded so haste is never double-counted.
    """
    used_names: set[str] = set()
    loadout: dict[str, dict] = {}

    groups = [
        ["HEAD"], ["FACE"], ["EAR1", "EAR2"], ["NECK"], ["SHOULDERS"], ["ARMS"],
        ["WRIST"], ["HANDS"], ["CHEST"], ["BACK"], ["WAIST"], ["LEGS"], ["FEET"],
        ["FINGER1", "FINGER2"], ["PRIMARY"], ["SECONDARY"], ["RANGE"], ["AMMO"],
    ]

    # Phase 1: find best single haste item across all slots
    best_haste_cand = None
    best_haste_slot_group = None
    for group in groups:
        ranked = rank_for_slot(pool, group[0], mode, stat_key)
        for cand in ranked:
            h = item_haste(cand.get("item") or {})
            if h <= 0:
                continue
            cand_h = dict(cand)
            cand_h["_haste"] = h
            if best_haste_cand is None or (h, cand["score"]) > (
                best_haste_cand["_haste"], best_haste_cand["score"]
            ):
                best_haste_cand = cand_h
                best_haste_slot_group = group

    reserved_haste_name = best_haste_cand["name"] if best_haste_cand else None
    reserved_haste_group = best_haste_slot_group

    for group in groups:
        ranked = rank_for_slot(pool, group[0], mode, stat_key)
        picks = []

        # If this group owns the reserved best haste, force it into the first open slot
        if reserved_haste_name and group == reserved_haste_group:
            for cand in ranked:
                if cand["name"] == reserved_haste_name and cand["name"] not in used_names:
                    c = dict(cand)
                    c["why"] = f"best haste +{int(best_haste_cand['_haste'])}%"
                    picks.append(c)
                    break

        for cand in ranked:
            if cand["name"] in used_names:
                continue
            if any(p["name"] == cand["name"] for p in picks):
                continue
            # Skip other haste items — only the reserved best haste counts
            h = item_haste(cand.get("item") or {})
            if h > 0 and cand["name"] != reserved_haste_name:
                continue
            picks.append(cand)
            if len(picks) >= len(group):
                break

        for slot, cand in zip(group, picks):
            used_names.add(cand["name"])
            why = cand["why"]
            if slot.endswith("2") and why in (
                "highest " + KEY_TO_LABEL.get(stat_key or "", ""),
                "best total score",
                "best ratio",
            ):
                if mode == "priority" and not cand["is_weapon"]:
                    why = f"2nd {KEY_TO_LABEL.get(stat_key or '', stat_key)}"
                elif mode == "max" and not cand["is_weapon"]:
                    why = "2nd total score"
                elif cand["is_weapon"]:
                    why = "2nd ratio"
            row = dict(cand)
            row["why"] = why
            row["slot"] = slot
            loadout[slot] = row
        for slot in group:
            if slot not in loadout:
                loadout[slot] = {
                    "slot": slot,
                    "name": "",
                    "score": 0,
                    "pval": 0,
                    "why": "no item",
                    "zone": "",
                    "drops_mobs": "",
                    "classes_str": "",
                    "ratio10": None,
                    "url": "",
                }
    return loadout


def apply_haste_loadout_to_lookup(priority_rows, max_rows, pool):
    """Ensure rank-1 entries in lookup/_scores match haste-aware loadouts per mode/stat."""
    # Index rows by (mode,stat,slot,rank)
    def key_of(r):
        return (r["mode"], r["stat"], r["slot"], r["rank"])

    pri_by = {key_of(r): r for r in priority_rows}
    max_by = {key_of(r): r for r in max_rows}

    # Rebuild rank-1 from haste-aware loadouts
    for stat_key, stat_label in PRIORITY_STATS:
        loadout = pick_loadout(pool, "priority", stat_key)
        for slot, cand in loadout.items():
            if not cand.get("name"):
                continue
            k = ("Priority Stat", stat_label, slot, 1)
            if k in pri_by:
                r = pri_by[k]
                r["name"] = cand["name"]
                r["pval"] = cand.get("pval")
                r["score"] = round(cand.get("score") or 0, 4)
                r["zone"] = cand.get("zone") or ""
                r["drops"] = cand.get("drops_mobs") or ""
                r["classes"] = cand.get("classes_str") or ""
                r["ratio10"] = cand.get("ratio10")
                r["url"] = cand.get("url") or ""
                r["why"] = cand.get("why") or r.get("why")
                r["bis_overlap"] = cand.get("bis_overlap", r.get("bis_overlap", 0))
                r["stats_plus10"] = dict(cand.get("stats_plus10") or {})

    loadout = pick_loadout(pool, "max", None)
    for slot, cand in loadout.items():
        if not cand.get("name"):
            continue
        k = ("Max All Stats", "(all)", slot, 1)
        if k in max_by:
            r = max_by[k]
            r["name"] = cand["name"]
            r["pval"] = cand.get("pval")
            r["score"] = round(cand.get("score") or 0, 4)
            r["zone"] = cand.get("zone") or ""
            r["drops"] = cand.get("drops_mobs") or ""
            r["classes"] = cand.get("classes_str") or ""
            r["ratio10"] = cand.get("ratio10")
            r["url"] = cand.get("url") or ""
            r["why"] = cand.get("why") or r.get("why")
            r["bis_overlap"] = cand.get("bis_overlap", r.get("bis_overlap", 0))
            r["stats_plus10"] = dict(cand.get("stats_plus10") or {})

    return priority_rows, max_rows



def build_lookup_tables(pool: list[dict]):
    """Precompute top-6 per (stat,slot) and per slot for max-all."""
    priority_rows = []  # dicts
    max_rows = []

    for stat_key, stat_label in PRIORITY_STATS:
        for slot in PLANNER_SLOTS:
            ranked = rank_for_slot(pool, slot, "priority", stat_key)
            # For EAR2/FINGER2, skip the #1 name when building alternates list displayed as rank1=best for that logical slot
            # Lookup stores absolute ranking for the shared pool; planner formulas use rank 1 for *1 and rank 2 for *2
            seen = set()
            rank = 0
            for cand in ranked:
                if cand["name"] in seen:
                    continue
                seen.add(cand["name"])
                rank += 1
                if rank > 6:
                    break
                priority_rows.append(
                    {
                        "mode": "Priority Stat",
                        "stat": stat_label,
                        "stat_key": stat_key,
                        "slot": slot,
                        "rank": rank,
                        "name": cand["name"],
                        "pval": cand["pval"],
                        "score": round(cand["score"], 4),
                        "zone": cand["zone"],
                        "drops": cand["drops_mobs"],
                        "classes": cand["classes_str"],
                        "ratio10": cand["ratio10"],
                        "url": cand["url"],
                        "why": (
                            cand["why"] if rank == 1 else (
                                "2nd ratio" if cand["is_weapon"] and rank == 2 else (
                                f"alt ratio #{rank}" if cand["is_weapon"] else (
                                f"2nd {KEY_TO_LABEL.get(stat_key, stat_key)}" if rank == 2 else f"alt #{rank} {KEY_TO_LABEL.get(stat_key, stat_key)}"
                                )))
                        ),
                        "bis_overlap": cand["bis_overlap"],
                        "stats_plus10": dict(cand.get("stats_plus10") or {}),
                    }
                )

    for slot in PLANNER_SLOTS:
        ranked = rank_for_slot(pool, slot, "max", None)
        seen = set()
        rank = 0
        for cand in ranked:
            if cand["name"] in seen:
                continue
            seen.add(cand["name"])
            rank += 1
            if rank > 6:
                break
            max_rows.append(
                {
                    "mode": "Max All Stats",
                    "stat": "(all)",
                    "stat_key": "",
                    "slot": slot,
                    "rank": rank,
                    "name": cand["name"],
                    "pval": cand["pval"],
                    "score": round(cand["score"], 4),
                    "zone": cand["zone"],
                    "drops": cand["drops_mobs"],
                    "classes": cand["classes_str"],
                    "ratio10": cand["ratio10"],
                    "url": cand["url"],
                    "why": (
                cand["why"] if rank == 1 else (
                    "2nd ratio" if cand["is_weapon"] and rank == 2 else (
                    f"alt ratio #{rank}" if cand["is_weapon"] else (
                    "2nd total score" if rank == 2 else f"alt #{rank} total"
                    )))
            ),
                    "bis_overlap": cand["bis_overlap"],
                    "stats_plus10": dict(cand.get("stats_plus10") or {}),
                }
            )

    return priority_rows, max_rows


LOOKUP_STAT10_COLS = [
    ("AC", "AC +10"), ("HP", "HP +10"), ("MANA", "Mana +10"), ("END", "END +10"),
    ("STR", "STR +10"), ("STA", "STA +10"), ("AGI", "AGI +10"), ("DEX", "DEX +10"),
    ("WIS", "WIS +10"), ("INT", "INT +10"), ("CHA", "CHA +10"),
    ("SVF", "SV Fire +10"), ("SVC", "SV Cold +10"), ("SVM", "SV Magic +10"),
    ("SVP", "SV Poison +10"), ("SVD", "SV Disease +10"),
    ("DMG", "DMG +10"), ("DLY", "DLY"), ("ATK", "ATK +10"), ("Haste", "Haste +10"),
]


def write_lookup_sheet(ws, rows, title_note: str):
    headers = [
        "Mode", "Stat", "Slot", "Rank", "Item", "Priority Stat +10", "Total score", "Why",
        "Zone", "Drops", "Classes", "Ratio +10", "URL", "BiS overlap",
    ] + [lab for _, lab in LOOKUP_STAT10_COLS]
    ws.append(headers)
    for r in rows:
        s10 = r.get("stats_plus10") or {}
        # weapons: ensure DMG/DLY visible from ratio fields if missing
        if r.get("ratio10") is not None and s10.get("DMG") is None and s10.get("DLY") is None:
            pass
        row = [
            r["mode"],
            r["stat"],
            r["slot"],
            r["rank"],
            r["name"],
            bx.clean_num(r["pval"]),
            bx.clean_num(r["score"]),
            r["why"],
            r["zone"],
            r["drops"],
            r["classes"],
            bx.clean_num(r["ratio10"]),
            r["url"],
            r["bis_overlap"],
        ]
        for key, _lab in LOOKUP_STAT10_COLS:
            row.append(bx.clean_num(s10.get(key)))
        ws.append(row)
    bx.style_header(ws, len(headers))
    bx.autosize(ws, max_width=22)
    url_col = headers.index("URL") + 1
    for row_idx in range(2, ws.max_row + 1):
        cell = ws.cell(row_idx, url_col)
        if cell.value:
            cell.hyperlink = cell.value
            cell.style = "Hyperlink"
    ws.freeze_panes = "E2"
    from openpyxl.utils import get_column_letter as _gcl
    ws.auto_filter.ref = f"A1:{_gcl(len(headers))}{ws.max_row}"
    ws.sheet_state = "hidden" if title_note == "hidden" else "visible"


def write_scores_helper(ws, priority_rows, max_rows):
    """Combined helper for INDEX/MATCH: key = Mode|Stat|Slot|Rank"""
    score_stat_cols = [
        ("AC", "AC10"), ("HP", "HP10"), ("MANA", "Mana10"),
        ("STR", "STR10"), ("STA", "STA10"), ("AGI", "AGI10"), ("DEX", "DEX10"),
        ("WIS", "WIS10"), ("INT", "INT10"), ("CHA", "CHA10"),
        ("SVF", "SVFire10"), ("SVC", "SVCold10"), ("SVM", "SVMagic10"),
        ("SVP", "SVPoison10"), ("SVD", "SVDisease10"),
        ("DMG", "DMG10"), ("DLY", "DLY"),
    ]
    headers = [
        "Key", "Mode", "Stat", "Slot", "Rank", "Item", "PriorityStat10", "TotalScore",
        "Zone", "Drops", "Classes", "Ratio10", "URL", "Why",
    ] + [lab for _, lab in score_stat_cols]
    ws.append(headers)
    for r in priority_rows + max_rows:
        # For Max All, Stat in key is blank-normalized to ALL
        stat_part = r["stat"] if r["mode"] == "Priority Stat" else "ALL"
        key = f"{r['mode']}|{stat_part}|{r['slot']}|{r['rank']}"
        s10 = r.get("stats_plus10") or {}
        row = [
            key,
            r["mode"],
            stat_part if r["mode"] == "Max All Stats" else r["stat"],
            r["slot"],
            r["rank"],
            r["name"],
            bx.clean_num(r["pval"]),
            bx.clean_num(r["score"]),
            r["zone"],
            r["drops"],
            r["classes"],
            bx.clean_num(r["ratio10"]),
            r["url"],
            r["why"],
        ]
        for key_s, _lab in score_stat_cols:
            row.append(bx.clean_num(s10.get(key_s)))
        ws.append(row)
    bx.style_header(ws, len(headers))
    bx.autosize(ws, max_width=28)
    ws.sheet_state = "hidden"


def write_stat_planner(wb, n_scores: int):
    ws = wb.create_sheet("Stat planner", 2)
    ws["A1"] = "EQ Legends — Stat Planner (default Paladin + Monk + Wizard; any 1–3 of 16)"
    ws["A1"].font = Font(bold=True, size=14, color="1F4E79")
    ws.merge_cells("A1:J1")

    ws["A2"] = "Mode:"
    ws["A2"].font = Font(bold=True)
    ws["B2"] = "Priority Stat"
    ws["B2"].fill = SELECT_FILL
    ws["B2"].font = Font(bold=True)
    dv_mode = DataValidation(type="list", formula1='"Priority Stat,Max All Stats"', allow_blank=False)
    ws.add_data_validation(dv_mode)
    dv_mode.add(ws["B2"])

    ws["A3"] = "Priority Stat:"
    ws["A3"].font = Font(bold=True)
    ws["B3"] = "INT"
    ws["B3"].fill = SELECT_FILL
    ws["B3"].font = Font(bold=True)
    stat_list = ",".join(PRIORITY_LABELS)
    dv_stat = DataValidation(type="list", formula1=f'"{stat_list}"', allow_blank=False)
    ws.add_data_validation(dv_stat)
    dv_stat.add(ws["B3"])

    ws["A4"] = "Upgrade:"
    ws["B4"] = "Scores use +10 scaled stats (weapons: Ratio +10). Change Mode/Priority Stat — loadout updates via lookup."
    ws["B4"].fill = NOTE_FILL
    ws.merge_cells("B4:J4")

    ws["A5"] = "Scoring:"
    ws["B5"] = (
        "Priority ≈ priority×100 + 0.15×other + haste×2; Weapons ≈ Ratio+10×10000 + priority×10. "
        "Max All ≈ HP+Mana+AC×2+attrs×1.5+resists + haste×2; Weapons ≈ Ratio×10000 + 0.2×stat_sum. "
        "Prefer multi-class BiS when within ~5%."
    )
    ws.merge_cells("B5:J5")

    ws["A6"] = "Haste:"
    ws["B6"] = (
        "ONLY ONE worn haste item counts (tooltip 'Haste: +N%'; does not scale). "
        "Loadout picks the single best Haste% piece; other haste gear is excluded so haste never stacks. "
        "Change planner classes on Class selector (B2–B4); scores precomputed for build-time trio (default PAL+MNK+WIZ). "
        "FINGER1/2 and EAR1/2 pick distinct pieces. Weapons rank by Ratio +10 first."
    )
    ws.merge_cells("B6:J6")

    # Recommended loadout table starting row 8
    headers = [
        "Slot", "Recommended Item", "Priority Stat value (+10)", "Total score", "Why",
        "AC +10", "HP +10", "Mana +10", "STR +10", "STA +10", "AGI +10", "DEX +10",
        "WIS +10", "INT +10", "CHA +10",
        "SV Fire +10", "SV Cold +10", "SV Magic +10", "SV Poison +10", "SV Disease +10",
        "DMG +10", "DLY", "Ratio +10 (weapons)",
        "Zone", "Drops", "Classes", "URL",
    ]
    start = 8
    for col, h in enumerate(headers, 1):
        cell = ws.cell(start, col, h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = THIN

    # Helper key column far right (after loadout stats)
    KEY_COL = 29  # column AC
    ws.cell(7, KEY_COL, "LookupKey")

    # For each slot, rank is 1 for most; EAR2/FINGER2 use rank 2
    rank_for = {s: 1 for s in PLANNER_SLOTS}
    rank_for["EAR2"] = 2
    rank_for["FINGER2"] = 2

    # _scores columns after stats expansion:
    # A Key B Mode C Stat D Slot E Rank F Item G PriorityStat10 H TotalScore
    # I Zone J Drops K Classes L Ratio10 M URL N Why
    # O AC10 P HP10 Q Mana10 R STR10 S STA10 T AGI10 U DEX10 V WIS10 W INT10 X CHA10
    # Y SVFire10 Z SVCold10 AA SVMagic10 AB SVPoison10 AC SVDisease10 AD DMG10 AE DLY
    score_map = [
        (2, "F"),   # Item
        (3, "G"),   # PriorityStat10
        (4, "H"),   # TotalScore
        (5, "N"),   # Why
        (6, "O"),   # AC10
        (7, "P"),   # HP10
        (8, "Q"),   # Mana10
        (9, "R"),   # STR10
        (10, "S"),  # STA10
        (11, "T"),  # AGI10
        (12, "U"),  # DEX10
        (13, "V"),  # WIS10
        (14, "W"),  # INT10
        (15, "X"),  # CHA10
        (16, "Y"),  # SVFire10
        (17, "Z"),  # SVCold10
        (18, "AA"), # SVMagic10
        (19, "AB"), # SVPoison10
        (20, "AC"), # SVDisease10
        (21, "AD"), # DMG10
        (22, "AE"), # DLY
        (23, "L"),  # Ratio10
        (24, "I"),  # Zone
        (25, "J"),  # Drops
        (26, "K"),  # Classes
        (27, "M"),  # URL
    ]

    key_cell = get_column_letter(KEY_COL)

    for i, slot in enumerate(PLANNER_SLOTS):
        row = start + 1 + i
        rank = rank_for[slot]
        ws.cell(row, 1, slot).border = THIN

        key_formula = (
            f'IF($B$2="Max All Stats",$B$2&"|ALL|"&A{row}&"|{rank}",'
            f'$B$2&"|"&$B$3&"|"&A{row}&"|{rank}")'
        )
        ws.cell(row, KEY_COL, f"={key_formula}")

        for dest_col, src_letter in score_map:
            formula = (
                f"=IFERROR(INDEX('_scores'!{src_letter}:{src_letter},"
                f"MATCH({key_cell}{row},'_scores'!A:A,0)),\"\")"
            )
            cell = ws.cell(row, dest_col, formula)
            cell.border = THIN
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.cell(row, 1).border = THIN

    ws.column_dimensions[key_cell].hidden = True

    widths = {
        "A": 12, "B": 34, "C": 14, "D": 12, "E": 16,
        "F": 9, "G": 9, "H": 10, "I": 9, "J": 9, "K": 9, "L": 9,
        "M": 9, "N": 9, "O": 9, "P": 11, "Q": 11, "R": 12, "S": 12, "T": 12,
        "U": 9, "V": 8, "W": 12, "X": 18, "Y": 22, "Z": 22, "AA": 36,
    }
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    ws.freeze_panes = "A9"

    # Alternates section
    alt_start = start + 2 + len(PLANNER_SLOTS)
    ws.cell(alt_start, 1, "Top alternates (same Mode/Stat) — ranks 2–6 for selected slot in B" + str(alt_start + 1))
    ws.cell(alt_start, 1).font = Font(bold=True, color="1F4E79")
    ws.merge_cells(start_row=alt_start, start_column=1, end_row=alt_start, end_column=6)

    ws.cell(alt_start + 1, 1, "Slot for alternates:")
    ws.cell(alt_start + 1, 2, "HEAD")
    ws.cell(alt_start + 1, 2).fill = SELECT_FILL
    slot_list = ",".join(PLANNER_SLOTS)
    dv_slot = DataValidation(type="list", formula1=f'"{slot_list}"', allow_blank=False)
    ws.add_data_validation(dv_slot)
    dv_slot.add(ws.cell(alt_start + 1, 2))

    alt_hdr_row = alt_start + 2
    alt_headers = [
        "Rank", "Item", "Priority +10", "Score", "Why",
        "AC +10", "HP +10", "Mana +10", "WIS +10", "INT +10", "Ratio +10", "URL",
    ]
    for col, h in enumerate(alt_headers, 1):
        cell = ws.cell(alt_hdr_row, col, h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = THIN

    b_alt = f"$B${alt_start + 1}"
    alt_map = [
        (2, "F"), (3, "G"), (4, "H"), (5, "N"),
        (6, "O"), (7, "P"), (8, "Q"), (9, "V"), (10, "W"), (11, "L"), (12, "M"),
    ]
    for ri, rank in enumerate(range(2, 7)):
        row = alt_hdr_row + 1 + ri
        ws.cell(row, 1, rank).border = THIN
        key_f = (
            f'IF($B$2="Max All Stats",$B$2&"|ALL|"&{b_alt}&"|{rank}",'
            f'$B$2&"|"&$B$3&"|"&{b_alt}&"|{rank}")'
        )
        ws.cell(row, KEY_COL, f"={key_f}")
        for dest_col, src_letter in alt_map:
            cell = ws.cell(
                row,
                dest_col,
                f"=IFERROR(INDEX('_scores'!{src_letter}:{src_letter},MATCH({key_cell}{row},'_scores'!A:A,0)),\"\")",
            )
            cell.border = THIN
            cell.fill = ALT_FILL
        ws.cell(row, 1).fill = ALT_FILL

    return ws
    return ws


def write_how_to_use_extended(wb, summary, weapon_counts, pool_count, planner_classes=None):
    planner_classes = list(planner_classes or TARGET)
    trio_txt = " + ".join(planner_classes)
    ws = wb.create_sheet("How to use", 0)
    counts = summary.get("counts") or {}
    lines = [
        "Josh's EverQuest Legends BiS Spreadsheet",
        "",
        "Source: https://eqlegendstools.com (fan site — not affiliated with Daybreak/EQ)",
        f"Catalog/runtime version: {summary.get('meta_version', 'unknown')} (site v4.8.x; data refreshed ~Sep 2 2026 per site activity text when captured)",
        f"Data decoded from guarded /api/r/* BiS bundles for ALL 16 classes + catalog.",
        f"Classes: {', '.join(summary.get('classes') or list(ALL_CLASSES))}",
        "",
        "*** STAT PLANNER ***",
        f"Open the 'Stat planner' sheet for interactive recommendations (build-time trio: {trio_txt}).",
        "1. Set Mode (B2): Priority Stat | Max All Stats",
        "2. Set Priority Stat (B3): AC, HP, Mana, STR, STA, AGI, DEX, WIS, INT, CHA, SV resists, END",
        "3. Recommended loadout updates via INDEX/MATCH against hidden '_scores' helper (precomputed at +10).",
        "4. FINGER1/FINGER2 and EAR1/EAR2 recommend two different items. Weapons always rank by Ratio +10 first.",
        "5. Class selector B2–B4: pick any 1–3 of the 16 classes (use (none) to leave empty). Default Paladin/Monk/Wizard.",
        "",
        "*** HASTE (important) ***",
        "ONLY ONE worn haste item counts on a character. Worn haste is the tooltip line 'Haste: +N%' (Haste +0/+10 columns; value does NOT scale with upgrade).",
        "Spell Haste / Summoning Haste / focus effects are NOT worn haste and are left in Effect text only.",
        "BiS ranking / Stat planner loadout: prefer the single best Haste% piece; do NOT stack multiple haste items.",
        "Individual item scores still SHOW haste and give a small haste preference; the loadout builder then keeps at most one haste item (highest % wins).",
        "",
        "Scoring (all on +10 scaled stats; weapons Ratio +10; haste non-scaling)",
        "Priority Stat mode (armor/jewelry): score ≈ priority_stat × 100 + 0.15 × sum(other positive AC/HP/Mana/attrs/resists) + Haste×2.",
        "Priority Stat mode (weapons): score ≈ Ratio+10 × 10000 + priority_stat × 10 + 0.15 × other + Haste×2 (damage dominates).",
        "Max All Stats mode (armor/jewelry): HP×1 + Mana×1 + AC×2 + (STR+STA+AGI+DEX+WIS+INT+CHA)×1.5 + resists×1 + END×0.5 + Haste×2.",
        "Max All Stats mode (weapons): Ratio+10 × 10000 + 0.2 × that weighted stat sum + Haste×2.",
        f"Only items usable by the planner trio ({trio_txt}). When scores are within ~5%, prefer items on multiple class BiS lists.",
        f"Planner item pool size this build: {pool_count} (merged BiS gear + catalog weapons).",
        "",
        "*** WEAPON BUG FIX (Sep 2026) ***",
        "Prior workbook versions were WRONG on weapons: BiS gear bundles barely include weapon rows,",
        "and PRIMARY rows sometimes showed Item=None with bogus ~0.65 ratios. Real weapons live in",
        "catalog.weapons (202 total). This rebuild adds dedicated weapon sheets from the catalog,",
        "uses catalog.weaponName, and computes DMG/Ratio with the site formula from sample-item.html:",
        "  scaledDamage = Math.floor(dmg * (1 + level/10));  Ratio = scaledDamage / delay;  DLY does NOT scale.",
        "Verified examples (Paladin):",
        "  Ghoulbane: 15/34 = 0.4412 @+0 → 30/34 = 0.8824 @+10",
        "  Aldryn, Blade of the Ocean: 20/26 = 0.7692 @+0 → 40/26 = 1.5385 @+10",
        "  Thelvorn, Blade of Light: same 20/26 → 40/26 = 1.5385 @+10",
        "  Truvinan: 32/40 = 0.8000 @+0 → 64/40 = 1.6000 @+10 (highest Paladin ratio in catalog)",
        "",
        "How to use",
        f"1. Start on 'Stat planner' for Mode + Priority Stat driven loadouts ({trio_txt}).",
        "2. Open Class selector and set Class 1 / Class 2 / Class 3 (any of the 16, or (none)).",
        "3. Use each class sheet (all 16) for that class's BiS armor/jewelry/shield list.",
        "4. Use 'Weapons (by class)' for catalog weapons usable by the planner trio (sorted by Ratio +10).",
        "5. Use '<Class> weapons top' sheets for per-class rankings (all 16 classes).",
        "   On Paladin weapons top: Truvinan (green), Aldryn (orange), Thelvorn (yellow), Ghoulbane (blue) are highlighted.",
        "6. Intersection sheet = items that appear on ALL selected planner-trio class BiS lists.",
        "7. Sheet 'All gear (all classes)' = unique union of all 16 BiS lists (nameless/broken weapon stubs removed).",
        "8. 'By priority (lookup)' / 'Max all (lookup)' = top item + 5 alternates per slot (and per stat for priority).",
        "",
        "Upgrade levels (+0 vs +10)",
        "EQ Legends Tools scales item stats client-side for upgrade levels 0–10.",
        "Bundles/catalog store BASE (+0) stats only. This workbook applies the site's published formula:",
        "  scaleItemStat(base, level) ≈ floor(base * (1 + level/10)), with max(base+level, …) for positives,",
        "  and special handling for small negatives / large negatives (matches sample-item.html JS).",
        "Weapon DMG uses the same floor(dmg*(1+level/10)); at +10 that is floor(dmg*2).",
        "Scalable: AC, HP, MANA, STR, STA, AGI, DEX, WIS, INT, CHA, END, ATK, SV resists, DMG.",
        "Does NOT scale: DLY (delay), Haste (%), elemental bonus DMG (Fire/Cold DMG), effects/focus text, charges.",
        "Ratio = DMG / DLY when both known.",
        "",
        "Columns (gear sheets)",
        "- Haste +0 / Haste +10: worn haste percent from tooltip 'Haste: +N%' when present (same value; does not scale).",
        "- Other stat columns: base (+0) and site-scaled (+10).",
        "",
        "Columns (weapons sheets)",
        "- Class(es): wearable classes from catalog.weapons.classNames",
        "- 1H/2H: from catalog oneHanded (Yes→1H, No→2H, Ranged→Ranged)",
        "- DMG +0 / DMG +10 / DLY / Ratio +0 / Ratio +10 / Haste +0 / Haste +10",
        "- Proc/Effect: Effect lines joined from catalog.tooltips when available",
        "- URL: https://eqlegendstools.com/items/<slug>/",
        "",
        "Gaps / caveats (fields left blank when missing — nothing invented)",
        "- BiS bundles still under-represent weapons; use the Weapons sheets for true weapon rankings.",
        "- Some gear items lack itemID, zone, drops, or level in the BiS payload.",
        "- Intermediate upgrade levels (+1…+9) are not separate columns; recompute with the formula if needed.",
        "- URLs may 404 if slugification differs from the live site.",
        "- Weapon attribute stats (STR/WIS/etc.) come from catalog.tooltips lines when present.",
        "- Worn haste only when the payload/tooltip has an explicit 'Haste: +N%' line.",
        "",
        "Counts (this build)",
        f"- Unique merged BiS (all 16): {counts.get('merged_unique', 'n/a')}",
        f"- Intersection (PAL+MNK+WIZ BiS lists): {counts.get('tri_bis_intersection_PAL_MNK_WIZ', counts.get('tri_bis_intersection', 'n/a'))}",
        f"- Catalog weapons total: {weapon_counts['total']}",
        f"- Weapons usable by planner trio: {weapon_counts['usable']}",
        f"- Items with worn haste (merged): {counts.get('items_with_worn_haste', 'n/a')}",
        f"- Planner pool (gear∪weapons): {pool_count}",
        f"- +0 and +10 both available: YES (+10 derived via site formula from +0 base stats; Haste non-scaling)",
        "",
        "Per-class BiS item counts:",
    ]
    for cls in ALL_CLASSES:
        lines.append(f"- {cls}: {counts.get('bis_' + cls, weapon_counts.get(cls, 'n/a'))}")
    lines += [
        "",
        "Credit: Item/BiS data © respective authors on eqlegendstools.com. Spreadsheet assembly for Josh Monroe.",
    ]
    section_headers = {
        "How to use",
        "Upgrade levels (+0 vs +10)",
        "Columns (weapons sheets)",
        "Columns (gear sheets)",
        "Gaps / caveats (fields left blank when missing — nothing invented)",
        "Counts (this build)",
        "*** WEAPON BUG FIX (Sep 2026) ***",
        "*** STAT PLANNER ***",
        "*** HASTE (important) ***",
        "Scoring (all on +10 scaled stats; weapons Ratio +10; haste non-scaling)",
        "Per-class BiS item counts:",
    }
    for i, line in enumerate(lines, 1):
        cell = ws.cell(i, 1, line)
        if i == 1:
            cell.font = Font(bold=True, size=16, color="1F4E79")
        elif line in section_headers:
            cell.font = Font(bold=True, size=12, color="1F4E79")
    ws.column_dimensions["A"].width = 120


def set_planner_target(classes):
    """Update module-level TARGET / TARGET_SET used by pool filters."""
    global TARGET, TARGET_SET
    cleaned = [c for c in classes if c and c != "(none)"]
    if not cleaned:
        cleaned = list(bx.DEFAULT_TRIO)
    TARGET = tuple(cleaned)
    TARGET_SET = set(TARGET)


def main():
    global TARGET, TARGET_SET
    # Default trio still Paladin+Monk+Wizard; Class selector allows any 1–3 of 16 at rebuild time
    planner_classes = tuple(bx.DEFAULT_TRIO)
    set_planner_target(planner_classes)

    loaded = bx.load_rows(planner_classes=planner_classes)
    merged, per, tri, summary, catalog, planner_classes = loaded
    set_planner_target(planner_classes)
    slug_map = bx.load_slug_map()

    weapons_all = bx.weapon_records(catalog, slug_map, target_classes=planner_classes)
    weapons_catalog_all = bx.weapon_records(catalog, slug_map, any_class=True)
    per_weapons = {
        cls: [w for w in weapons_catalog_all if cls in w["classes"] or "ALL" in w["classes"]]
        for cls in ALL_CLASSES
    }
    for cls in ALL_CLASSES:
        per_weapons[cls].sort(key=lambda r: (-(r["ratio10"] or 0), r["name"]))

    gear_per = {cls: bx.filter_gear_rows(per.get(cls, [])) for cls in ALL_CLASSES}
    gear_tri = bx.filter_gear_rows(tri)
    # Merged gear usable by planner trio (for All gear sheet subset) + full union sheet
    gear_merged_all = bx.filter_gear_rows(merged)
    gear_merged_trio = [
        r for r in gear_merged_all
        if usable_by_tri(r.get("classes") or [])
    ]

    weapon_counts = {
        "total": len(catalog.get("weapons") or []),
        "usable": len(weapons_all),
    }
    for cls in ALL_CLASSES:
        weapon_counts[cls] = len(per_weapons[cls])

    gear_counts = {cls: len(gear_per[cls]) for cls in ALL_CLASSES}
    gear_counts["tri"] = len(gear_tri)
    gear_counts["merged"] = len(gear_merged_all)

    # Sanity checks on known weapons
    by_name = {w["name"]: w for w in weapons_catalog_all}
    gh = by_name.get("Ghoulbane")
    al = by_name.get("Aldryn, Blade of the Ocean")
    tr = by_name.get("Truvinan")
    th = by_name.get("Thelvorn, Blade of Light")
    assert gh and abs(gh["ratio0"] - 0.4412) < 1e-4 and abs(gh["ratio10"] - 0.8824) < 1e-4, gh
    assert al and abs(al["ratio0"] - 0.7692) < 1e-4 and abs(al["ratio10"] - 1.5385) < 1e-4, al
    assert th and abs(th["ratio10"] - 1.5385) < 1e-4, th
    assert tr and abs(tr["ratio0"] - 0.8) < 1e-4 and abs(tr["ratio10"] - 1.6) < 1e-4, tr

    pool = build_item_pool(merged, catalog, slug_map)
    priority_rows, max_rows = build_lookup_tables(pool)
    priority_rows, max_rows = apply_haste_loadout_to_lookup(priority_rows, max_rows, pool)

    # Verification loadouts
    verify = {"planner_classes": list(planner_classes), "haste_rule": "at most one worn haste item"}
    for label, mode, sk in [
        ("Priority_INT", "priority", "INT"),
        ("Priority_WIS", "priority", "WIS"),
        ("Max_All_Stats", "max", None),
    ]:
        loadout = pick_loadout(pool, mode, sk)
        haste_picks = []
        sample = {}
        for slot in PLANNER_SLOTS:
            r = loadout.get(slot) or {}
            if not r.get("name"):
                continue
            h = item_haste(r.get("item") or {"stats_plus10": r.get("stats_plus10") or {}})
            # stats may be on cand directly
            if h <= 0:
                h = num((r.get("stats_plus10") or {}).get("Haste"))
            if h > 0:
                haste_picks.append({"slot": slot, "item": r.get("name"), "haste": h})
            if slot in ("HEAD", "CHEST", "PRIMARY", "WAIST", "BACK", "HANDS"):
                sample[slot] = {
                    "item": r.get("name"),
                    "priority_stat_value": r.get("pval"),
                    "total_score": round(r.get("score") or 0, 4),
                    "ratio10": r.get("ratio10"),
                    "why": r.get("why"),
                    "classes": r.get("classes_str"),
                    "zone": r.get("zone"),
                    "haste": h if h > 0 else None,
                }
        verify[label] = {"slots": sample, "haste_items_in_loadout": haste_picks}
        assert len(haste_picks) <= 1, f"haste stacking in {label}: {haste_picks}"

    VERIFY.write_text(json.dumps(verify, indent=2), encoding="utf-8")
    print("VERIFY", json.dumps(verify, indent=2))

    wb = Workbook()
    default = wb.active
    wb.remove(default)

    write_how_to_use_extended(wb, summary, weapon_counts, len(pool), planner_classes)
    bx.write_class_selector(wb, summary, weapon_counts, gear_counts, planner_classes)
    write_stat_planner(wb, len(priority_rows) + len(max_rows))

    ws_pri = wb.create_sheet("By priority (lookup)")
    write_lookup_sheet(ws_pri, priority_rows, "visible")
    ws_max = wb.create_sheet("Max all (lookup)")
    write_lookup_sheet(ws_max, max_rows, "visible")

    ws_scores = wb.create_sheet("_scores")
    write_scores_helper(ws_scores, priority_rows, max_rows)

    ws_wep = wb.create_sheet("Weapons (by class)")
    bx.write_weapon_sheet(ws_wep, weapons_all, highlight=True)

    trio_label = "+".join(
        {"Paladin": "PAL", "Monk": "MNK", "Wizard": "WIZ"}.get(c, c[:3].upper())
        for c in planner_classes
    )
    ws_tri = wb.create_sheet(f"{trio_label} BiS"[:31])
    bx.write_gear_rows(ws_tri, gear_tri)

    for cls in ALL_CLASSES:
        ws = wb.create_sheet(cls[:31])
        bx.write_gear_rows(ws, gear_per[cls])

    ws_all = wb.create_sheet("All gear (all classes)")
    bx.write_gear_rows(ws_all, gear_merged_all)

    ws_trio_gear = wb.create_sheet("All gear (planner trio)")
    bx.write_gear_rows(ws_trio_gear, gear_merged_trio)

    for cls in ALL_CLASSES:
        ws = wb.create_sheet(f"{cls} weapons top"[:31])
        bx.write_weapon_sheet(ws, per_weapons[cls], highlight=(cls == "Paladin"))

    for path_out in (XLSX, XLSX_FIXED):
        wb.save(path_out)
        print(f"Wrote {path_out}")

    print("sheets:", wb.sheetnames)
    print("pool_size", len(pool))
    print("priority_lookup_rows", len(priority_rows), "max_lookup_rows", len(max_rows))
    print("gear_counts", {k: gear_counts[k] for k in list(ALL_CLASSES)[:3] + ["tri", "merged"]})
    print("weapon_counts usable/total", weapon_counts["usable"], weapon_counts["total"])
    haste_in_pool = sum(1 for it in pool if item_haste(it) > 0)
    print("pool_items_with_haste", haste_in_pool)


if __name__ == "__main__":
    main()
