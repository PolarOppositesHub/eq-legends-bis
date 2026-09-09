"""BiS pool + scoring + simulate engine.

Reuses /workspace/eq-legends build_planner / build_xlsx / decode_local.
Item stats come only from decoded JSON — never invented.
"""
from __future__ import annotations

import json
import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import paths as _paths  # noqa: E402
from .paths import APP_ROOT, decoded_dir, ensure_vendor_on_path, legends_root  # noqa: E402

EQ_ROOT = ensure_vendor_on_path()
DECODED = decoded_dir()

import build_planner as bp  # noqa: E402
import build_xlsx as bx  # noqa: E402
from decode_local import SCALABLE_STATS, scale_item_stat  # noqa: E402

_paths.apply_legends_roots()

from .races import RACES, get_races_payload, race_bases, class_stat_rows  # noqa: E402
from . import weapon_dps as wdps  # noqa: E402
from . import scoring as sc  # noqa: E402
from . import class_roles as class_roles  # noqa: E402
from . import ac_softcap as ac_softcap  # noqa: E402
from . import character_pools as pools  # noqa: E402
from . import spell_buffs as spell_buffs  # noqa: E402

ALL_CLASSES = list(bx.ALL_CLASSES)
DEFAULT_TRIO = list(bx.DEFAULT_TRIO)
# Prefer scoring PLANNER_SLOTS (includes ANY1/ANY2) over vendor build_planner list.
PLANNER_SLOTS = list(sc.PLANNER_SLOTS)

MAX_CHARACTER_LEVEL = 50
DEFAULT_CHARACTER_LEVEL = 50
# Prefer enhanced priority list (includes regen labels) while keeping vendor keys.
PRIORITY_STATS = list(sc.PRIORITY_STATS)
PRIORITY_LABELS = list(sc.PRIORITY_LABELS)
LABEL_TO_KEY = dict(sc.LABEL_TO_KEY)
KEY_TO_LABEL = dict(sc.KEY_TO_LABEL)

TOTAL_STAT_KEYS = [
    "HP", "MANA", "END", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA",
    "AC", "SVF", "SVC", "SVM", "SVP", "SVD", "SVV", "ATK",
]


