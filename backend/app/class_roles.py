"""Class primary stats / roles for BiS weighting (EQ Legends).

Primary attribute bonuses come from data/races.json classStats (creation allotment).
Tank / mana roles follow classic EQ Legends class roles — used for Max-all and AI choice.
Never invents item stats; only class-level weighting hints.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import APP_ROOT

ATTR_KEYS = ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA")

# Classic EQ Legends tank / hybrid tanks — AC/HP weighed heavier in Max-all / AI.
TANK_CLASSES = frozenset({"Warrior", "Paladin", "Shadow Knight"})

# Classes that spend mana as a core resource.
MANA_CLASSES = frozenset({
    "Cleric", "Druid", "Shaman", "Wizard", "Magician", "Enchanter", "Necromancer",
    "Paladin", "Shadow Knight", "Ranger", "Beastlord", "Bard",
})

# Non-mana (or essentially non-mana) melee for mana-stat suppression.
NON_MANA_CLASSES = frozenset({"Warrior", "Monk", "Rogue", "Berserker"})

# Soft role tags for AI choice explanations / secondary weights.
ROLE_TAGS: dict[str, list[str]] = {
    "Warrior": ["tank", "melee"],
    "Paladin": ["tank", "healer", "melee"],
    "Shadow Knight": ["tank", "melee", "caster"],
    "Cleric": ["healer", "caster"],
    "Druid": ["healer", "caster", "utility"],
    "Shaman": ["healer", "caster", "utility"],
    "Wizard": ["dps", "caster"],
    "Magician": ["dps", "caster", "pet"],
    "Enchanter": ["utility", "caster"],
    "Necromancer": ["dps", "caster", "pet"],
    "Monk": ["dps", "melee"],
    "Rogue": ["dps", "melee"],
    "Ranger": ["dps", "melee", "hybrid"],
    "Bard": ["utility", "melee", "hybrid"],
    "Beastlord": ["dps", "pet", "hybrid"],
    "Berserker": ["dps", "melee"],
}


@lru_cache(maxsize=1)
def _load_class_stats() -> dict[str, dict[str, float]]:
    path = APP_ROOT / "data" / "races.json"
    out: dict[str, dict[str, float]] = {}
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for row in data.get("classStats") or []:
        name = (row.get("Class") or "").strip()
        if not name:
            continue
        out[name] = {k: float(row.get(k) or 0) for k in ATTR_KEYS}
    return out


def class_primary_attrs(class_name: str, *, top_n: int = 3) -> list[str]:
    """Return top creation-bonus attrs for a class (highest allotment first)."""
    stats = _load_class_stats().get(class_name) or {}
    ranked = sorted(
        ((k, stats.get(k, 0.0)) for k in ATTR_KEYS),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return [k for k, v in ranked if v > 0][:top_n] or [k for k, _ in ranked[:2]]


def trio_primary_attr_weights(classes: list[str]) -> dict[str, float]:
    """Sum creation bonuses across trio → relative attr weights (min 0)."""
    weights = {k: 0.0 for k in ATTR_KEYS}
    stats = _load_class_stats()
    for c in classes:
        row = stats.get(c) or {}
        for k in ATTR_KEYS:
            weights[k] += float(row.get(k) or 0)
    # Normalize so average positive weight ~1.5 scale similar to old attr*1.5
    total = sum(weights.values()) or 1.0
    scale = 30.0 * max(1, len(classes)) / total  # classStats total is 30 each
    return {k: (v * scale) / 10.0 for k, v in weights.items()}  # ~0..4.5 range


def trio_default_priority_tiers(classes: list[str]) -> dict[str, list[str]]:
    """Default selectable priority tiers from the trio's classStats ranking.

    Most important attrs → primary (up to 3), next → secondary, next → tertiary.
    Empty when no classes selected.
    """
    cleaned = [c for c in (classes or []) if c]
    if not cleaned:
        return {"primary": [], "secondary": [], "tertiary": []}
    weights = {k: 0.0 for k in ATTR_KEYS}
    stats = _load_class_stats()
    for c in cleaned:
        row = stats.get(c) or {}
        for k in ATTR_KEYS:
            weights[k] += float(row.get(k) or 0)
    ranked = [k for k, v in sorted(weights.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0]
    # If allotments are sparse, still fill from remaining attrs by role soft preference
    if len(ranked) < 3:
        for k in ATTR_KEYS:
            if k not in ranked:
                ranked.append(k)
    return {
        "primary": ranked[0:3],
        "secondary": ranked[3:6],
        "tertiary": ranked[6:9],
    }


def trio_has_tank(classes: list[str]) -> bool:
    return any(c in TANK_CLASSES for c in classes)


def trio_uses_mana(classes: list[str]) -> bool:
    return any(c in MANA_CLASSES for c in classes)


def trio_roles(classes: list[str]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for c in classes:
        for t in ROLE_TAGS.get(c, []):
            if t not in seen:
                seen.add(t)
                tags.append(t)
    return tags


def class_roles_payload() -> dict[str, Any]:
    """Expose roles + primary attrs for UI / meta."""
    stats = _load_class_stats()
    classes = []
    for name in sorted(stats.keys() or list(ROLE_TAGS.keys())):
        classes.append({
            "name": name,
            "primary_attrs": class_primary_attrs(name),
            "creation_bonuses": stats.get(name) or {},
            "is_tank": name in TANK_CLASSES,
            "uses_mana": name in MANA_CLASSES,
            "roles": ROLE_TAGS.get(name, []),
        })
    return {
        "classes": classes,
        "tank_classes": sorted(TANK_CLASSES),
        "mana_classes": sorted(MANA_CLASSES),
        "source": "data/races.json classStats + EQ Legends role map",
    }


def normalize_stat_key(stat: str | None) -> str | None:
    if not stat:
        return None
    s = str(stat).strip()
    aliases = {
        "Mana": "MANA", "SV Fire": "SVF", "SV Cold": "SVC", "SV Magic": "SVM",
        "SV Poison": "SVP", "SV Disease": "SVD", "HP Regen": "HP_REGEN",
        "Mana Regen": "MANA_REGEN", "End Regen": "END_REGEN",
    }
    if s in aliases:
        return aliases[s]
    up = s.upper().replace(" ", "_")
    return up
