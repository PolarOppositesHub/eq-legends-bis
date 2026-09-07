"""Enhanced BiS scoring: multi-tier priority, class-aware max-all, AI choice, regen.

Canonical formulas used by engine via build_planner (vendor twin must stay in sync).
Item numeric stats come only from decoded JSON / tooltip-parsed regen — never invented.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from . import ac_softcap
from . import class_roles as roles

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
REGEN_KEYS = ("HP_REGEN", "MANA_REGEN", "END_REGEN")

PRIORITY_STATS = [
    ("AC", "AC"), ("HP", "HP"), ("MANA", "Mana"), ("END", "END"),
    ("STR", "STR"), ("STA", "STA"), ("AGI", "AGI"), ("DEX", "DEX"),
    ("WIS", "WIS"), ("INT", "INT"), ("CHA", "CHA"),
    ("HP_REGEN", "HP Regen"), ("MANA_REGEN", "Mana Regen"), ("END_REGEN", "End Regen"),
    ("SVF", "SV Fire"), ("SVC", "SV Cold"), ("SVM", "SV Magic"),
    ("SVP", "SV Poison"), ("SVD", "SV Disease"),
]

PRIORITY_LABELS = [lab for _, lab in PRIORITY_STATS]
LABEL_TO_KEY = {lab: key for key, lab in PRIORITY_STATS}
KEY_TO_LABEL = {key: lab for key, lab in PRIORITY_STATS}

_REGEN_RE = re.compile(r"(HP|Mana|End)\s*Regen:\s*\+?(\d+)", re.I)

# Tier multipliers for multi-stat priority mode
TIER_WEIGHTS = {"primary": 100.0, "secondary": 25.0, "tertiary": 6.0}


def num(v, default=0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def positive(v: float) -> float:
    return v if v > 0 else 0.0


def parse_regen_from_text(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for kind, val in _REGEN_RE.findall(text or ""):
        key = {"hp": "HP_REGEN", "mana": "MANA_REGEN", "end": "END_REGEN"}[kind.lower()]
        out[key] = out.get(key, 0.0) + float(val)
    return out


def enrich_stats_with_regen(item: dict) -> dict:
    """Return stats_plus10-like dict including tooltip-parsed regen keys."""
    s10 = dict(item.get("stats_plus10") or {})
    chunks: list[str] = []
    tips = item.get("tooltipLines") or []
    if isinstance(tips, list):
        chunks.extend(str(x) for x in tips)
    special = item.get("special") or []
    if isinstance(special, list):
        chunks.extend(str(x) for x in special)
    elif special:
        chunks.append(str(special))
    effect = item.get("effect")
    if effect:
        chunks.append(str(effect))
    parsed = parse_regen_from_text("\n".join(chunks))
    for k, v in parsed.items():
        if num(s10.get(k)) <= 0:
            s10[k] = v
    return s10


def item_haste(item: dict) -> float:
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


def other_positive_sum(s10: dict, exclude_keys: set[str] | None = None) -> float:
    exclude_keys = exclude_keys or set()
    total = 0.0
    for k in OTHER_SCORE_KEYS:
        if k in exclude_keys:
            continue
        total += positive(num(s10.get(k)))
    if "END" not in exclude_keys:
        total += positive(num(s10.get("END")))
    return total


def _norm_stat_list(stats: list[str] | None) -> list[str]:
    out: list[str] = []
    for s in stats or []:
        key = roles.normalize_stat_key(s) or str(s).strip().upper()
        if key and key not in out:
            out.append(key)
    return out[:3]


def default_score_opts(
    *,
    classes: list[str] | None = None,
    primary_stats: list[str] | None = None,
    secondary_stats: list[str] | None = None,
    tertiary_stats: list[str] | None = None,
    maximize_hp_regen: bool = False,
    priority_stat: str | None = None,
    character_level: int = 50,
    combat_stability_rank: int = 3,
    physical_enhancement: bool = True,
    current_worn_ac: float | None = None,
) -> dict[str, Any]:
    classes = [c for c in (classes or []) if c]
    primary = _norm_stat_list(primary_stats)
    secondary = _norm_stat_list(secondary_stats)
    tertiary = _norm_stat_list(tertiary_stats)
    # Back-compat: single priority_stat fills primary if tiers empty
    if not primary and priority_stat:
        key = roles.normalize_stat_key(priority_stat) or priority_stat
        if key in LABEL_TO_KEY:
            key = LABEL_TO_KEY[key]
        primary = [key]
    level = max(1, min(50, int(character_level or 50)))
    softcap = ac_softcap.softcap_target(
        level,
        combat_stability_rank=combat_stability_rank,
        physical_enhancement=physical_enhancement,
    )
    return {
        "classes": classes,
        "primary_stats": primary,
        "secondary_stats": secondary,
        "tertiary_stats": tertiary,
        "maximize_hp_regen": bool(maximize_hp_regen),
        "has_tank": roles.trio_has_tank(classes),
        "uses_mana": roles.trio_uses_mana(classes),
        "attr_weights": roles.trio_primary_attr_weights(classes) if classes else {
            k: 1.5 for k in ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA")
        },
        "roles": roles.trio_roles(classes),
        "character_level": level,
        "combat_stability_rank": max(0, min(3, int(combat_stability_rank))),
        "physical_enhancement": bool(physical_enhancement),
        "ac_softcap": softcap,
        "ac_post_cap_return": ac_softcap.best_post_cap_return(classes),
        # When set (loadout greedy), AC is valued vs remaining softcap room.
        "current_worn_ac": current_worn_ac,
    }


def _item_ac(s10: dict) -> float:
    return num(s10.get("AC"))


def max_all_stat_sum(s10: dict, opts: dict[str, Any] | None = None) -> float:
    """Class-aware Max All Stats weighting with AC soft-cap awareness.

    Hit the AA-raised soft cap first (full value under cap); overcap AC is lightly
    valued via class post-cap return so other stats compete.
    """
    opts = opts or default_score_opts()
    s10 = dict(s10)
    hp = num(s10.get("HP"))
    mana = num(s10.get("MANA"))
    ac = _item_ac(s10)
    resists = sum(num(s10.get(k)) for k in RESIST_KEYS)
    end = num(s10.get("END"))
    attr_w = opts.get("attr_weights") or {}
    attrs = sum(num(s10.get(k)) * float(attr_w.get(k, 1.5)) for k in ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA"))

    # Survivability without drowning attrs: HP gets the tank bump; AC uses softcap model.
    hp_w = 1.55 if opts.get("has_tank") else 1.0
    mana_w = 1.2 if opts.get("uses_mana") else 0.05

    softcap = float(opts.get("ac_softcap") or ac_softcap.softcap_target(opts.get("character_level") or 50))
    post = float(opts.get("ac_post_cap_return") or ac_softcap.best_post_cap_return(opts.get("classes") or []))
    # Standalone ranking (no running loadout AC): assume ~half softcap already worn
    # so mid-build pieces still help fill, but pure AC stacks don't dominate forever.
    if opts.get("current_worn_ac") is None:
        current = softcap * 0.45
    else:
        current = float(opts.get("current_worn_ac") or 0.0)
    ac_score = ac_softcap.valued_ac(ac, current, softcap, post)

    score = hp * hp_w + mana * mana_w + ac_score + attrs + resists * 1.0 + end * 0.5

    if opts.get("maximize_hp_regen"):
        score += num(s10.get("HP_REGEN")) * 40.0
    if opts.get("uses_mana"):
        score += num(s10.get("MANA_REGEN")) * 18.0
    else:
        score += num(s10.get("MANA_REGEN")) * 0.5
    score += num(s10.get("END_REGEN")) * 4.0
    return score


def score_priority_tiers(item: dict, opts: dict[str, Any]) -> tuple[float, float, str]:
    s10 = enrich_stats_with_regen(item)
    primary = opts.get("primary_stats") or []
    secondary = opts.get("secondary_stats") or []
    tertiary = opts.get("tertiary_stats") or []
    hb = haste_bonus(item)
    weapon = item.get("is_weapon") and item.get("ratio_plus10") is not None

    tier_score = 0.0
    pval = 0.0
    labels = []
    used: set[str] = set()
    for tier, keys in (("primary", primary), ("secondary", secondary), ("tertiary", tertiary)):
        w = TIER_WEIGHTS[tier]
        for k in keys:
            used.add(k)
            v = num(s10.get(k))
            tier_score += v * w
            if tier == "primary":
                pval += v
            labels.append(f"{tier[0].upper()}:{KEY_TO_LABEL.get(k, k)}")
    other = other_positive_sum(s10, exclude_keys=used)
    if opts.get("maximize_hp_regen") and "HP_REGEN" not in used:
        tier_score += num(s10.get("HP_REGEN")) * 35.0

    if weapon:
        ratio10 = num(item.get("ratio_plus10"))
        score = ratio10 * 10000.0 + tier_score * 0.1 + 0.15 * other + hb
        return score, pval, "best ratio"
    score = tier_score + 0.15 * other + hb
    why = "priority " + " > ".join(labels) if labels else "priority (none selected)"
    return score, pval, why


def score_priority(item: dict, stat_key: str) -> tuple[float, float, str]:
    opts = default_score_opts(primary_stats=[stat_key or "INT"])
    return score_priority_tiers(item, opts)


def score_max_all(item: dict, opts: dict[str, Any] | None = None) -> tuple[float, float, str]:
    opts = opts or default_score_opts()
    s10 = enrich_stats_with_regen(item)
    bang = max_all_stat_sum(s10, opts)
    hb = haste_bonus(item)
    weapon = item.get("is_weapon") and item.get("ratio_plus10") is not None
    if weapon:
        ratio10 = num(item.get("ratio_plus10"))
        score = ratio10 * 10000.0 + 0.2 * bang + hb
        return score, bang, "best ratio"
    why = "max all (class-weighted"
    if opts.get("has_tank"):
        why += "; tank HP/STA; AC to softcap"
    else:
        why += "; AC softcap-aware"
    if opts.get("maximize_hp_regen"):
        why += "; HP regen"
    if not opts.get("uses_mana"):
        why += "; mana de-emphasized"
    why += ")"
    return bang + hb, bang, why


def score_ai_choice(item: dict, opts: dict[str, Any]) -> tuple[float, float, str]:
    """AI choice: role-aware blend of class primaries, tank/mana, haste, regen."""
    opts = dict(opts or default_score_opts())
    classes = opts.get("classes") or []
    # Seed primary tiers from class creation bonuses when user didn't set priority tiers
    if not (opts.get("primary_stats") or opts.get("secondary_stats") or opts.get("tertiary_stats")):
        # Gather top attrs across trio
        weights = opts.get("attr_weights") or {}
        ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
        opts["primary_stats"] = [k for k, v in ranked[:2] if v > 0]
        opts["secondary_stats"] = [k for k, v in ranked[2:4] if v > 0]
        # Prefer STA/HP as soft tertiary; AC handled via softcap-aware max_all.
        opts["tertiary_stats"] = ["STA", "HP"]
    s10 = enrich_stats_with_regen(item)
    bang = max_all_stat_sum(s10, opts)
    # Extra AI nudges from role tags
    role_bonus = 0.0
    tags = set(opts.get("roles") or [])
    if "healer" in tags or "caster" in tags:
        role_bonus += num(s10.get("WIS")) * 2.0 + num(s10.get("INT")) * 2.0 + num(s10.get("MANA")) * 0.8
        role_bonus += num(s10.get("MANA_REGEN")) * 25.0
    if "tank" in tags:
        # Softcap model already values under-cap AC; prefer STA/HP here.
        role_bonus += num(s10.get("HP")) * 1.5 + num(s10.get("STA")) * 2.5
        # Tiny AC nudge only when still under softcap (fill floor).
        softcap = float(opts.get("ac_softcap") or 0)
        current = float(opts.get("current_worn_ac") if opts.get("current_worn_ac") is not None else softcap * 0.45)
        if softcap and current < softcap:
            role_bonus += num(s10.get("AC")) * 0.35
    if "melee" in tags or "dps" in tags:
        role_bonus += num(s10.get("STR")) * 1.5 + num(s10.get("DEX")) * 1.2 + num(s10.get("AGI")) * 1.0
    if opts.get("maximize_hp_regen"):
        role_bonus += num(s10.get("HP_REGEN")) * 50.0
    else:
        role_bonus += num(s10.get("HP_REGEN")) * 12.0  # mild baseline value in AI mode

    hb = haste_bonus(item)
    weapon = item.get("is_weapon") and item.get("ratio_plus10") is not None
    if weapon:
        ratio10 = num(item.get("ratio_plus10"))
        score = ratio10 * 10000.0 + 0.25 * bang + 0.15 * role_bonus + hb
        return score, bang + role_bonus, "AI choice (best ratio)"
    trio = "/".join(classes) if classes else "trio"
    return bang + role_bonus + hb, bang + role_bonus, f"AI choice for {trio}"


def score_item(item: dict, mode: str, stat_key: str | None, opts: dict[str, Any] | None = None) -> tuple[float, float, str]:
    opts = opts or default_score_opts(priority_stat=stat_key)
    mode_n = normalize_mode(mode)
    if mode_n == "priority":
        if opts.get("primary_stats") or opts.get("secondary_stats") or opts.get("tertiary_stats"):
            return score_priority_tiers(item, opts)
        return score_priority(item, stat_key or "INT")
    if mode_n == "ai":
        return score_ai_choice(item, opts)
    return score_max_all(item, opts)


def normalize_mode(mode: str | None) -> str:
    m = (mode or "priority").strip().lower()
    if m in ("max", "max_all", "max-all", "max all stats"):
        return "max"
    if m in ("ai", "ai_choice", "ai-choice", "ai choice"):
        return "ai"
    return "priority"


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


def rank_for_slot(
    pool: list[dict],
    planner_slot: str,
    mode: str,
    stat_key: str | None,
    score_opts: dict[str, Any] | None = None,
) -> list[dict]:
    if planner_slot in ("EAR1", "EAR2"):
        match_slots = {"EAR1", "EAR2"}
    elif planner_slot in ("FINGER1", "FINGER2"):
        match_slots = {"FINGER1", "FINGER2"}
    else:
        match_slots = {planner_slot}

    opts = score_opts or default_score_opts(priority_stat=stat_key)
    candidates = []
    for item in pool:
        pslots = set(item.get("planner_slots") or [])
        if not (pslots & match_slots):
            continue
        score, pval, why = score_item(item, mode, stat_key, opts)
        if item.get("is_weapon") and item.get("ratio_plus10") is not None:
            why = "best ratio" if normalize_mode(mode) != "ai" else why
        s10 = enrich_stats_with_regen(item)
        candidates.append({
            "name": item["name"],
            "score": score,
            "pval": pval,
            "why": why,
            "zone": item.get("zone") or "",
            "drops_mobs": item.get("drops_mobs") or "",
            "quest_source": item.get("quest_source") or item.get("source") or "",
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
            "stats_plus10": s10,
            "haste": item_haste(item),
            "planner_slots": item.get("planner_slots") or [],
            "slot": item.get("slot") or "",
            "image_url": item.get("image_url") or "",
            "item": item,
        })
    candidates.sort(key=lambda r: (-r["score"], -r["bis_overlap"], r["name"]))
    return prefer_multi_class(candidates, 0.05)


def pick_loadout(
    pool: list[dict],
    mode: str,
    stat_key: str | None,
    score_opts: dict[str, Any] | None = None,
) -> dict[str, dict]:
    used_names: set[str] = set()
    loadout: dict[str, dict] = {}
    groups = [
        ["HEAD"], ["FACE"], ["EAR1", "EAR2"], ["NECK"], ["SHOULDERS"], ["ARMS"],
        ["WRIST"], ["HANDS"], ["CHEST"], ["BACK"], ["WAIST"], ["LEGS"], ["FEET"],
        ["FINGER1", "FINGER2"], ["PRIMARY"], ["SECONDARY"], ["RANGE"], ["AMMO"],
    ]
    opts = dict(score_opts or default_score_opts(priority_stat=stat_key))
    mode_n = normalize_mode(mode)
    softcap_aware = mode_n in ("max", "ai")
    worn_ac = 0.0

    best_haste_cand = None
    best_haste_slot_group = None
    for group in groups:
        ranked = rank_for_slot(pool, group[0], mode, stat_key, opts)
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
        # Re-score this slot with remaining softcap room so we fill AC to the
        # AA-raised soft cap first, then prefer other stats.
        slot_opts = dict(opts)
        if softcap_aware:
            slot_opts["current_worn_ac"] = worn_ac
        ranked = rank_for_slot(pool, group[0], mode, stat_key, slot_opts)
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
            why = cand["why"]
            if softcap_aware and opts.get("ac_softcap"):
                if worn_ac < float(opts["ac_softcap"]):
                    why = f"{why}; AC→softcap"
                else:
                    why = f"{why}; past AC softcap"
            if slot.endswith("2") and not cand.get("is_weapon"):
                if mode_n == "priority":
                    why = "2nd priority tier"
                elif mode_n == "max":
                    why = "2nd total score"
                elif mode_n == "ai":
                    why = "2nd AI choice"
            row = dict(cand)
            row["why"] = why
            row["slot"] = slot
            # Keep nested item for engine.recommend_bis (stats / ratio / haste).
            loadout[slot] = row
            if softcap_aware:
                s10 = cand.get("stats_plus10") or enrich_stats_with_regen(cand.get("item") or {})
                worn_ac += _item_ac(s10 if isinstance(s10, dict) else {})
        for slot in group:
            if slot not in loadout:
                loadout[slot] = {
                    "slot": slot, "name": "", "score": 0, "pval": 0, "why": "no item",
                    "zone": "", "drops_mobs": "", "classes_str": "", "ratio10": None,
                    "url": "", "stats_plus0": {}, "stats_plus10": {}, "haste": 0,
                    "is_weapon": False, "image_url": "", "item": None,
                }
    return loadout


def serialize_ranked(cands: list[dict], limit: int = 15) -> list[dict]:
    out = []
    for c in cands[:limit]:
        row = {k: v for k, v in c.items() if k != "item"}
        out.append(row)
    return out