def _num(v, default=0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def scale_stats_to_level(stats0: dict, level: int) -> dict:
    """Scale +0 stats to upgrade level 0..10. Haste/DLY/FIRE_DMG/COLD_DMG do not scale."""
    level = max(0, min(10, int(level)))
    out: dict[str, Any] = {}
    for k, v in (stats0 or {}).items():
        if k == "DMG":
            try:
                base = float(v)
            except (TypeError, ValueError):
                continue
            # Site formula: floor(base * (1 + level/10)) for DMG (same as decode_local scaled_dmg pattern)
            if level == 0:
                out[k] = base
            else:
                out[k] = float(math.floor(base * (1 + level / 10)))
                # decode_local uses floor(o*(1+level/10)) for DMG specifically via scaled_dmg in build_xlsx
                # Prefer bx.scaled_dmg when available
                try:
                    out[k] = float(bx.scaled_dmg(base, level))
                except Exception:
                    out[k] = float(math.floor(base * (1 + level / 10)))
        elif k in ("DLY", "FIRE_DMG", "COLD_DMG", "Haste"):
            out[k] = float(v) if v is not None else 0.0
        elif k in SCALABLE_STATS or k in TOTAL_STAT_KEYS:
            out[k] = float(scale_item_stat(v, level))
        else:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = v
    return out


def ratio_at_level(item: dict, level: int) -> float | None:
    s0 = item.get("stats_plus0") or {}
    dmg0 = s0.get("DMG")
    dly = s0.get("DLY")
    if dmg0 is None or not dly:
        # fall back to stored ratios
        if level >= 10 and item.get("ratio_plus10") is not None:
            return float(item["ratio_plus10"])
        if level == 0 and item.get("ratio_plus0") is not None:
            return float(item["ratio_plus0"])
        return item.get("ratio_plus10") if item.get("ratio_plus10") is not None else item.get("ratio_plus0")
    dmg = bx.scaled_dmg(dmg0, level)
    return bx.ratio(dmg, dly)


@lru_cache(maxsize=1)
def _load_catalog_and_slug():
    catalog = json.loads((DECODED / "catalog.json").read_text(encoding="utf-8"))
    slug_map = bx.load_slug_map()
    summary = {}
    sp = DECODED / "summary.json"
    if sp.exists():
        summary = json.loads(sp.read_text(encoding="utf-8"))
    return catalog, slug_map, summary


def _public_item(item: dict, level: int = 10) -> dict:
    """Serialize item for API without nested circular refs."""
    s0 = dict(item.get("stats_plus0") or {})
    s_lvl = scale_stats_to_level(s0, level) if level != 10 else dict(item.get("stats_plus10") or scale_stats_to_level(s0, 10))
    if level == 0:
        s_lvl = dict(s0)
        # ensure numeric
        s_lvl = {k: (_num(v) if not isinstance(v, str) else v) for k, v in s_lvl.items()}
    s10 = dict(item.get("stats_plus10") or scale_stats_to_level(s0, 10))
    haste = bp.item_haste(item)
    return {
        "name": item.get("name"),
        "itemID": item.get("itemID"),
        "slots": item.get("slots") or [],
        "planner_slots": item.get("planner_slots") or [],
        "classes": item.get("classes") or [],
        "classes_str": item.get("classes_str") or "",
        "bis_for": item.get("bis_for") or [],
        "bis_for_str": item.get("bis_for_str") or "",
        "bis_overlap": item.get("bis_overlap", 0),
        "tri_classes": item.get("tri_classes", 0),
        "zone": item.get("zone") or "",
        "drops_mobs": item.get("drops_mobs") or "",
        "quest_source": item.get("quest_source") or "",
        "level": item.get("level"),
        "effect": item.get("effect") or "",
        "url": item.get("url") or "",
        "is_weapon": bool(item.get("is_weapon")),
        "stats_plus0": s0,
        "stats_plus10": s10,
        "stats_at_upgrade": s_lvl,
        "ratio_plus0": item.get("ratio_plus0"),
        "ratio_plus10": item.get("ratio_plus10"),
        "ratio_at_upgrade": ratio_at_level(item, level),
        "haste": haste if haste > 0 else 0,
    }


def _item_usable_by_any(item: dict, selected: set[str]) -> bool:
    """True if item is usable by ANY selected class (or ALL)."""
    cl = {str(c) for c in (item.get("classes") or [])}
    if "ALL" in cl:
        return True
    return bool(cl & selected)


def _has_weapon_ratio(item: dict) -> bool:
    """True when item has DMG/DLY (ratio weapon), not tomes/stat sticks."""
    if item.get("ratio_plus10") is not None or item.get("ratio_plus0") is not None:
        s0 = item.get("stats_plus0") or {}
        if _num(s0.get("DMG")) > 0 and _num(s0.get("DLY")) > 0:
            return True
        if item.get("ratio_plus10") is not None:
            return True
    s0 = item.get("stats_plus0") or {}
    return _num(s0.get("DMG")) > 0 and _num(s0.get("DLY")) > 0



# --- Dual wield vs 2H (delegates to weapon_dps; eqlwiki working Legends model) ---
DUAL_WIELD_CLASSES = wdps.DUAL_WIELD_CLASSES


def any_dual_wield_class(classes: list[str]) -> bool:
    return wdps.any_dual_wield_class(classes)


@lru_cache(maxsize=1)
def _weapon_catalog_by_name() -> dict:
    catalog, _, _ = _load_catalog_and_slug()
    out: dict = {}
    for w in catalog.get("weapons") or []:
        name = (w.get("weaponName") or "").strip()
        if name:
            out[name.lower()] = w
    return out


def enrich_weapon_handedness(item: dict) -> dict:
    """Attach catalog oneHanded / offhandUsable onto pool items when missing."""
    return wdps.enrich_item_handedness(item, _weapon_catalog_by_name())


def estimate_dw_skill(character_level: int) -> int:
    return wdps.estimate_dw_skill(character_level)


def dual_wield_chance(character_level: int, skill: int | None = None) -> float:
    return wdps.dual_wield_chance(character_level, skill)


def damage_bonus_raw(weapon_dmg, delay, character_level, *, two_handed: bool) -> float:
    return wdps.damage_bonus_raw(weapon_dmg, delay, character_level, two_handed=two_handed)


def main_hand_damage_score(weapon_dmg, delay, character_level, *, two_handed: bool) -> float:
    return wdps.main_hand_damage_score(weapon_dmg, delay, character_level, two_handed=two_handed)


def offhand_damage_score(weapon_dmg, delay, dw_chance) -> float:
    return wdps.offhand_damage_score(weapon_dmg, delay, dw_chance)


def evaluate_dw_vs_2h(weapon_pool: list[dict], upgrade: int, character_level: int) -> dict:
    return wdps.evaluate_dw_vs_2h(
        weapon_pool,
        upgrade,
        character_level,
        scaled_dmg_fn=bx.scaled_dmg,
        ratio_at_level_fn=ratio_at_level,
        catalog_by_name=_weapon_catalog_by_name(),
    )




def _slot_uses_ratio_rank(slot: str, item: dict | None, prefer_ranged_damage: bool) -> bool:
    """PRIMARY/SECONDARY with DMG always ratio-only; RANGE with DMG when prefer_ranged on.

    ANY1/ANY2 never use weapon ratio — damage does not matter in Any Slot.
    """
    if not item or not _has_weapon_ratio(item):
        return False
    if slot in sc.ANY_SLOTS:
        return False
    if slot in ("PRIMARY", "SECONDARY"):
        return True
    if slot == "RANGE" and prefer_ranged_damage:
        return True
    return False


def build_pool_for_classes(
    classes: list[str],
    mode: str = "any",
    *,
    require_all: bool | None = None,
) -> list[dict]:
    """Build item pool for selected classes.

    mode="any" (default): usable by ANY selected class (BiS armor/jewelry/weapons).
    mode="intersection" / require_all=True: usable by ALL selected classes (legacy shared-only filter).
    Empty class list → empty pool (UI starts with no classes; do not force DEFAULT_TRIO).
    Scoring still prefers multi-class overlap on near ties (prefer_multi_class / bis_overlap).
    """
    if require_all is None:
        require_all = str(mode).lower() in ("intersection", "all", "shared")
    cleaned = [c for c in classes if c in ALL_CLASSES]
    if not cleaned:
        return []
    bp.set_planner_target(cleaned)
    catalog, slug_map, _ = _load_catalog_and_slug()
    loaded = bx.load_rows(planner_classes=tuple(cleaned))
    merged, _per, _tri, _summary, cat2, planner_classes = loaded
    if cat2:
        catalog = cat2
    bp.set_planner_target(list(planner_classes))
    pool = bp.build_item_pool(merged, catalog, slug_map)
    selected = set(cleaned)
    out = []
    for item in pool:
        cl = {str(c) for c in (item.get("classes") or [])}
        if "ALL" in cl:
            out.append(item)
            continue
        if require_all:
            if selected.issubset(cl):
                out.append(item)
        elif cl & selected:
            out.append(item)
    return out


def _match_slots(planner_slot: str) -> set[str]:
    if planner_slot in ("EAR1", "EAR2"):
        return {"EAR1", "EAR2"}
    if planner_slot in ("FINGER1", "FINGER2"):
        return {"FINGER1", "FINGER2"}
    return {planner_slot}


def rank_slot_by_ratio(pool: list[dict], slot: str, upgrade: int) -> list[dict]:
    """Rank DMG/DLY weapons for a slot by ratio at upgrade only (no other stats)."""
    match = _match_slots(slot)
    ranked: list[dict] = []
    for item in pool:
        pslots = set(item.get("planner_slots") or [])
        if not (pslots & match):
            continue
        if not _has_weapon_ratio(item):
            continue
        ratio = ratio_at_level(item, upgrade)
        if ratio is None:
            continue
        ranked.append({
            "name": item["name"],
            "score": float(ratio) * 10000.0,
            "pval": float(ratio),
            "why": f"best ratio @+{upgrade}",
            "zone": item.get("zone") or "",
            "drops_mobs": item.get("drops_mobs") or "",
            "classes_str": item.get("classes_str") or "",
            "ratio10": item.get("ratio_plus10"),
            "ratio_at_upgrade": ratio,
            "url": item.get("url") or "",
            "bis_overlap": item.get("bis_overlap", 0),
            "tri_classes": item.get("tri_classes", 0),
            "is_weapon": True,
            "stats_plus10": item.get("stats_plus10") or {},
            "stats_plus0": item.get("stats_plus0") or {},
            "planner_slots": item.get("planner_slots") or [],
            "item": item,
        })
    ranked.sort(key=lambda r: (-_num(r["ratio_at_upgrade"]), -r.get("bis_overlap", 0), r["name"]))
    return ranked


def recommend_bis(
    classes: list[str],
    mode: str = "priority",
    priority_stat: str = "INT",
    alts: int = 5,
    upgrade: int = 10,
    prefer_ranged_damage: bool = True,
    character_level: int = 50,
    primary_stats: list[str] | None = None,
    secondary_stats: list[str] | None = None,
    tertiary_stats: list[str] | None = None,
    maximize_hp_regen: bool = False,
) -> dict:
    """Return haste-aware BiS loadout + per-slot ranked alts.

    Weapon slots (PRIMARY/SECONDARY, and RANGE when prefer_ranged_damage):
    eligibility = any selected class.
    If any selected class can dual wield: PRIMARY/SECONDARY compare best 1H+1H DW
    pair vs best 2H under eqlwiki Game_Mechanics working Legends expected-damage
    model (not raw ratio alone). Otherwise: ratio-only ranking at `upgrade`.
    """
    upgrade = max(0, min(10, int(upgrade)))
    character_level = max(1, min(MAX_CHARACTER_LEVEL, int(character_level or DEFAULT_CHARACTER_LEVEL)))
    mode_n = sc.normalize_mode(mode)
    # Accept label or key
    stat_key = priority_stat
    if stat_key in LABEL_TO_KEY:
        stat_key = LABEL_TO_KEY[stat_key]
    if mode_n == "priority" and stat_key not in KEY_TO_LABEL:
        stat_key = "INT"

    cleaned = [c for c in classes if c in ALL_CLASSES]
    score_opts = sc.default_score_opts(
        classes=cleaned,
        primary_stats=primary_stats,
        secondary_stats=secondary_stats,
        tertiary_stats=tertiary_stats,
        maximize_hp_regen=maximize_hp_regen,
        priority_stat=stat_key if mode_n == "priority" else None,
        character_level=character_level,
    )
    mode_label = {
        "max": "Max All Stats",
        "ai": "AI Choice",
        "priority": "Priority Stat",
    }.get(mode_n, "Priority Stat")

    if not cleaned:
        return {
            "classes": [],
            "mode": mode_label,
            "priority_stat": KEY_TO_LABEL.get(stat_key, stat_key) if mode_n == "priority" else None,
            "priority_stat_key": stat_key if mode_n == "priority" else None,
            "primary_stats": score_opts.get("primary_stats") or [],
            "secondary_stats": score_opts.get("secondary_stats") or [],
            "tertiary_stats": score_opts.get("tertiary_stats") or [],
            "maximize_hp_regen": bool(maximize_hp_regen),
            "upgrade": upgrade,
            "character_level": character_level,
            "prefer_ranged_damage": prefer_ranged_damage,
            "haste_rule": "Only ONE worn haste item counts (highest %). Loadout enforces this.",
            "haste_in_loadout": [],
            "slots": [],
            "pool_size": 0,
            "note": "Select at least one class.",
        }

    # Armor/jewelry + weapons: any-class union (item usable by at least one selected class).
    # Multi-class overlap is a soft scoring preference, not an eligibility gate.
    gear_pool = build_pool_for_classes(cleaned, mode="any")
    weapon_pool = gear_pool
    pool = gear_pool  # default ranking pool for non-weapon slots
    loadout = sc.pick_loadout(
        gear_pool,
        mode_n,
        stat_key if mode_n == "priority" else None,
        score_opts,
    )

    # Override weapon slots from any-class pool.
    used_names = {
        (loadout.get(s) or {}).get("name")
        for s in PLANNER_SLOTS
        if (loadout.get(s) or {}).get("name")
    }
    dw_enabled = any_dual_wield_class(cleaned)
    dw_eval = None
    if dw_enabled:
        dw_eval = evaluate_dw_vs_2h(weapon_pool, upgrade, character_level)
        # Clear prior PRIMARY/SECONDARY picks before applying DW/2H winner.
        for slot in ("PRIMARY", "SECONDARY"):
            cur = (loadout.get(slot) or {}).get("name")
            if cur:
                used_names.discard(cur)
        if dw_eval.get("mode") == "dual_wield":
            prim = dw_eval["primary"]
            sec = dw_eval["secondary"]
            used_names.add(prim["name"])
            used_names.add(sec["name"])
            loadout["PRIMARY"] = prim
            loadout["SECONDARY"] = sec
        elif dw_eval.get("mode") == "two_hand":
            prim = dw_eval["primary"]
            used_names.add(prim["name"])
            loadout["PRIMARY"] = prim
            # 2H occupies both hands — do not auto-fill a 1H into SECONDARY.
            loadout["SECONDARY"] = {
                "name": "",
                "score": 0,
                "pval": 0,
                "why": (
                    f"2H occupies both hands "
                    f"(beat DW pair score {dw_eval.get('pair_score')}; "
                    f"eqlwiki Game_Mechanics working Legends model)"
                ),
                "why_ui": "Two-handed weapon (occupies both hands)",
                "zone": "",
                "drops_mobs": "",
                "classes_str": "",
                "ratio10": None,
                "ratio_at_upgrade": None,
                "url": "",
                "bis_overlap": 0,
                "tri_classes": 0,
                "is_weapon": False,
                "stats_plus10": {},
                "stats_plus0": {},
                "planner_slots": ["SECONDARY"],
                "item": None,
            }
        # else mode none → fall through to ratio for PRIMARY/SECONDARY below

    for slot in ("PRIMARY", "SECONDARY", "RANGE"):
        if slot == "RANGE" and not prefer_ranged_damage:
            # Keep priority/max-stats pick for RANGE when toggle is off (any-class pool).
            continue
        if dw_enabled and slot in ("PRIMARY", "SECONDARY") and dw_eval and dw_eval.get("mode") in (
            "dual_wield", "two_hand",
        ):
            # Already set by DW vs 2H comparison.
            continue
        ratio_ranked = rank_slot_by_ratio(weapon_pool, slot, upgrade)
        if not ratio_ranked:
            continue
        cur = (loadout.get(slot) or {}).get("name")
        if cur:
            used_names.discard(cur)
        pick = None
        for cand in ratio_ranked:
            if cand["name"] not in used_names:
                pick = cand
                break
        if pick is None:
            pick = ratio_ranked[0]
        used_names.add(pick["name"])
        loadout[slot] = pick

    # After weapon overrides free/claim names, refill Any Slot from leftovers.
    # Damage/ratio never applies here — score other stats only.
    for slot in ("ANY1", "ANY2"):
        cur = (loadout.get(slot) or {}).get("name")
        if cur:
            used_names.discard(cur)
    any_opts = dict(score_opts)
    any_opts["ignore_weapon_ratio"] = True
    for slot in ("ANY1", "ANY2"):
        ranked = sc.rank_for_slot(
            gear_pool,
            slot,
            mode_n,
            stat_key if mode_n == "priority" else None,
            any_opts,
        )
        pick = None
        for cand in ranked:
            if cand["name"] not in used_names:
                pick = cand
                break
        if pick is None:
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
                "ratio_at_upgrade": None,
                "url": "",
                "bis_overlap": 0,
                "tri_classes": 0,
                "is_weapon": False,
                "stats_plus10": {},
                "stats_plus0": {},
                "planner_slots": [slot],
                "item": None,
            }
        else:
            used_names.add(pick["name"])
            row = dict(pick)
            row["slot"] = slot
            loadout[slot] = row

    slots_out = []
    haste_items = []
    for slot in PLANNER_SLOTS:
        cand = loadout.get(slot) or {}
        item = cand.get("item")
        use_ratio = (
            slot not in sc.ANY_SLOTS
            and (
                _slot_uses_ratio_rank(slot, item, prefer_ranged_damage)
                or (
                    slot in ("PRIMARY", "SECONDARY") and _has_weapon_ratio(item or {})
                )
                or (slot == "RANGE" and prefer_ranged_damage and _has_weapon_ratio(item or {}))
            )
        )
        ratio_u = ratio_at_level(item, upgrade) if item else None
        s0 = (item or {}).get("stats_plus0") or {}
        s10 = cand.get("stats_plus10") or (item or {}).get("stats_plus10") or {}
        s_up = scale_stats_to_level(s0, upgrade) if item else {}
        if upgrade == 10 and s10:
            s_up = dict(s10)
        row = {
            "slot": slot,
            "name": cand.get("name") or "",
            "why": cand.get("why") or "",
            "why_ui": cand.get("why_ui") or "",
            "score": round(_num(cand.get("score")), 4),
            "priority_value": cand.get("pval"),
            "zone": cand.get("zone") or "",
            "drops_mobs": cand.get("drops_mobs") or "",
            "quest_source": cand.get("quest_source") or (item or {}).get("quest_source") or (item or {}).get("source") or "",
            "classes_str": cand.get("classes_str") or "",
            "ratio_plus10": cand.get("ratio10") if cand.get("ratio10") is not None else (item or {}).get("ratio_plus10"),
            "ratio_at_upgrade": ratio_u if ratio_u is not None else cand.get("ratio_at_upgrade"),
            "url": cand.get("url") or "",
            "image_url": f"/api/item-image?name={cand.get('name')}" if cand.get("name") else "",
            "bis_overlap": cand.get("bis_overlap", 0),
            "is_weapon": bool(cand.get("is_weapon") or (item or {}).get("is_weapon")),
            "stats_plus0": s0,
            "stats_plus10": sc.enrich_stats_with_regen({"stats_plus10": s10, "tooltipLines": (item or {}).get("tooltipLines") or [], "special": (item or {}).get("special"), "effect": (item or {}).get("effect")}) if (s10 or item) else {},
            "stats_at_upgrade": s_up,
            "upgrade": upgrade,
            "haste": 0,
            "alts": [],
        }
        dw_slot = bool(
            dw_enabled and slot in ("PRIMARY", "SECONDARY")
            and dw_eval and dw_eval.get("mode") in ("dual_wield", "two_hand")
        )
        if dw_slot:
            # Keep expected-damage why/score from DW vs 2H evaluation.
            if cand.get("damage_score") is not None:
                row["score"] = round(_num(cand.get("damage_score")), 4)
            row["damage_score"] = row["score"]
            row["weapon_compare"] = dw_eval.get("mode")
        elif use_ratio and row["name"]:
            row["why"] = f"best ratio @+{upgrade}"
            row["why_ui"] = f"Best weapon ratio @+{upgrade}"
            if ratio_u is not None:
                row["score"] = round(float(ratio_u) * 10000.0, 4)
        h = bp.item_haste(item) if item else _num((row["stats_plus10"] or {}).get("Haste"))
        row["haste"] = h if h > 0 else 0
        if row["haste"] > 0 and row["name"]:
            haste_items.append({"slot": slot, "name": row["name"], "haste": row["haste"]})

        if slot in ("PRIMARY", "SECONDARY") or (slot == "RANGE" and prefer_ranged_damage):
            ranked = rank_slot_by_ratio(weapon_pool, slot, upgrade)
            if not ranked:
                ranked = sc.rank_for_slot(
                    weapon_pool, slot, mode_n, stat_key if mode_n == "priority" else None, score_opts
                )
        else:
            ranked = sc.rank_for_slot(
                gear_pool, slot, mode_n, stat_key if mode_n == "priority" else None, score_opts
            )
        alts_list = []
        # When DW compare ran, surface the losing 2H (or DW pair) as first alt on PRIMARY.
        if (
            dw_enabled and slot == "PRIMARY" and dw_eval
            and dw_eval.get("mode") == "dual_wield"
            and dw_eval.get("runner_up_2h")
        ):
            ru = dw_eval["runner_up_2h"]
            if ru.get("name") and ru["name"] != row.get("name"):
                alts_list.append({
                    "name": ru["name"],
                    "score": round(_num(ru["score"]), 4),
                    "why": ru.get("why"),
                    "why_ui": ru.get("why_ui") or "Runner-up two-hander",
                    "zone": ru.get("zone") or "",
                    "ratio_plus10": ru.get("ratio10"),
                    "ratio_at_upgrade": ru.get("ratio_at_upgrade"),
                    "haste": 0,
                    "bis_overlap": ru.get("bis_overlap", 0),
                    "stats_plus10": ru.get("stats_plus10") or {},
                    "stats_at_upgrade": scale_stats_to_level(
                        ((ru.get("item") or {}).get("stats_plus0") or {}), upgrade
                    ) if ru.get("item") else {},
                    "url": ru.get("url") or "",
                    "damage_score": round(_num(ru["score"]), 4),
                })
        if (
            dw_enabled and slot == "PRIMARY" and dw_eval
            and dw_eval.get("mode") == "two_hand"
            and dw_eval.get("runner_up_dw")
        ):
            ru = dw_eval["runner_up_dw"]
            alts_list.append({
                "name": f"{ru['main']} + {ru['off']}",
                "score": round(_num(ru["score"]), 4),
                "why": (
                    f"best DW pair expected-dmg {ru['score']:.4f} "
                    f"(lost to 2H; eqlwiki Game_Mechanics working Legends model)"
                ),
                "why_ui": "Runner-up dual-wield pair",
                "zone": "",
                "ratio_plus10": None,
                "ratio_at_upgrade": None,
                "haste": 0,
                "bis_overlap": 0,
                "stats_plus10": {},
                "stats_at_upgrade": {},
                "url": "",
                "damage_score": round(_num(ru["score"]), 4),
            })
        for r in ranked[: max(alts, 1) + 8]:
            if r["name"] == row["name"]:
                continue
            ih = bp.item_haste(r.get("item") or {})
            r_item = r.get("item") or {}
            r_ratio = r.get("ratio_at_upgrade")
            if r_ratio is None and r_item:
                r_ratio = ratio_at_level(r_item, upgrade)
            alts_list.append({
                "name": r["name"],
                "score": round(_num(r["score"]), 4),
                "why": r.get("why"),
                "why_ui": r.get("why_ui") or "",
                "zone": r.get("zone") or "",
                "drops_mobs": r.get("drops_mobs") or r_item.get("drops_mobs") or "",
                "quest_source": r.get("quest_source") or r_item.get("quest_source") or r_item.get("source") or "",
                "ratio_plus10": r.get("ratio10"),
                "ratio_at_upgrade": r_ratio,
                "haste": ih if ih > 0 else 0,
                "bis_overlap": r.get("bis_overlap", 0),
                "stats_plus0": r_item.get("stats_plus0") or {},
                "stats_plus10": sc.enrich_stats_with_regen(r_item) if r_item else (r.get("stats_plus10") or {}),
                "stats_at_upgrade": scale_stats_to_level((r_item.get("stats_plus0") or {}), upgrade) if r_item else {},
                "url": r.get("url") or "",
                "image_url": f"/api/item-image?name={r['name']}" if r.get("name") else "",
            })
            if len(alts_list) >= alts:
                break
        row["alts"] = alts_list
        slots_out.append(row)

    # Enforce single haste after weapon overrides (weapon haste is rare but possible)
    if len(haste_items) > 1:
        best = max(haste_items, key=lambda h: (h["haste"], h["name"]))
        haste_items = [best]

    if dw_enabled:
        weapon_rule = (
            "PRIMARY/SECONDARY: any selected class can dual wield → compare best 1H+1H dual-wield "
            "pair vs best 2H using eqlwiki Game_Mechanics working Legends expected-damage model "
            f"(L={character_level}; DWChance=Skill/400, skill≈{estimate_dw_skill(character_level)}). "
            "RANGE when Prefer ranged: ratio-only. "
            "Non-weapon gear: usable by any selected class (union); multi-class preferred on ties."
        )
    else:
        weapon_rule = (
            "PRIMARY/SECONDARY (and RANGE when Prefer ranged damage): usable by any selected class; "
            "ranked by DMG/DLY ratio only at selected upgrade (no DW class selected). "
            "Non-weapon gear: usable by any selected class (union); multi-class preferred on ties."
        )

    return {
        "classes": cleaned,
        "mode": mode_label,
        "priority_stat": KEY_TO_LABEL.get(stat_key, stat_key) if mode_n == "priority" else None,
        "priority_stat_key": stat_key if mode_n == "priority" else None,
        "primary_stats": score_opts.get("primary_stats") or [],
        "secondary_stats": score_opts.get("secondary_stats") or [],
        "tertiary_stats": score_opts.get("tertiary_stats") or [],
        "maximize_hp_regen": bool(maximize_hp_regen),
        "class_roles": {
            "has_tank": score_opts.get("has_tank"),
            "uses_mana": score_opts.get("uses_mana"),
            "roles": score_opts.get("roles") or [],
            "attr_weights": score_opts.get("attr_weights") or {},
        },
        "upgrade": upgrade,
        "character_level": character_level,
        "ac_softcap": {
            **ac_softcap.softcap_payload(
                character_level,
                cleaned,
                combat_stability_rank=int(score_opts.get("combat_stability_rank") or 3),
                physical_enhancement=bool(score_opts.get("physical_enhancement", True)),
            ),
            "loadout_worn_ac": round(sum(
                float((s.get("stats_at_upgrade") or s.get("stats_plus10") or {}).get("AC") or 0)
                for s in slots_out
            ), 2),
        },
        "prefer_ranged_damage": prefer_ranged_damage,
        "dual_wield_enabled": dw_enabled,
        "dual_wield_eval": (
            {
                "mode": dw_eval.get("mode"),
                "dw_chance": dw_eval.get("dw_chance"),
                "dw_skill": dw_eval.get("dw_skill"),
                "pair_score": dw_eval.get("pair_score"),
                "two_hand_score": dw_eval.get("two_hand_score"),
                "two_hand_name": dw_eval.get("two_hand_name"),
                "model_note": dw_eval.get("model_note"),
            }
            if dw_eval
            else None
        ),
        "haste_rule": "Only ONE worn haste item counts (highest %). Loadout enforces this.",
        "haste_in_loadout": haste_items,
        "slots": slots_out,
        "pool_size": len(gear_pool),
        "weapon_pool_size": len(weapon_pool),
        "weapon_rule": weapon_rule,
    }


