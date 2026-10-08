"""Item-name matching for inventory, owned gear, and saved builds.

The game export spells some catalog names differently. Matching is
case-insensitive, treats hyphens and spaces as the same, treats apostrophe
marks as optional, and collapses whitespace. A saved build that still has the
old catalog spelling resolves through the alias table.

Item IDs are used only when both sides actually have one. This module does
not invent an id for a row whose catalog itemID is null.
"""
from __future__ import annotations

import re
import unicodedata

# Apostrophe marks seen in catalog names and Inventory.txt (straight, curly, backtick).
_APOSTROPHES = "’‘`'ʼ´'"

# Old eqlegendstools spelling -> in-game / Inventory.txt spelling.
# Kept so a saved build that stored the old name still finds the item.
CANONICAL_ALIASES: dict[str, str] = {
    "Slime Blood of Cazic Thule": "Slime Blood of Cazic-Thule",
}


def _strip_tier(name: str) -> str:
    n = (name or "").strip()
    if n.endswith("*"):
        n = n[:-1].strip()
    match = re.search(r"(?:\s*\+\s*\d+)\s*$", n)
    if match:
        n = n[: match.start()].strip()
    return n


def owned_name_key(name: str) -> str:
    """Key for owned, equipped, and merge comparisons.

    Hyphens and spaces compare equal. Apostrophes compare equal to each other
    and to their absence. Extra whitespace collapses.
    """
    s = unicodedata.normalize("NFKC", _strip_tier(name))
    s = s.replace("\xa0", " ").replace("\u200b", "")
    for ch in _APOSTROPHES:
        s = s.replace(ch, "")
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip().casefold()
    return s


def names_match(a: str, b: str) -> bool:
    left = owned_name_key(a)
    right = owned_name_key(b)
    return bool(left) and left == right


def canonical_item_name(name: str) -> str:
    """Game spelling when this name is a known alias. Otherwise the base name."""
    base = _strip_tier(name)
    if not base:
        return ""
    key = owned_name_key(base)
    for old, canon in CANONICAL_ALIASES.items():
        if owned_name_key(old) == key or owned_name_key(canon) == key:
            return canon
    return base


def aliases_for(name: str) -> list[str]:
    """Other spellings that must still resolve to ``name``."""
    canon = canonical_item_name(name)
    if not canon:
        return []
    out = []
    for old, target in CANONICAL_ALIASES.items():
        if target == canon and old != canon:
            out.append(old)
    return out


def item_id_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text in {"0", "None"}:
        return ""
    return text
