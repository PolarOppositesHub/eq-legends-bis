"""EQ Legends AC soft-cap helpers for BiS scoring.

Sources (never invent item stats; caps are research-backed, not item DB):
- eqlwiki Statistics/AC: for level ≤ 50, soft-cap (raw/worn AC) ≈ level * 6 + 25
  (wiki notes EQL may differ — treat as working model, document in meta).
- eqlwiki Alternate Advancement:
  - Combat Stability ranks 1/2/3 → +2% / +5% / +10% soft cap
  - Physical Enhancement rank 1 → +2% soft cap
  - Combat Agility is avoidance only — does NOT raise soft cap

BiS default assumes max soft-cap AAs (CS 3/3 + PE) so loadouts aim at the
AA-raised soft cap at minimum, then prefer other stats over more AC.
"""
from __future__ import annotations

from typing import Any

# Combat Stability rank → soft-cap % increase (eqlwiki General AAs)
COMBAT_STABILITY_PCT = {0: 0, 1: 2, 2: 5, 3: 10}

# Physical Enhancement (General AA): +2% soft cap when trained
PHYSICAL_ENHANCEMENT_PCT = 2

# Classic/EMU-style over-softcap effectiveness by class (fraction of AC above cap).
# Used only to lightly value overcap AC — never as hard item invent.
POST_CAP_RETURN: dict[str, float] = {
    "Warrior": 0.45,
    "Paladin": 0.33,
    "Shadow Knight": 0.33,
    "Monk": 0.33,
    "Cleric": 0.23,
    "Bard": 0.23,
    "Berserker": 0.23,
    "Rogue": 0.23,
    "Shaman": 0.23,
    "Ranger": 0.17,
    "Beastlord": 0.17,
    "Druid": 0.06,
    "Wizard": 0.06,
    "Magician": 0.06,
    "Necromancer": 0.06,
    "Enchanter": 0.06,
}

# Full-value weight for AC that still fills toward the soft cap (Max All / AI).
# High enough that filling the softcap beats stacking attrs while under-cap.
UNDER_SOFTCAP_AC_WEIGHT = 4.5
# Base weight applied to overcap AC before class post-cap return.
OVER_SOFTCAP_AC_WEIGHT = 0.45


def base_softcap(level: int) -> float:
    """eqlwiki L≤50 worn-AC soft cap: level * 6 + 25."""
    lv = max(1, int(level or 50))
    # Wiki formula is documented for level 50 or below; clamp to that model.
    lv = min(lv, 50)
    return float(lv * 6 + 25)


def aa_softcap_pct(
    *,
    combat_stability_rank: int = 3,
    physical_enhancement: bool = True,
) -> float:
    """Total % soft-cap increase from soft-cap AAs (not Combat Agility)."""
    rank = max(0, min(3, int(combat_stability_rank)))
    pct = float(COMBAT_STABILITY_PCT.get(rank, 0))
    if physical_enhancement:
        pct += float(PHYSICAL_ENHANCEMENT_PCT)
    return pct


def softcap_target(
    level: int = 50,
    *,
    combat_stability_rank: int = 3,
    physical_enhancement: bool = True,
) -> float:
    """Soft cap after AA increases (BiS default = max CS + PE)."""
    base = base_softcap(level)
    pct = aa_softcap_pct(
        combat_stability_rank=combat_stability_rank,
        physical_enhancement=physical_enhancement,
    )
    return base * (1.0 + pct / 100.0)


def best_post_cap_return(classes: list[str] | None) -> float:
    """Best (highest) overcap return among selected classes — tanks keep more."""
    if not classes:
        return 0.20
    return max(POST_CAP_RETURN.get(c, 0.15) for c in classes)


def valued_ac(
    item_ac: float,
    current_worn_ac: float,
    softcap: float,
    post_cap_return: float,
    *,
    under_weight: float = UNDER_SOFTCAP_AC_WEIGHT,
    over_weight: float = OVER_SOFTCAP_AC_WEIGHT,
) -> float:
    """Score contribution for adding item_ac given loadout AC already worn.

    Under softcap: full under_weight (hit the cap first).
    Over softcap: over_weight * class post-cap return (care about other stats more).
    """
    ac = max(0.0, float(item_ac or 0))
    if ac <= 0:
        return 0.0
    cur = max(0.0, float(current_worn_ac or 0))
    cap = max(1.0, float(softcap or 1))
    room = max(0.0, cap - cur)
    under = min(ac, room)
    over = max(0.0, ac - room)
    ret = max(0.0, min(1.0, float(post_cap_return)))
    return under * under_weight + over * over_weight * ret


def softcap_payload(
    level: int = 50,
    classes: list[str] | None = None,
    *,
    combat_stability_rank: int = 3,
    physical_enhancement: bool = True,
) -> dict[str, Any]:
    """Expose soft-cap model for API / UI notes."""
    base = base_softcap(level)
    pct = aa_softcap_pct(
        combat_stability_rank=combat_stability_rank,
        physical_enhancement=physical_enhancement,
    )
    target = softcap_target(
        level,
        combat_stability_rank=combat_stability_rank,
        physical_enhancement=physical_enhancement,
    )
    return {
        "level": max(1, min(50, int(level or 50))),
        "base_softcap": base,
        "formula": "level * 6 + 25 (eqlwiki Statistics/AC for level ≤ 50)",
        "combat_stability_rank": max(0, min(3, int(combat_stability_rank))),
        "combat_stability_pct": COMBAT_STABILITY_PCT.get(
            max(0, min(3, int(combat_stability_rank))), 0
        ),
        "physical_enhancement": bool(physical_enhancement),
        "physical_enhancement_pct": PHYSICAL_ENHANCEMENT_PCT if physical_enhancement else 0,
        "aa_softcap_pct": pct,
        "softcap_target": round(target, 2),
        "post_cap_return": best_post_cap_return(classes or []),
        "note": (
            "BiS assumes max Combat Stability + Physical Enhancement so the soft "
            "cap is the AA-raised target. Hit that worn-AC floor, then prefer other "
            "stats; overcap AC is lightly valued via class post-cap return. "
            "eqlwiki notes EQL caps may differ — working model only."
        ),
        "sources": [
            "https://eqlwiki.com/AC",
            "https://eqlwiki.com/Alternate_Advancement",
        ],
    }