def items_for_slot(
    classes: list[str],
    slot: str | None = None,
    q: str | None = None,
    upgrade: int = 10,
    *,
    prefer_ranged_damage: bool = True,
) -> list[dict]:
    """Slot item list for UI dropdowns / API.

    All slots: any-class union (usable by at least one selected class).
    prefer_ranged_damage is retained for API compatibility; it no longer changes eligibility.
    """
    slot_u = (slot or "").upper()
    pool = build_pool_for_classes(classes, mode="any")
    upgrade = max(0, min(10, int(upgrade)))
    qn = (q or "").strip().lower()
    out = []
    for item in pool:
        pslots = item.get("planner_slots") or []
        if slot:
            if slot_u in sc.ANY_SLOTS:
                # Any Slot can hold general worn gear (no catalog ANY token).
                if not pslots:
                    continue
            else:
                match = {slot_u}
                if slot_u in ("EAR1", "EAR2"):
                    match = {"EAR1", "EAR2"}
                elif slot_u in ("FINGER1", "FINGER2"):
                    match = {"FINGER1", "FINGER2"}
                if not (set(pslots) & match):
                    continue
        if qn and qn not in (item.get("name") or "").lower():
            continue
        out.append(_public_item(item, upgrade))
    out.sort(
        key=lambda r: (
            -_num(r.get("ratio_at_upgrade") if r.get("ratio_at_upgrade") is not None else r.get("ratio_plus10")),
            -_num((r.get("stats_at_upgrade") or r.get("stats_plus10") or {}).get("HP")),
            r["name"] or "",
        )
    )
    return out


