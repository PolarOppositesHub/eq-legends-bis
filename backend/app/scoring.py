"""BiS ranking + haste rules ported from /workspace/eq-legends/build_planner.py."""
from __future__ import annotations

from copy import deepcopy

PLANNER_SLOTS = [
    "HEAD", "FACE", "EAR1", "EAR2", "NECK", "SHOULDERS", "ARMS", "WRIST",
    "HANDS", "CHEST", "BACK", "WAIST", "LEGS", "FEET",
    "FINGER1", "FINGER2", "PRIMARY", "SECONDARY", "RANGE", "AMMO",
]

SLOT_ALIASES = {
    "HEAD": ["HEAD"], "FACE": ["FACE"], "EAR": ["EAR1", "EAR2"], "NECK": ["NECK"],
    "SHOULDERS": ["SHOULDERS"], "ARMS": ["ARMS"], "WRIST": ["WRIST"], "HANDS": ["HANDS"],
    "CHEST": ["CHEST"], "BACK": ["BACK"], "WAIST": ["WAIST"], "LEGS": ["LEGS"],
    "FEET": ["FEET"], "FINGER": ["FINGER1", "FINGER2"], "PRIMARY": ["PRIMARY"],
    "SECONDARY": ["SECONDARY"], "RANGE": ["RANGE"], "RANGED": ["RANGE"], "AMMO": ["AMMO"],
}

