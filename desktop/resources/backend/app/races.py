"""Race base stats verified from public EQ Legends sources.

Primary decode: eqlegendstools.com char-sheet core bundle
(`/api/r/05ef4a7f7f1efd0a352de2de`, decoded 2026-09-06) — raceStats / raceSaves / classStats.
Cross-check: eqlwiki.com/Race Base Stats table (same attribute numbers).
Stored copy: /workspace/eq-legends-app/data/races.json
"""
from __future__ import annotations
import json
from pathlib import Path

def _races_json() -> Path:
    from .paths import APP_ROOT, app_root
    for c in (
        APP_ROOT / "data" / "races.json",
        app_root() / "resources" / "data" / "races.json",
        app_root() / "data" / "races.json",
    ):
        if c.exists():
            return c
    return APP_ROOT / "data" / "races.json"

DATA = _races_json()

RACE_SOURCE = {
    "url": "https://eqlegendstools.com/char-sheet/",
    "cross_check": "https://eqlwiki.com/Race",
    "title": "EQ Legends race base stats",
    "fetched": "2026-09-06",
    "note": "Attrs+saves from eqlegendstools decoded core; attrs match eqlwiki Base Stats table.",
}

_ATTRS = ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA")
_ABBREV = {
    "Barbarian": "BAR", "Dark Elf": "DEF", "Dwarf": "DWF", "Erudite": "ERU",
    "Froglok": "FRG", "Gnome": "GNM", "Half-Elf": "HEF", "Halfling": "HFL",
    "High Elf": "HIE", "Human": "HUM", "Iksar": "IKS", "Kerran": "KER",
    "Ogre": "OGR", "Troll": "TRL", "Wood Elf": "ELF",
}


def _load_bundle() -> dict:
    if DATA.exists():
        return json.loads(DATA.read_text())
    return {}


def _races_from_bundle() -> list[dict]:
    bundle = _load_bundle()
    rows = bundle.get("raceStats") or []
    out = []
    for row in rows:
        name = row.get("Race") or ""
        if not name:
            continue
        rid = name.lower().replace("-", "_").replace(" ", "_")
        bases = {k: int(row.get(k) or 0) for k in _ATTRS}
        out.append({
            "id": rid,
            "name": name,
            "abbrev": _ABBREV.get(name, name[:3].upper()),
            "bases": bases,
            "total": int(row.get("Total") or sum(bases.values())),
        })
    return out


def _saves_map() -> dict[str, dict]:
    bundle = _load_bundle()
    out = {}
    for row in bundle.get("raceSaves") or []:
        name = row.get("Race") or ""
        out[name] = {
            "SVM": int(row.get("SV Magic") or 0),
            "SVF": int(row.get("SV Fire") or 0),
            "SVC": int(row.get("SV Cold") or 0),
            "SVD": int(row.get("SV Disease") or 0),
            "SVP": int(row.get("SV Poison") or 0),
        }
    return out


def _class_stats_map() -> dict[str, dict]:
    bundle = _load_bundle()
    out = {}
    for row in bundle.get("classStats") or []:
        name = row.get("Class") or ""
        if not name:
            continue
        out[name] = {k: int(row.get(k) or 0) for k in _ATTRS}
        out[name]["Total"] = int(row.get("Total") or sum(out[name].values()))
    return out


def class_stat_rows(classes: list[str] | None) -> list[dict]:
    """Creation allotment rows for each selected class (eqlegendstools classStats)."""
    table = _class_stats_map()
    rows = []
    for c in classes or []:
        if c in table:
            rows.append({"Class": c, **table[c]})
    return rows


def get_races_payload() -> dict:
    races = _races_from_bundle()
    saves = _saves_map()
    bases_available = bool(races)
    enriched = []
    for r in races:
        item = dict(r)
        item["resists"] = saves.get(r["name"], {})
        enriched.append(item)
    return {
        "source": RACE_SOURCE,
        "bases_available": bases_available,
        "races": enriched,
        "class_stats": [
            {"Class": k, **v} for k, v in _class_stats_map().items()
        ],
        "note": (
            "Attribute bases and racial resists from eqlegendstools (verified; matches eqlwiki). "
            "Live Totals HP/Mana/END use the eqlegendstools char-sheet pool formulas "
            "(race + class allotments + STA/INT/WIS); gear still from decoded JSON only."
            if bases_available else
            "Race base stats unavailable — using zero bases. Do not invent numbers."
        ),
    }


def race_bases(race_name: str | None) -> dict:
    if not race_name:
        return {}
    key = race_name.strip().lower().replace("-", " ").replace("_", " ")
    for r in _races_from_bundle():
        if r["name"].lower() == key or r["id"].replace("_", " ") == key or r["abbrev"].lower() == key:
            bases = dict(r["bases"])
            saves = _saves_map().get(r["name"], {})
            bases.update(saves)
            return bases
    return {}


# Compatibility alias used by engine.py
def _ensure_races_list():
    return _races_from_bundle()

RACES = _races_from_bundle()  # populated at import from data/races.json