def get_item_by_name(pool: list[dict], name: str) -> dict | None:
    if not name:
        return None
    key = name.strip().lower()
    for item in pool:
        if (item.get("name") or "").strip().lower() == key:
            return item
    return None


def simulate(
    classes: list[str],
    race: str | None,
    equipment: dict[str, str],
    upgrade: int = 10,
    character_level: int | None = None,
    cast_buffs: str = "off",
    active_buff_ids: list[str] | None = None,
    assume_max_aas: bool = True,
    slot_upgrades: dict[str, Any] | None = None,
) -> dict:
    """Live totals for equipped gear with race/class pools + optional Cast Buffs.

    Pool math mirrors eqlegendstools char-sheet (race + class allotments +
    STA/INT/WIS formulas). Item stats still come only from decoded JSON.
    Cast Buffs use their verified spellBuffs catalog (Quick Buff = max line
    per stacking group for the selected trio).

    ``slot_upgrades`` optionally overrides ``upgrade`` per planner slot (0..10).
    """
    upgrade = max(0, min(10, int(upgrade)))
    slot_upg: dict[str, int] = {}
    for k, v in (slot_upgrades or {}).items():
        try:
            slot_upg[str(k).upper()] = max(0, min(10, int(v)))
        except (TypeError, ValueError):
            continue
    cleaned = [c for c in classes if c in ALL_CLASSES]
    pool = build_pool_for_classes(cleaned, mode="any")
    by_name = {(it.get("name") or "").strip().lower(): it for it in pool}

    equipped = []
    haste_candidates = []
    warnings = []
    gear_stats: dict[str, float] = {}

    for slot in PLANNER_SLOTS:
        raw_name = (equipment or {}).get(slot) or (equipment or {}).get(slot.lower()) or ""
        slot_level = slot_upg.get(slot, upgrade)
        if not raw_name or str(raw_name).strip().lower() in ("", "none", "-"):
            equipped.append({
                "slot": slot,
                "name": "",
                "included_stats": {},
                "haste": 0,
                "haste_applied": False,
                "upgrade": slot_level,
            })
            continue
        item = by_name.get(str(raw_name).strip().lower())
        if not item:
            warnings.append(f"{slot}: item not in trio pool: {raw_name}")
            equipped.append({
                "slot": slot,
                "name": str(raw_name),
                "missing": True,
                "included_stats": {},
                "haste": 0,
                "haste_applied": False,
                "upgrade": slot_level,
            })
            continue
        stats = scale_stats_to_level(item.get("stats_plus0") or {}, slot_level)
        if slot_level == 10 and item.get("stats_plus10"):
            stats = dict(item["stats_plus10"])
        h = bp.item_haste(item)
        entry = {
            "slot": slot,
            "name": item["name"],
            "is_weapon": bool(item.get("is_weapon")),
            "included_stats": stats,
            "haste": h if h > 0 else 0,
            "haste_applied": False,
            "ratio": ratio_at_level(item, slot_level),
            "url": item.get("url") or "",
            "zone": item.get("zone") or "",
            "upgrade": slot_level,
        }
        equipped.append(entry)
        if h > 0:
            haste_candidates.append(entry)
        for k, v in stats.items():
            if k == "Haste":
                continue
            gear_stats[k] = gear_stats.get(k, 0.0) + _num(v)

    applied_haste = 0.0
    applied_slot = None
    if haste_candidates:
        best = max(haste_candidates, key=lambda e: (e["haste"], e["name"]))
        best["haste_applied"] = True
        applied_haste = best["haste"]
        applied_slot = best["slot"]
        if len(haste_candidates) > 1:
            others = [f"{e['slot']}:{e['name']} (+{int(e['haste'])}%)" for e in haste_candidates if e is not best]
            warnings.append(
                f"Multiple haste items equipped; only highest counts "
                f"({best['name']} +{int(applied_haste)}%). Ignored: {', '.join(others)}"
            )

    buffs_info = spell_buffs.cast_buffs_payload(
        cleaned,
        mode=cast_buffs or "off",
        active_ids=list(active_buff_ids or []),
        character_level=character_level if character_level is not None else 50,
    )
    buff_effects = dict(buffs_info.get("effects") or {})
    buff_haste = float(buff_effects.pop("HASTE", 0) or 0)

    bases = race_bases(race)
    race_attrs = {k: bases.get(k, 0) for k in pools.ATTR_KEYS}
    race_resists = {k: bases.get(k, 0) for k in pools.RESIST_KEYS}
    class_rows = class_stat_rows(cleaned)

    pooled = pools.compute_pools(
        classes=cleaned,
        race_attrs=race_attrs,
        race_resists=race_resists,
        class_stat_rows=class_rows,
        gear_stats=gear_stats,
        buff_stats=buff_effects,
        assume_max_aas=bool(assume_max_aas),
    )
    totals = dict(pooled["totals"])

    worn_haste = int(applied_haste)
    total_haste = max(worn_haste, int(buff_haste))
    totals["Haste"] = total_haste

    weapon_ratios = []
    for e in equipped:
        if e.get("is_weapon") and e.get("ratio") is not None and e.get("name") and not e.get("missing"):
            weapon_ratios.append({
                "slot": e["slot"],
                "name": e["name"],
                "ratio": e["ratio"],
                "dmg": _num((e.get("included_stats") or {}).get("DMG")),
                "dly": _num((e.get("included_stats") or {}).get("DLY")),
            })

    def _nice(v):
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return 0
        return int(fv) if fv.is_integer() else round(fv, 2)

    totals_out = {k: _nice(v) for k, v in totals.items()}

    haste_items = [{"slot": e["slot"], "name": e["name"], "haste": e["haste"]} for e in haste_candidates]
    return {
        "classes": cleaned,
        "race": race,
        "character_level": character_level,
        "race_bases": bases,
        "class_stats": class_rows,
        "race_note": pools.SOURCE_NOTE,
        "upgrade": upgrade,
        "slot_upgrades": {
            e["slot"]: int(e.get("upgrade", upgrade))
            for e in equipped
            if e.get("name")
        },
        "hp_label": "pool HP (race+class+STA+gear+buffs)",
        "haste": {
            "applied": total_haste,
            "applied_pct": total_haste,
            "applied_slot": applied_slot,
            "worn_pct": worn_haste,
            "buff_pct": int(buff_haste),
            "rule": "Worn haste: only ONE item (highest %). Spell haste from Cast Buffs takes max with worn.",
            "candidates": haste_items,
            "items": haste_items,
        },
        "haste_applied": total_haste,
        "haste_pieces": haste_items,
        "haste_warning": warnings[0] if warnings else None,
        "totals": totals_out,
        "pool_breakdown": pooled.get("breakdown") or {},
        "cast_buffs": buffs_info,
        "assume_max_aas": bool(assume_max_aas),
        "weapons": weapon_ratios,
        "equipment": [
            {
                "slot": e["slot"],
                "name": e.get("name") or "",
                "upgrade": int(e.get("upgrade", upgrade)),
                "haste": e.get("haste") or 0,
                "haste_applied": e.get("haste_applied", False),
                "ratio": e.get("ratio"),
                "stats": e.get("included_stats") or {},
                "missing": e.get("missing", False),
                "url": e.get("url") or "",
            }
            for e in equipped
        ],
        "warnings": warnings,
        "note": (
            f"{pools.SOURCE_NOTE} "
            + (
                f"Cast Buffs ({buffs_info.get('mode')}): "
                + (", ".join(b['name'] for b in buffs_info.get('active') or []) or "none")
                + ". "
                if buffs_info.get("mode") != "off"
                else "Cast Buffs off. "
            )
            + ("Max AAs assumed for sheet AAs (Natural Durability, Eminence, etc.). " if assume_max_aas else "")
            + "Pool math matches EQLT L50 sheet formulas; gear still from decoded JSON only."
        ),
    }


