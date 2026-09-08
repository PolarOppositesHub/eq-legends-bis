"""Spell buff catalog + Quick Buff (Cast Buffs) for Live Totals.

Source: eqlegendstools.com char-sheet `spellBuffs` bundle (decoded alongside
raceStats), enriched with cast levels from eqlwiki spell pages and lower-rank
lines so mid-level characters are not stuck with L50-only max buffs.

Quick Buff mirrors their `qt()` stacking rules, then keeps only buffs the
selected trio can cast at the chosen character level.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import APP_ROOT, app_root

SOURCE = {
    "url": "https://eqlegendstools.com/char-sheet/",
    "title": "EQ Legends Tools spellBuffs + eqlwiki cast levels",
    "note": (
        "Buff effects from the eqlegendstools char-sheet catalog (plus lower-rank "
        "eqlwiki lines). Cast levels from eqlwiki Classes lists. Quick Buff picks "
        "the highest stacking priority per group among buffs your selected classes "
        "can cast at the current Character Level. Icons from eqlegendstools spellicons."
    ),
}

# Human labels for stacking groups (Quick Buff UI grouping).
GROUP_LABELS: dict[str, str] = {
    "hp-buff-one": "HP Buff",
    "hp-buff-two": "HP Buff (2)",
    "shielding": "Shielding",
    "symbol": "Symbol",
    "armor-class": "Armor Class",
    "strength": "Strength",
    "stamina": "Stamina",
    "agility": "Agility",
    "dexterity": "Dexterity",
    "yaulp": "Yaulp",
    "rage": "Rage / Frenzy",
    "haste": "Haste",
    "chloroplast": "Chloroplast",
    "resist-magic": "Resist Magic",
    "resist-fire": "Resist Fire",
    "resist-cold": "Resist Cold",
    "resist-poison": "Resist Poison",
    "resist-disease": "Resist Disease",
    "other": "Other Buffs",
}

# Preferred display order for Quick Buff groups.
GROUP_ORDER = [
    "haste",
    "hp-buff-one",
    "hp-buff-two",
    "shielding",
    "symbol",
    "armor-class",
    "strength",
    "stamina",
    "agility",
    "dexterity",
    "yaulp",
    "rage",
    "resist-magic",
    "resist-fire",
    "resist-cold",
    "resist-poison",
    "resist-disease",
    "chloroplast",
    "other",
]

EFFECT_LABELS = {
    "HP": "HP",
    "MANA": "Mana",
    "END": "Endurance",
    "AC": "AC",
    "STR": "STR",
    "STA": "STA",
    "AGI": "AGI",
    "DEX": "DEX",
    "WIS": "WIS",
    "INT": "INT",
    "CHA": "CHA",
    "SVF": "SV Fire",
    "SVC": "SV Cold",
    "SVM": "SV Magic",
    "SVP": "SV Poison",
    "SVD": "SV Disease",
    "ATK": "ATK",
    "HASTE": "Haste",
    "HP_REGEN": "HP Regen",
    "MANA_REGEN": "Mana Regen",
    "END_REGEN": "Endurance Regen",
}


def _buffs_json() -> Path:
    for c in (
        APP_ROOT / "data" / "spell_buffs.json",
        app_root() / "resources" / "data" / "spell_buffs.json",
        app_root() / "data" / "spell_buffs.json",
    ):
        if c.exists():
            return c
    return APP_ROOT / "data" / "spell_buffs.json"


@lru_cache(maxsize=1)
def load_spell_buffs() -> dict[str, Any]:
    path = _buffs_json()
    if not path.exists():
        return {"source": SOURCE, "buffs": [], "verified": False}
    data = json.loads(path.read_text())
    return {
        "source": {**SOURCE, **({k: data.get(k) for k in ("source", "verified", "schemaVersion", "levelNote") if k in data})},
        "buffs": list(data.get("buffs") or []),
        "verified": bool(data.get("verified", True)),
    }


def _norm_class(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "")


def _level_for_class(buff: dict[str, Any], class_name: str) -> int | None:
    """Cast level for one class from eqlwiki levels_by_class, else buff.level."""
    by = buff.get("levels_by_class") or {}
    want = _norm_class(class_name)
    for k, v in by.items():
        if _norm_class(str(k)) == want:
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
    if buff.get("level") is not None:
        try:
            return int(buff["level"])
        except (TypeError, ValueError):
            return None
    return None


def buff_castable_at(
    buff: dict[str, Any],
    classes: list[str],
    character_level: int,
) -> bool:
    """True if any selected class can cast this buff at character_level."""
    selected = {_norm_class(c) for c in (classes or []) if c}
    if not selected:
        return False
    lv = max(1, min(50, int(character_level or 50)))
    castable_classes = buff.get("classes") or []
    matched = False
    for c in castable_classes:
        if _norm_class(c) not in selected:
            continue
        matched = True
        need = _level_for_class(buff, c)
        if need is None:
            # Unknown level: only allow at cap so we never grant high lines early.
            if lv >= 50:
                return True
            continue
        if need <= lv:
            return True
    return False if matched else False


def available_buffs(
    classes: list[str],
    *,
    character_level: int = 50,
) -> list[dict[str, Any]]:
    """Buffs any selected class can cast at character_level, minus redundant endure lines."""
    selected = {c for c in (classes or []) if c}
    if not selected:
        return []
    lv = max(1, min(50, int(character_level or 50)))
    rows = load_spell_buffs().get("buffs") or []
    usable = [
        b for b in rows
        if selected.intersection(set(b.get("classes") or []))
        and buff_castable_at(b, list(selected), lv)
    ]
    groups_present = {
        (b.get("stacking") or {}).get("group")
        for b in usable
        if (b.get("stacking") or {}).get("group")
    }
    out = []
    for b in usable:
        st = b.get("stacking") or {}
        red = st.get("redundantWhenAvailable")
        if red and red in groups_present:
            # Hide Endure X when a Resist line in that group is available at this level.
            continue
        out.append(b)
    return out


def _priority(buff: dict[str, Any]) -> int:
    return int((buff.get("stacking") or {}).get("priority") or 0)


def _group(buff: dict[str, Any]) -> str | None:
    return (buff.get("stacking") or {}).get("group")


def group_label(group: str | None) -> str:
    g = (group or "other").strip() or "other"
    if g in GROUP_LABELS:
        return GROUP_LABELS[g]
    return g.replace("-", " ").title()


def format_effects_lines(effects: dict[str, Any] | None) -> list[str]:
    """Signed effect lines for hover tip (catalog values only)."""
    lines: list[str] = []
    for k, v in (effects or {}).items():
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if abs(n) < 1e-9:
            continue
        label = EFFECT_LABELS.get(k, k)
        if k == "HASTE":
            lines.append(f"{label} +{int(n) if n == int(n) else n}%")
        else:
            num = int(n) if n == int(n) else n
            sign = "+" if n > 0 else ""
            lines.append(f"{label} {sign}{num}")
    return lines


def buff_hover_text(buff: dict[str, Any]) -> str:
    """In-game-style explanation from catalog tooltip + effects (never invented)."""
    parts: list[str] = []
    tip = (buff.get("tooltip") or "").strip()
    if tip:
        parts.append(tip)
    effect_lines = format_effects_lines(buff.get("effects") or {})
    if effect_lines:
        parts.append("Effects:\n" + "\n".join(f"  {ln}" for ln in effect_lines))
    classes = buff.get("classes") or []
    lv = buff.get("level")
    meta = []
    if classes:
        meta.append(", ".join(str(c) for c in classes))
    if lv is not None:
        meta.append(f"L{lv}")
    if meta:
        parts.append(" · ".join(meta))
    return "\n\n".join(parts) if parts else "No buff details in catalog."


def _public_buff(buff: dict[str, Any]) -> dict[str, Any]:
    st = buff.get("stacking") or {}
    group = st.get("group") or "other"
    icon = buff.get("icon") or ""
    return {
        "id": buff["id"],
        "name": buff["name"],
        "classes": buff.get("classes") or [],
        "level": buff.get("level"),
        "effects": buff.get("effects") or {},
        "tooltip": buff.get("tooltip") or "",
        "hover_text": buff_hover_text(buff),
        "icon": icon,
        "icon_url": f"/api/spell-icon?name={icon}" if icon else "",
        "stacking_group": group,
        "group_label": group_label(group),
        "stacking": st,
    }


def group_active_buffs(active: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group public buff rows for Simulator UI."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for b in active or []:
        g = b.get("stacking_group") or ((b.get("stacking") or {}).get("group")) or "other"
        buckets.setdefault(g, []).append(b)
    ordered_keys = [g for g in GROUP_ORDER if g in buckets]
    ordered_keys.extend(sorted(k for k in buckets if k not in GROUP_ORDER))
    groups = []
    for g in ordered_keys:
        rows = sorted(buckets[g], key=lambda x: (x.get("name") or ""))
        groups.append({
            "id": g,
            "label": group_label(g),
            "buffs": rows,
        })
    return groups


def spell_icons_dir() -> Path:
    for c in (
        APP_ROOT / "data" / "spell-icons",
        app_root() / "resources" / "data" / "spell-icons",
        app_root() / "data" / "spell-icons",
        app_root() / "desktop" / "resources" / "data" / "spell-icons",
    ):
        if c.is_dir():
            return c
    return APP_ROOT / "data" / "spell-icons"


def resolve_spell_icon(name: str) -> Path | None:
    """Resolve a catalog icon filename under data/spell-icons (basename only)."""
    raw = (name or "").strip()
    if not raw:
        return None
    base = Path(raw).name
    if not base.lower().endswith(".png"):
        base = f"{base}.png"
    # Reject path tricks
    if base != Path(base).name or ".." in base:
        return None
    path = spell_icons_dir() / base
    if path.is_file():
        return path
    return None


def quick_buff_ids(classes: list[str], *, character_level: int = 50) -> list[str]:
    """qt() — highest-priority non-conflicting set for the trio at this level."""
    candidates = sorted(
        available_buffs(classes, character_level=character_level),
        key=lambda b: (-_priority(b), b.get("name") or ""),
    )
    chosen: list[dict[str, Any]] = []
    for buff in candidates:
        g = _group(buff)
        if g and any(_group(c) == g for c in chosen):
            continue
        excludes = set((buff.get("stacking") or {}).get("excludes") or [])
        if any(
            buff["id"] in set((c.get("stacking") or {}).get("excludes") or [])
            or c["id"] in excludes
            for c in chosen
        ):
            continue
        chosen.append(buff)
    return [b["id"] for b in chosen]


def buffs_by_ids(
    ids: list[str],
    classes: list[str] | None = None,
    *,
    character_level: int = 50,
) -> list[dict[str, Any]]:
    if classes is not None:
        allow = {b["id"]: b for b in available_buffs(classes, character_level=character_level)}
    else:
        allow = {b["id"]: b for b in (load_spell_buffs().get("buffs") or [])}
    out = []
    for i in ids or []:
        b = allow.get(i)
        if b:
            out.append(b)
    return out


def aggregate_buff_effects(buffs: list[dict[str, Any]]) -> dict[str, float]:
    """Vt() — sum effects; Haste takes max."""
    stats: dict[str, float] = {}
    haste = 0.0
    for b in buffs or []:
        for k, v in (b.get("effects") or {}).items():
            if k == "HASTE":
                haste = max(haste, float(v or 0))
                continue
            stats[k] = stats.get(k, 0.0) + float(v or 0)
    if haste:
        stats["HASTE"] = haste
    return stats


def cast_buffs_payload(
    classes: list[str],
    *,
    mode: str = "off",
    active_ids: list[str] | None = None,
    character_level: int = 50,
) -> dict[str, Any]:
    """
    mode:
      - off: no buffs
      - quick: auto max-priority set for trio classes at character_level
      - manual: use active_ids (filtered to available at character_level)
    """
    lv = max(1, min(50, int(character_level or 50)))
    avail = available_buffs(classes, character_level=lv)
    mode_n = (mode or "off").strip().lower()
    if mode_n in ("quick", "auto", "max", "on", "true", "1"):
        ids = quick_buff_ids(classes, character_level=lv)
        mode_n = "quick"
    elif mode_n in ("manual", "custom"):
        ids = [i for i in (active_ids or []) if i]
        mode_n = "manual"
    else:
        ids = []
        mode_n = "off"

    active = buffs_by_ids(ids, classes, character_level=lv)
    if mode_n == "manual":
        pruned: list[dict[str, Any]] = []
        for b in sorted(active, key=lambda x: (-_priority(x), x.get("name") or "")):
            g = _group(b)
            if g and any(_group(c) == g for c in pruned):
                continue
            pruned.append(b)
        active = pruned
        ids = [b["id"] for b in active]

    effects = aggregate_buff_effects(active)
    active_public = [_public_buff(b) for b in active]
    available_public = [
        _public_buff(b) for b in sorted(avail, key=lambda x: x.get("name") or "")
    ]
    return {
        "mode": mode_n,
        "character_level": lv,
        "available": available_public,
        "active_ids": ids,
        "active": active_public,
        "groups": group_active_buffs(active_public),
        "effects": effects,
        "source": SOURCE,
        "note": (
            f"Quick Buff at character level {lv}: only spells a selected class "
            f"can cast at that level (eqlwiki cast levels)."
            if mode_n == "quick"
            else None
        ),
    }