ATTR_KEYS = ["AC", "HP", "MANA", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA"]
RESIST_KEYS = ["SVF", "SVC", "SVM", "SVP", "SVD", "SVV"]
OTHER_SCORE_KEYS = ATTR_KEYS + RESIST_KEYS

PRIORITY_STATS = [
    ("AC", "AC"), ("HP", "HP"), ("MANA", "Mana"), ("END", "END"),
    ("STR", "STR"), ("STA", "STA"), ("AGI", "AGI"), ("DEX", "DEX"),
    ("WIS", "WIS"), ("INT", "INT"), ("CHA", "CHA"),
    ("SVF", "SV Fire"), ("SVC", "SV Cold"), ("SVM", "SV Magic"),
    ("SVP", "SV Poison"), ("SVD", "SV Disease"),
]

PRIORITY_LABELS = [lab for _, lab in PRIORITY_STATS]
LABEL_TO_KEY = {lab: key for key, lab in PRIORITY_STATS}
KEY_TO_LABEL = {key: lab for key, lab in PRIORITY_STATS}


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
    h = item_haste(item)
    return h * 2.0 if h > 0 else 0.0


def expand_slots(slot_field) -> list[str]:
    if isinstance(slot_field, list):
        parts = [str(s).strip().upper() for s in slot_field if s]
    else:
        parts = [p.strip().upper() for p in str(slot_field or "").split("/") if p.strip()]
    out = []
    for p in parts:
        out.extend(SLOT_ALIASES.get(p, []))
    seen, uniq = set(), []
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


def other_positive_sum(s10: dict, exclude_key: str | None = None) -> float:
    total = 0.0
    for k in OTHER_SCORE_KEYS:
        if exclude_key and k == exclude_key:
            continue
        total += positive(num(s10.get(k)))
    if exclude_key != "END":
        total += positive(num(s10.get("END")))
    return total


def max_all_stat_sum(s10: dict) -> float:
    hp = num(s10.get("HP"))
    mana = num(s10.get("MANA"))
    ac = num(s10.get("AC"))
    attrs = sum(num(s10.get(k)) for k in ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA"))
    resists = sum(num(s10.get(k)) for k in RESIST_KEYS)
    end = num(s10.get("END"))
    return hp * 1.0 + mana * 1.0 + ac * 2.0 + attrs * 1.5 + resists * 1.0 + end * 0.5


def score_priority(item: dict, stat_key: str) -> tuple[float, float, str]:
    s10 = item.get("stats_plus10") or {}
    pval = num(s10.get(stat_key))
    hb = haste_bonus(item)
    weapon = item.get("is_weapon") and item.get("ratio_plus10") is not None
    if weapon:
        ratio10 = num(item.get("ratio_plus10"))
        other = other_positive_sum(s10, exclude_key=stat_key)
        score = ratio10 * 10000.0 + pval * 10.0 + 0.15 * other + hb
        return score, pval, "best ratio"
    other = other_positive_sum(s10, exclude_key=stat_key)
    score = pval * 100.0 + 0.15 * other + hb
    why = f"highest {KEY_TO_LABEL.get(stat_key, stat_key)}"
    return score, pval, why


def score_max_all(item: dict) -> tuple[float, float, str]:
    s10 = item.get("stats_plus10") or {}
    bang = max_all_stat_sum(s10)
    hb = haste_bonus(item)
    weapon = item.get("is_weapon") and item.get("ratio_plus10") is not None
    if weapon:
        ratio10 = num(item.get("ratio_plus10"))
        score = ratio10 * 10000.0 + 0.2 * bang + hb
        return score, bang, "best ratio"
    return bang + hb, bang, "best total score"


def prefer_multi_class(ranked: list[dict], within_pct: float = 0.05) -> list[dict]:
    if not ranked:
        return ranked
    best = ranked[0]["score"]
    top_band = [r for r in ranked if r["score"] >= best * (1 - within_pct)]
    rest = [r for r in ranked if r["score"] < best * (1 - within_pct)]
    top_band.sort(key=lambda r: (-r.get("bis_overlap", 0), -r.get("tri_classes", 0), -r["score"], r["name"]))
    return top_band + rest


def is_weapon_item(item: dict) -> bool:
    if item.get("is_weapon"):
        return True
    bases = set(base_slots_from_item(item))
    if bases & {"PRIMARY", "SECONDARY", "RANGE", "AMMO"} and (
        item.get("ratio_plus10") is not None
        or num((item.get("stats_plus0") or {}).get("DMG")) > 0
        or num((item.get("stats_plus10") or {}).get("DMG")) > 0
    ):
        if "AMMO" in bases and not (bases & {"PRIMARY", "SECONDARY", "RANGE"}):
            return True
        if item.get("ratio_plus10") is not None or (
            num((item.get("stats_plus0") or {}).get("DMG")) > 0
            and num((item.get("stats_plus0") or {}).get("DLY")) > 0
        ):
            return True
    return False


def prepare_item(raw: dict, selected: set[str]) -> dict | None:
    classes = list(raw.get("classes") or [])
    cl = {str(c) for c in classes}
    if "ALL" not in cl and not (cl & selected):
        return None
    item = deepcopy(raw)
    item["planner_slots"] = expand_slots(item.get("slots") or item.get("slot"))
    item["is_weapon"] = is_weapon_item(item)
    item["classes_str"] = item.get("classes_str") or ", ".join(classes)
    bis_for = set(item.get("bis_for") or [])
    item["bis_overlap"] = len(bis_for & selected) if bis_for else 0
    if "ALL" in cl:
        item["tri_classes"] = len(selected)
    else:
        item["tri_classes"] = len(cl & selected)
    return item


def rank_for_slot(pool: list[dict], planner_slot: str, mode: str, stat_key: str | None) -> list[dict]:
    if planner_slot in ("EAR1", "EAR2"):
        match_slots = {"EAR1", "EAR2"}
    elif planner_slot in ("FINGER1", "FINGER2"):
        match_slots = {"FINGER1", "FINGER2"}
    else:
        match_slots = {planner_slot}

    candidates = []
    for item in pool:
        pslots = set(item.get("planner_slots") or [])
        if not (pslots & match_slots):
            continue
        if mode == "priority":
            score, pval, why = score_priority(item, stat_key or "INT")
        else:
            score, pval, why = score_max_all(item)
        if item.get("is_weapon") and item.get("ratio_plus10") is not None:
            why = "best ratio"
        candidates.append({
            "name": item["name"],
            "score": score,
            "pval": pval,
            "why": why,
            "zone": item.get("zone") or "",
            "drops_mobs": item.get("drops_mobs") or "",
            "classes_str": item.get("classes_str") or "",
            "classes": item.get("classes") or [],
            "bis_for": item.get("bis_for") or [],
            "ratio0": item.get("ratio_plus0"),
            "ratio10": item.get("ratio_plus10"),
            "url": item.get("url") or "",
            "bis_overlap": item.get("bis_overlap", 0),
            "tri_classes": item.get("tri_classes", 0),
            "is_weapon": item.get("is_weapon", False),
            "stats_plus0": item.get("stats_plus0") or {},
            "stats_plus10": item.get("stats_plus10") or {},
            "haste": item_haste(item),
            "planner_slots": item.get("planner_slots") or [],
            "slot": item.get("slot") or "",
            "item": item,
        })
    candidates.sort(key=lambda r: (-r["score"], -r["bis_overlap"], r["name"]))
    return prefer_multi_class(candidates, 0.05)


def pick_loadout(pool: list[dict], mode: str, stat_key: str | None) -> dict[str, dict]:
    """Pick one item per planner slot; only ONE worn-haste item (highest %)."""
    used_names: set[str] = set()
    loadout: dict[str, dict] = {}
    groups = [
        ["HEAD"], ["FACE"], ["EAR1", "EAR2"], ["NECK"], ["SHOULDERS"], ["ARMS"],
        ["WRIST"], ["HANDS"], ["CHEST"], ["BACK"], ["WAIST"], ["LEGS"], ["FEET"],
        ["FINGER1", "FINGER2"], ["PRIMARY"], ["SECONDARY"], ["RANGE"], ["AMMO"],
    ]

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
            h = item_haste(cand.get("item") or {})
            if h > 0 and cand["name"] != reserved_haste_name:
                continue
            picks.append(cand)
            if len(picks) >= len(group):
                break
        for slot, cand in zip(group, picks):
            used_names.add(cand["name"])
            row = dict(cand)
            row["slot"] = slot
            # strip nested item for API size
            row.pop("item", None)
            loadout[slot] = row
        for slot in group:
            if slot not in loadout:
                loadout[slot] = {
                    "slot": slot, "name": "", "score": 0, "pval": 0, "why": "no item",
                    "zone": "", "drops_mobs": "", "classes_str": "", "ratio10": None,
                    "url": "", "stats_plus0": {}, "stats_plus10": {}, "haste": 0,
                    "is_weapon": False,
                }
    return loadout


def serialize_ranked(cands: list[dict], limit: int = 15) -> list[dict]:
    out = []
    for c in cands[:limit]:
        row = {k: v for k, v in c.items() if k != "item"}
        out.append(row)
    return out