def meta_payload() -> dict:
    catalog, _slug, summary = _load_catalog_and_slug()
    return {
        "classes": ALL_CLASSES,
        "default_trio": DEFAULT_TRIO,  # reference for export scripts only — UI must start empty
        "ui_default_classes": [],
        "slots": PLANNER_SLOTS,
        "priority_stats": [{"key": k, "label": lab} for k, lab in PRIORITY_STATS],
        "modes": [
            {"id": "priority", "label": "Priority Stat"},
            {"id": "max", "label": "Max All Stats"},
            {"id": "ai", "label": "AI Choice"},
        ],
        "haste_rule": summary.get("haste_note") or (
            "Only ONE worn haste item counts (highest %). Haste does not scale with upgrade."
        ),
        "weapon_rule": (
            "PRIMARY/SECONDARY: DW pair vs 2H expected-dmg when any DW class selected; "
            "else ratio-only. RANGE when Prefer ranged: ratio-only. "
            "ANY1/ANY2: stats only (weapon DMG/ratio ignored)."
        ),
        "races": get_races_payload(),
        "class_roles": class_roles.class_roles_payload(),
        "data_root": str(DECODED),
        "summary_counts": summary.get("counts") or {},
        "catalog_weapons": len(catalog.get("weapons") or []),
        "upgrade_levels": list(range(0, 11)),
        "character_levels": list(range(1, MAX_CHARACTER_LEVEL + 1)),
        "prefer_ranged_damage_default": True,
        "version": "1.0.11",
        "scoring": {
            "priority_armor": (
                "primary×100 + secondary×25 + tertiary×6 + 0.15×other + Haste×2 "
                "(up to 3 stats per tier; defaults from classStats)"
            ),
            "priority_weapon": (
                "If any DW class selected: expected-dmg DW pair vs 2H "
                "(eqlwiki Game_Mechanics working Legends model); else ratio-only. "
                "RANGE if prefer ranged: ratio-only."
            ),
            "max_armor": (
                "Class-weighted attrs from races.json classStats; HP bump for tanks; "
                "AC softcap-aware (eqlwiki L≤50: level×6+25, +CS/+PE AAs — hit softcap then "
                "prefer other stats; overcap lightly valued via class post-cap return); "
                "mana only for mana classes; optional HP regen toggle"
            ),
            "ai_armor": (
                "Role-aware blend of trio primaries + STA/HP tank nudges; same AC softcap "
                "model as Max All; cross-check vs community EQ Legends tools when validating"
            ),
            "ac_softcap": (
                "Working model from eqlwiki Statistics/AC + Alternate Advancement "
                "(Combat Stability + Physical Enhancement). Combat Agility is avoidance only."
            ),
            "max_weapon": "Same as priority_weapon for damaging PRIMARY/SECONDARY/RANGE",
            "gear_eligibility": (
                "armor/jewelry/weapons: any selected class (union); "
                "multi-class overlap preferred on near ties"
            ),
            "dual_wield_classes": sorted(DUAL_WIELD_CLASSES),
            "dw_chance": "Skill/400; skill≈min(252, level*252/50) when no skill table (L50 cap)",
        },
    }
