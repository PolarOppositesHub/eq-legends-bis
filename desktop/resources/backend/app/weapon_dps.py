"""Working Legends DW vs 2H weapon BiS scoring.

eqlwiki Skill_Dual_Wield / Game_Mechanics — WORKING MODEL, not exact server DPS.
Used by engine.recommend_bis when any selected class can dual wield.
"""
from __future__ import annotations

from typing import Any, Callable

# Typical classic EQ / Legends DW classes (eqlwiki Skill_Dual_Wield).
DUAL_WIELD_CLASSES: frozenset[str] = frozenset({
    "Monk", "Rogue", "Ranger", "Bard", "Beastlord", "Warrior",
})

HAND_MOD_1H = 0.8
HAND_MOD_2H = 1.1
MODEL_LABEL = "eqlwiki Game_Mechanics working Legends model (not exact)"


def any_dual_wield_class(classes: list[str]) -> bool:
    return any(c in DUAL_WIELD_CLASSES for c in classes)


MAX_CHARACTER_LEVEL = 50


def estimate_dw_skill(character_level: int) -> int:
    """No verified per-class skill table in decoded data.

    High-skill default: skill≈min(252, level*252/50) so L50 ≈ 252 (EQ Legends cap).
    """
    lv = max(1, min(MAX_CHARACTER_LEVEL, int(character_level)))
    return min(252, int(lv * 252 / MAX_CHARACTER_LEVEL))


def dual_wield_chance(character_level: int, skill: int | None = None) -> float:
    """eqlwiki Skill_Dual_Wield working model: DWChance = Skill ÷ 400.

    Level only affects skill cap (estimate_dw_skill). Optional Ambidexterity ×1.32
    is NOT applied by default (toggle later). Label as working model in BiS why text.
    """
    lv = max(1, min(MAX_CHARACTER_LEVEL, int(character_level)))
    sk = estimate_dw_skill(lv) if skill is None else int(skill)
    return float(sk) / 400.0


def damage_bonus_raw(
    weapon_dmg: float,
    delay: float,
    character_level: int,
    *,
    two_handed: bool,
) -> float:
    """DB = HandMod * max(Level, WeaponDMG) * (min(Delay,50)/40) * (Level/100)."""
    hand_mod = HAND_MOD_2H if two_handed else HAND_MOD_1H
    lv = float(character_level)
    dmg = float(weapon_dmg)
    dly = float(delay)
    return hand_mod * max(lv, dmg) * (min(dly, 50.0) / 40.0) * (lv / 100.0)


def main_hand_damage_score(
    weapon_dmg: float,
    delay: float,
    character_level: int,
    *,
    two_handed: bool,
) -> float:
    """MainScore = ((2*MainDMG)+MainDB)/MainDelay"""
    dly = float(delay)
    if dly <= 0:
        return 0.0
    db = damage_bonus_raw(weapon_dmg, dly, character_level, two_handed=two_handed)
    return ((2.0 * float(weapon_dmg)) + db) / dly


def offhand_damage_score(weapon_dmg: float, delay: float, dw_chance: float) -> float:
    """OffScore = DWChance * ((2*OffDMG)/OffDelay) — no DB on offhand."""
    dly = float(delay)
    if dly <= 0:
        return 0.0
    return float(dw_chance) * ((2.0 * float(weapon_dmg)) / dly)


def _slots_upper(item: dict) -> set[str]:
    raw = item.get("planner_slots") or item.get("slots") or []
    return {str(s).strip().upper() for s in raw if s}


def is_one_handed(item: dict) -> bool:
    return (item.get("oneHanded") or "").strip() == "Yes"


def is_two_handed(item: dict) -> bool:
    return (item.get("oneHanded") or "").strip() == "No"


def can_main_hand(item: dict) -> bool:
    return "PRIMARY" in _slots_upper(item)


def can_offhand(item: dict) -> bool:
    if not is_one_handed(item):
        return False
    if "SECONDARY" in _slots_upper(item):
        return True
    return str(item.get("offhandUsable") or "").strip().lower() in ("yes", "true", "1")


def enrich_item_handedness(item: dict, catalog_by_name: dict[str, dict]) -> dict:
    """Attach catalog oneHanded / offhandUsable / hand onto pool items when missing."""
    if item.get("oneHanded") and item.get("offhandUsable") not in (None, ""):
        oh = (item.get("oneHanded") or "").strip()
        if oh == "Yes":
            item["hand"] = item.get("hand") or "1H"
        elif oh == "No":
            item["hand"] = item.get("hand") or "2H"
        elif oh == "Ranged":
            item["hand"] = item.get("hand") or "Ranged"
        return item
    w = catalog_by_name.get((item.get("name") or "").strip().lower())
    if not w:
        return item
    if not item.get("oneHanded"):
        item["oneHanded"] = (w.get("oneHanded") or "").strip()
    if item.get("offhandUsable") in (None, ""):
        item["offhandUsable"] = (w.get("offhandUsable") or "").strip()
    oh = (item.get("oneHanded") or "").strip()
    if oh == "Yes":
        item["hand"] = "1H"
    elif oh == "No":
        item["hand"] = "2H"
    elif oh == "Ranged":
        item["hand"] = "Ranged"
    return item


def evaluate_dw_vs_2h(
    weapon_pool: list[dict],
    upgrade: int,
    character_level: int,
    *,
    scaled_dmg_fn: Callable,
    ratio_at_level_fn: Callable,
    catalog_by_name: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Compare best dual-wield 1H+1H pair vs best 2H under working Legends model."""
    level = max(1, min(MAX_CHARACTER_LEVEL, int(character_level or MAX_CHARACTER_LEVEL)))
    skill = estimate_dw_skill(level)
    dwc = dual_wield_chance(level, skill)
    cat = catalog_by_name or {}

    def dmg_dly(item: dict) -> tuple[float, float] | None:
        s0 = item.get("stats_plus0") or {}
        dmg0 = s0.get("DMG")
        dly = s0.get("DLY")
        if dmg0 is None or not dly:
            return None
        return float(scaled_dmg_fn(dmg0, upgrade)), float(dly)

    ones: list[dict] = []
    twos: list[dict] = []
    for raw in weapon_pool:
        item = enrich_item_handedness(dict(raw), cat)
        s0 = item.get("stats_plus0") or {}
        has_ratio = (
            item.get("ratio_plus10") is not None
            or item.get("ratio_plus0") is not None
            or (float(s0.get("DMG") or 0) > 0 and float(s0.get("DLY") or 0) > 0)
        )
        if not has_ratio:
            continue
        stats = dmg_dly(item)
        if not stats:
            continue
        item["_up_dmg"], item["_up_dly"] = stats
        if is_one_handed(item):
            ones.append(item)
        elif is_two_handed(item):
            twos.append(item)

    best_2h = None
    best_2h_score = -1.0
    for item in twos:
        if not can_main_hand(item):
            continue
        sc = main_hand_damage_score(item["_up_dmg"], item["_up_dly"], level, two_handed=True)
        if sc > best_2h_score:
            best_2h_score = sc
            best_2h = item

    best_pair = None
    best_pair_score = -1.0
    for i, a in enumerate(ones):
        for b in ones[i + 1 :]:
            arrangements = []
            if can_main_hand(a) and can_offhand(b):
                arrangements.append((a, b))
            if can_main_hand(b) and can_offhand(a):
                arrangements.append((b, a))
            for main, off in arrangements:
                m_sc = main_hand_damage_score(main["_up_dmg"], main["_up_dly"], level, two_handed=False)
                o_sc = offhand_damage_score(off["_up_dmg"], off["_up_dly"], dwc)
                total = m_sc + o_sc
                if total > best_pair_score:
                    best_pair_score = total
                    best_pair = (main, off, total, m_sc, o_sc)

    model_note = (
        f"{MODEL_LABEL}: "
        "DB=HandMod*max(L,DMG)*(min(DLY,50)/40)*(L/100); "
        f"1H HandMod={HAND_MOD_1H}, 2H={HAND_MOD_2H}; "
        "Main=((2*DMG)+DB)/DLY; Off=DWChance*((2*DMG)/DLY); "
        f"DWChance=skill/400 with skill≈{skill} @L{level} "
        "(assumption: no skill table in decoded data; monk-style high-skill default)"
    )

    def cand(item: dict, *, score: float, why: str, pval: float | None = None) -> dict:
        ratio = ratio_at_level_fn(item, upgrade)
        return {
            "name": item["name"],
            "score": float(score),
            "pval": float(pval if pval is not None else score),
            "why": why,
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
            "oneHanded": item.get("oneHanded") or "",
            "offhandUsable": item.get("offhandUsable") or "",
            "hand": item.get("hand") or "",
            "damage_score": float(score),
            "item": item,
        }

    if best_pair is None and best_2h is None:
        return {
            "mode": "none",
            "character_level": level,
            "dw_chance": dwc,
            "dw_skill": skill,
            "model_note": model_note,
        }

    use_dw = best_pair is not None and (best_2h is None or best_pair_score >= best_2h_score)
    if use_dw:
        main, off, total, m_sc, o_sc = best_pair
        two_name = best_2h["name"] if best_2h else "(none)"
        two_sc = best_2h_score if best_2h is not None else 0.0
        why_main = (
            f"DW main score {total:.4f} (main {m_sc:.4f} + off {o_sc:.4f}) "
            f">= 2H {two_name} {two_sc:.4f}; {model_note}"
        )
        why_off = (
            f"DW offhand with {main['name']} (pair score {total:.4f}, "
            f"DWChance {dwc:.2%}); {model_note}"
        )
        return {
            "mode": "dual_wield",
            "character_level": level,
            "dw_chance": dwc,
            "dw_skill": skill,
            "model_note": model_note,
            "pair_score": total,
            "two_hand_score": two_sc if best_2h is not None else None,
            "two_hand_name": two_name if best_2h else None,
            "primary": cand(main, score=total, why=why_main, pval=m_sc),
            "secondary": cand(off, score=o_sc, why=why_off, pval=o_sc),
            "runner_up_2h": (
                cand(
                    best_2h,
                    score=best_2h_score,
                    why=f"best 2H expected-dmg {best_2h_score:.4f} (lost to DW pair); {model_note}",
                    pval=best_2h_score,
                )
                if best_2h is not None
                else None
            ),
        }

    assert best_2h is not None
    pair_sc = best_pair_score if best_pair is not None else 0.0
    pair_desc = (
        f"{best_pair[0]['name']} + {best_pair[1]['name']} ({pair_sc:.4f})"
        if best_pair is not None
        else "(no 1H pair)"
    )
    why = f"2H expected-dmg score {best_2h_score:.4f} >= DW pair {pair_desc}; {model_note}"
    return {
        "mode": "two_hand",
        "character_level": level,
        "dw_chance": dwc,
        "dw_skill": skill,
        "model_note": model_note,
        "pair_score": pair_sc if best_pair is not None else None,
        "two_hand_score": best_2h_score,
        "two_hand_name": best_2h["name"],
        "primary": cand(best_2h, score=best_2h_score, why=why, pval=best_2h_score),
        "secondary": None,
        "runner_up_dw": (
            {
                "main": best_pair[0]["name"],
                "off": best_pair[1]["name"],
                "score": pair_sc,
            }
            if best_pair is not None
            else None
        ),
    }
