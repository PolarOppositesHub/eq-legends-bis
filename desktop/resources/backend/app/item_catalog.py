"""Item catalog search + image cache (eqlwiki / local).

Looks up item icons from eqlwiki when missing and saves under data/item-images/
for reuse across BiS, Simulator, and Item Search. Never invents item stats.
"""
from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import APP_ROOT, decoded_dir, image_seed_dirs, images_dir

USER_AGENT = "EQLegendsBiS/1.0.10 (local; josh; item-icon-cache)"

# Serialize wiki fetches so BiS first-paint does not stampede eqlwiki.
_ensure_locks: dict[str, Any] = {}
_ensure_guard = None


def _images_dir() -> Path:
    return images_dir()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-").lower()
    return s or "item"


# Tooltip line stats — same keys as build_planner.parse_tip_stats (real lines only).
_TIP_STAT_PAT = re.compile(
    r"(AC|HP|MANA|END|STR|STA|AGI|DEX|WIS|INT|CHA|ATK|DMG|Haste|"
    r"SV FIRE|SV COLD|SV MAGIC|SV POISON|SV DISEASE|SV VOID|"
    r"FIRE DMG|COLD DMG)\s*:\s*\+?(-?\d+)",
    re.I,
)
_TIP_DLY_PAT = re.compile(r"Atk Delay:\s*(\d+)", re.I)
_TIP_STAT_MAP = {
    "AC": "AC", "HP": "HP", "MANA": "MANA", "END": "END",
    "STR": "STR", "STA": "STA", "AGI": "AGI", "DEX": "DEX",
    "WIS": "WIS", "INT": "INT", "CHA": "CHA", "ATK": "ATK",
    "DMG": "DMG", "HASTE": "Haste",
    "SV FIRE": "SVF", "SV COLD": "SVC", "SV MAGIC": "SVM",
    "SV POISON": "SVP", "SV DISEASE": "SVD", "SV VOID": "SVV",
    "FIRE DMG": "FIRE_DMG", "COLD DMG": "COLD_DMG",
}
_SCALABLE = {
    "AC", "HP", "MANA", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA",
    "END", "ATK", "SVM", "SVF", "SVC", "SVD", "SVP", "SVV",
}


def _parse_tip_stats(lines: list[Any] | None) -> dict[str, Any]:
    """Parse AC/HP/…/DMG/DLY from real tooltip lines only — never invent."""
    stats: dict[str, Any] = {}
    for line in lines or []:
        s = str(line)
        for m in _TIP_STAT_PAT.finditer(s):
            key = _TIP_STAT_MAP.get(m.group(1).upper())
            if key:
                stats[key] = int(m.group(2))
        m2 = _TIP_DLY_PAT.search(s)
        if m2:
            stats["DLY"] = int(m2.group(1))
    return stats


def _scale_stats_plus10(stats0: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (stats0 or {}).items():
        if k == "DMG":
            try:
                out[k] = float(math.floor(float(v) * 2))
            except (TypeError, ValueError):
                continue
        elif k in ("DLY", "FIRE_DMG", "COLD_DMG", "Haste"):
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
        elif k in _SCALABLE:
            try:
                o = float(v)
                a = math.floor(o * 2)
                out[k] = float(max(a, o + 10) if o > 0 else o)
            except (TypeError, ValueError):
                continue
    return out


def _slots_classes_from_lines(lines: list[Any] | None) -> tuple[list[str], list[str]]:
    slots: list[str] = []
    classes: list[str] = []
    for line in lines or []:
        s = str(line).strip()
        low = s.lower()
        if low.startswith("slot:"):
            slots = [p.strip().upper() for p in s.split(":", 1)[1].split() if p.strip()]
        elif low.startswith("class:"):
            raw = s.split(":", 1)[1].strip()
            classes = [p.strip() for p in re.split(r"[,/]", raw) if p.strip()]
    return slots, classes


def _zone_from_tip(tip: dict[str, Any]) -> tuple[str, str, str]:
    """Return (zone, drops_mobs, quest_source) from tip fields / lines."""
    drops = tip.get("dropsFrom") or []
    zones: list[str] = []
    mobs: list[str] = []
    if isinstance(drops, list):
        for e in drops:
            if isinstance(e, dict):
                if e.get("location"):
                    zones.append(str(e["location"]))
                if e.get("npc"):
                    mobs.append(str(e["npc"]))
            elif isinstance(e, str) and e.strip():
                zones.append(e.strip())
    quests = tip.get("rewardFromQuests") or []
    quest_source = ""
    if isinstance(quests, list) and quests:
        quest_source = f"Reward from quest: {quests[0]}"
    for line in tip.get("lines") or []:
        s = str(line).strip()
        low = s.lower()
        if low.startswith("drops from:") and not zones:
            rest = s.split(":", 1)[1].strip() if ":" in s else ""
            zones.append(rest.split(":")[0].strip() if ":" in rest else rest)
        if low.startswith("reward from") and not quest_source:
            quest_source = s
    zone = ", ".join(dict.fromkeys(zones))
    drops_mobs = ", ".join(dict.fromkeys(mobs))
    return zone, drops_mobs, quest_source


def _tooltip_row(tip: dict[str, Any], *, kind: str) -> dict[str, Any] | None:
    if not isinstance(tip, dict):
        return None
    name = (tip.get("name") or "").strip()
    if not name:
        return None
    lines = list(tip.get("lines") or tip.get("tooltipLines") or [])
    s0 = _parse_tip_stats(lines)
    if tip.get("stats") and isinstance(tip["stats"], dict):
        s0 = {**s0, **tip["stats"]}
    s10 = tip.get("stats_plus10") if isinstance(tip.get("stats_plus10"), dict) else None
    if not s10:
        s10 = _scale_stats_plus10(s0) if s0 else {}
    slots, classes = _slots_classes_from_lines(lines)
    if tip.get("slots"):
        slots = [str(s).strip().upper() for s in tip["slots"] if s]
    if tip.get("classes") or tip.get("classNames"):
        classes = list(tip.get("classes") or tip.get("classNames") or [])
    zone, drops_mobs, quest_source = _zone_from_tip(tip)
    return {
        "name": name,
        "itemID": tip.get("itemID"),
        "slots": slots,
        "slot": " / ".join(slots),
        "classes": classes,
        "classes_str": ", ".join(classes),
        "stats_plus0": s0,
        "stats_plus10": s10,
        "url": tip.get("sourceHref") or "",
        "sourceUrl": tip.get("sourceUrl") or "",
        "zamUrl": tip.get("zamUrl") or "",
        "zone": zone,
        "drops_mobs": drops_mobs,
        "quest_source": quest_source,
        "tooltipLines": lines,
        "catalog_kind": kind,
        "from_catalog_tooltip": True,
    }


def _name_key(name: str) -> str:
    """Casefold + normalize apostrophes/whitespace for catalog matching."""
    import unicodedata

    s = unicodedata.normalize("NFKC", name or "")
    s = s.replace("\xa0", " ").replace("\u200b", "").strip().lower()
    for ch in ("’", "‘", "`", "ʼ", "´"):
        s = s.replace(ch, "'")
    s = re.sub(r"\s+", " ", s)
    return s


def _threading_lock():
    global _ensure_guard
    if _ensure_guard is None:
        import threading

        _ensure_guard = threading.Lock()
    return _ensure_guard


def _lock_for(name: str):
    import threading

    key = (name or "").strip().lower() or "item"
    with _threading_lock():
        lock = _ensure_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _ensure_locks[key] = lock
        return lock


def _merge_row(by_name: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    name = (row.get("name") or "").strip()
    if not name:
        return
    key = _name_key(name)
    if key not in by_name:
        by_name[key] = row
        return
    cur = by_name[key]
    # Prefer entry with more stats / url; fill missing fields from new row
    if not (cur.get("stats_plus10") or cur.get("stats_plus0")) and (
        row.get("stats_plus10") or row.get("stats_plus0")
    ):
        by_name[key] = {**row, **{k: cur[k] for k in cur if cur.get(k) and not row.get(k)}}
        cur = by_name[key]
    for fld in (
        "url", "sourceUrl", "zamUrl", "zone", "itemID", "classes_str",
        "drops_mobs", "quest_source",
    ):
        if not cur.get(fld) and row.get(fld):
            cur[fld] = row[fld]
    if not cur.get("classes") and row.get("classes"):
        cur["classes"] = row["classes"]
    if not cur.get("slots") and row.get("slots"):
        cur["slots"] = row["slots"]
    if not cur.get("tooltipLines") and row.get("tooltipLines"):
        cur["tooltipLines"] = row["tooltipLines"]
    if row.get("is_weapon"):
        cur["is_weapon"] = True
    if (not cur.get("stats_plus0")) and row.get("stats_plus0"):
        cur["stats_plus0"] = row["stats_plus0"]
    if (not cur.get("stats_plus10")) and row.get("stats_plus10"):
        cur["stats_plus10"] = row["stats_plus10"]
    if "_" in (cur.get("name") or "") and "_" not in name:
        cur["name"] = name


def _weapon_row_from_catalog(w: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize catalog.weapons / proc rows into search shape (real DMG/DLY only)."""
    name = (w.get("weaponName") or w.get("itemName") or w.get("name") or "").strip()
    if not name:
        return None
    classes = list(w.get("classNames") or w.get("classes") or [])
    slots = [str(s).strip().upper() for s in (w.get("slots") or []) if s]
    s0: dict[str, Any] = {}
    dmg = w.get("dmg")
    dly = w.get("dly")
    if dmg is not None:
        s0["DMG"] = dmg
    if dly is not None:
        s0["DLY"] = dly
    zone = (w.get("sourceZone") or w.get("sourceDisplay") or "").strip()
    if not zone:
        locs = []
        for e in w.get("dropsFromEntries") or []:
            if isinstance(e, dict) and e.get("location"):
                locs.append(str(e["location"]))
        zone = ", ".join(dict.fromkeys(locs))
    return {
        "name": name,
        "itemID": w.get("itemID"),
        "slots": slots,
        "slot": " / ".join(slots),
        "classes": classes,
        "classes_str": ", ".join(classes),
        "stats_plus0": s0,
        "stats_plus10": dict(s0),
        "url": w.get("sourceHref") or "",
        "sourceUrl": w.get("sourceUrl") or "",
        "zamUrl": w.get("zamUrl") or "",
        "zone": zone,
        "tooltipLines": w.get("tooltipLines") or [],
        "is_weapon": True,
        "from_catalog_weapons": True,
    }


def _named_catalog_row(row: dict[str, Any], *, kind: str) -> dict[str, Any] | None:
    name = (row.get("itemName") or row.get("weaponName") or row.get("name") or "").strip()
    if not name:
        return None
    classes = list(row.get("classNames") or row.get("classes") or [])
    slots = [str(s).strip().upper() for s in (row.get("slots") or []) if s]
    return {
        "name": name,
        "itemID": row.get("itemID"),
        "slots": slots,
        "slot": " / ".join(slots) if slots else (row.get("slot") or ""),
        "classes": classes,
        "classes_str": ", ".join(classes),
        "stats_plus0": row.get("stats") or row.get("stats_plus0") or {},
        "stats_plus10": row.get("stats_plus10") or row.get("stats") or {},
        "url": row.get("sourceHref") or "",
        "sourceUrl": row.get("sourceUrl") or "",
        "zamUrl": row.get("zamUrl") or "",
        "zone": (row.get("sourceZone") or row.get("sourceDisplay") or "").strip(),
        "tooltipLines": row.get("tooltipLines") or [],
        "catalog_kind": kind,
    }


def _load_json(path: Path) -> Any:
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@lru_cache(maxsize=1)
def _all_flat_items() -> list[dict[str, Any]]:
    """Union of flat_* + aggregate + catalog.json lists + tooltip item maps.

    Never invents stats. Missing/corrupt files are skipped so search/import
    degrade to an empty or partial catalog instead of raising.
    """
    by_name: dict[str, dict[str, Any]] = {}
    try:
        decoded = decoded_dir()
    except Exception:
        return []
    try:
        if not decoded.exists():
            return []
    except OSError:
        return []
    try:
        flat_paths = sorted(decoded.glob("flat_*.json"))
    except OSError:
        flat_paths = []
    for path in flat_paths:
        rows = _load_json(path)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                try:
                    _merge_row(by_name, row)
                except Exception:
                    continue
    agg_rows = _load_json(decoded / "aggregate.json")
    for row in agg_rows if isinstance(agg_rows, list) else []:
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        try:
            _merge_row(by_name, {
                "name": name,
                "itemID": row.get("itemID"),
                "slots": row.get("slots") or [],
                "classes": row.get("classes") or [],
                "stats_plus0": row.get("stats") or {},
                "stats_plus10": row.get("stats") or {},
                "url": row.get("sourceHref") or row.get("sourceUrl") or "",
                "sourceUrl": row.get("sourceUrl") or "",
                "zamUrl": row.get("zamUrl") or "",
                "zone": row.get("sourceZone") or "",
                "tooltipLines": row.get("tooltipLines") or [],
                "from_aggregate_only": True,
            })
        except Exception:
            continue
    catalog = _load_json(decoded / "catalog.json")
    if isinstance(catalog, dict):
        for w in catalog.get("weapons") or []:
            if not isinstance(w, dict):
                continue
            try:
                norm = _weapon_row_from_catalog(w)
                if norm:
                    _merge_row(by_name, norm)
            except Exception:
                continue
        for w in catalog.get("proc") or []:
            if not isinstance(w, dict):
                continue
            try:
                norm = _weapon_row_from_catalog(w)
                if norm:
                    _merge_row(by_name, norm)
            except Exception:
                continue
        for kind in ("focus", "bardResonance", "clickies", "worn"):
            for row in catalog.get(kind) or []:
                if not isinstance(row, dict):
                    continue
                try:
                    norm = _named_catalog_row(row, kind=kind)
                    if norm:
                        _merge_row(by_name, norm)
                except Exception:
                    continue
        # Tooltip item maps often hold instruments/clickies not in list sections.
        for kind in (
            "tooltips",
            "focusItemTooltips",
            "clickyItemTooltips",
            "wornItemTooltips",
            "procItemTooltips",
        ):
            tip_map = catalog.get(kind) or {}
            if not isinstance(tip_map, dict):
                continue
            for tip in tip_map.values():
                try:
                    norm = _tooltip_row(tip if isinstance(tip, dict) else {}, kind=kind)
                    if norm:
                        _merge_row(by_name, norm)
                except Exception:
                    continue

    # Full game coverage: every eqlwiki Category:Items name (equipable + non-equipable).
    # Wiki-only rows start without stats; Item Detail may fill from the real wiki page.
    try:
        wiki = _wiki_display_names()
    except Exception:
        wiki = {}
    for key, display in wiki.items():
        if not display or str(key).startswith("__"):
            continue
        title = display.replace(" ", "_")
        wiki_url = f"https://eqlwiki.com/{urllib.parse.quote(title)}"
        if key in by_name:
            cur = by_name[key]
            if not cur.get("catalog_source"):
                cur["catalog_source"] = "tools"
            if not (cur.get("url") or cur.get("sourceUrl")):
                cur["url"] = wiki_url
                cur["sourceUrl"] = wiki_url
            # Attach catalog reward quests when known.
            quests = _quests_payload_for_item(display)
            if quests and not cur.get("quests"):
                cur["quests"] = quests
            continue
        by_name[key] = {
            "name": display,
            "itemID": None,
            "slots": [],
            "classes": [],
            "classes_str": "",
            "stats_plus0": {},
            "stats_plus10": {},
            "tooltipLines": [],
            "zone": "",
            "url": wiki_url,
            "sourceUrl": wiki_url,
            "catalog_source": "eqlwiki",
            "has_stats": False,
            "quests": _quests_payload_for_item(display),
        }

    for row in by_name.values():
        if not row.get("catalog_source"):
            row["catalog_source"] = "tools"
        stats = row.get("stats_plus0") or row.get("stats_plus10") or {}
        row["has_stats"] = bool(stats) or bool(row.get("tooltipLines"))
        if not row.get("quests"):
            row["quests"] = _quests_payload_for_item(row.get("name") or "")

    return list(by_name.values())


def search_items(
    q: str = "",
    *,
    slot: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Search catalog. Never raises — empty catalog when data is missing."""
    qn = (q or "").strip().lower()
    slot_u = (slot or "").strip().upper() or None
    try:
        pool = _all_flat_items()
    except Exception:
        pool = []
    hits: list[dict[str, Any]] = []
    for it in pool:
        try:
            name = it.get("name") or ""
            if qn and qn not in name.lower():
                blob = f"{name} {it.get('classes_str') or ''} {it.get('zone') or ''}".lower()
                if qn not in blob:
                    continue
            if slot_u:
                slots = {str(s).upper() for s in (it.get("slots") or [])}
                slot_field = str(it.get("slot") or "").upper()
                if slot_u not in slots and slot_u not in slot_field.replace("/", " ").split():
                    if not any(slot_u in str(s).upper() for s in slots) and slot_u not in slot_field:
                        continue
            hits.append(_public_item(it))
        except Exception:
            continue
    hits.sort(key=lambda r: (r["name"] or "").lower())
    total = len(hits)
    page = hits[offset: offset + max(1, min(200, limit))]
    decoded_s = ""
    try:
        decoded_s = str(decoded_dir())
    except Exception:
        decoded_s = ""
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": q,
        "slot": slot_u,
        "items": page,
        "catalog_size": len(pool),
        "tools_items": sum(1 for it in pool if (it.get("catalog_source") or "tools") == "tools"),
        "eqlwiki_names": sum(1 for it in pool if it.get("catalog_source") == "eqlwiki"),
        "decoded_dir": decoded_s,
        "index_path": (_wiki_name_index().get("__index_path__") if _wiki_name_index() else "") or "",
        "warning": None if pool else "Item catalog empty — decoded data missing or unreadable.",
        "note": (
            "Search covers eqlegendstools decoded items plus every eqlwiki Category:Items name "
            "(including non-equipable). Stats/descriptions come only from decoded data or the "
            "item's eqlwiki page — never invented."
        ),
    }


@lru_cache(maxsize=1)
def _flat_by_name() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        for it in _all_flat_items():
            key = _name_key(it.get("name") or "")
            if key and key not in out:
                out[key] = it
    except Exception:
        return {}
    return out


@lru_cache(maxsize=1)
def _flat_by_id() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        for it in _all_flat_items():
            iid = it.get("itemID")
            if iid is None or str(iid).strip() == "":
                continue
            out[str(iid).strip()] = it
    except Exception:
        return {}
    return out


@lru_cache(maxsize=1)
def _wiki_name_index() -> dict[str, str]:
    """eqlwiki Category:Items names from any known decoded / resources location."""
    out: dict[str, str] = {}
    candidates: list[Path] = []
    decoded = None
    try:
        decoded = decoded_dir()
        candidates.append(decoded / "eqlwiki_item_names.json")
    except Exception:
        decoded = None
    root = APP_ROOT
    candidates.extend(
        [
            root / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_item_names.json",
            root / "resources" / "data" / "decoded" / "eqlwiki_item_names.json",
            root / "data" / "decoded" / "eqlwiki_item_names.json",
            Path(__file__).resolve().parents[2] / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_item_names.json",
            Path(__file__).resolve().parents[2] / "resources" / "data" / "decoded" / "eqlwiki_item_names.json",
            Path(__file__).resolve().parents[1] / "resources" / "data" / "decoded" / "eqlwiki_item_names.json",
        ]
    )
    # Also walk sibling decoded dirs when EQ_DATA_ROOT points at a thin tree.
    if decoded and decoded.is_dir():
        for sibling in (
            decoded.parent / "decoded" / "eqlwiki_item_names.json",
            decoded.parent.parent / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_item_names.json",
            decoded.parent.parent / "resources" / "data" / "decoded" / "eqlwiki_item_names.json",
        ):
            candidates.append(sibling)
    seen: set[str] = set()
    raw = None
    used = None
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        loaded = _load_json(path)
        if isinstance(loaded, dict) and isinstance(loaded.get("names"), list) and loaded.get("names"):
            raw = loaded
            used = path
            break
    names = (raw or {}).get("names") if isinstance(raw, dict) else None
    if not isinstance(names, list):
        return out
    for name in names:
        if not isinstance(name, str):
            continue
        display = name.strip()
        key = _name_key(display)
        if key and key not in out:
            out[key] = display
    if used:
        out["__index_path__"] = str(used)  # type: ignore[assignment]
    return out


def _wiki_display_names() -> dict[str, str]:
    """Wiki name index without internal meta keys."""
    return {k: v for k, v in _wiki_name_index().items() if not str(k).startswith("__")}


@lru_cache(maxsize=1)
def _hub_quest_names() -> dict[str, str]:
    """Canonical Quest Hub names keyed for matching wiki/catalog quest labels."""
    try:
        from . import quest_hub as qh
        rows = qh.list_quests()
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in rows or []:
        name = (row.get("name") if isinstance(row, dict) else "") or ""
        name = str(name).strip()
        if not name:
            continue
        key = _name_key(name)
        if key and key not in out:
            out[key] = name
    return out


@lru_cache(maxsize=1)
def _catalog_reward_quests_by_item() -> dict[str, list[str]]:
    """item_key → quest names that list this item as a decoded catalog reward."""
    out: dict[str, list[str]] = {}
    try:
        decoded = decoded_dir()
        catalog = _load_json(decoded / "catalog.json")
    except Exception:
        return out
    if not isinstance(catalog, dict):
        return out

    def add(item_name: str, quest_name: str) -> None:
        ik = _name_key(item_name)
        qn = (quest_name or "").strip()
        if not ik or not qn:
            return
        bucket = out.setdefault(ik, [])
        if qn not in bucket:
            bucket.append(qn)

    for kind in (
        "tooltips",
        "focusItemTooltips",
        "clickyItemTooltips",
        "wornItemTooltips",
        "procItemTooltips",
    ):
        tip_map = catalog.get(kind) or {}
        if not isinstance(tip_map, dict):
            continue
        for tip in tip_map.values():
            if not isinstance(tip, dict):
                continue
            item = (tip.get("name") or "").strip()
            for q in tip.get("rewardFromQuests") or []:
                if isinstance(q, str):
                    add(item, q)
    return out


def _quests_payload_for_item(
    item_name: str,
    *,
    extra_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Deduped quest rows for an item, marked when present in Quest Hub."""
    hub = _hub_quest_names()
    catalog_names = list(_catalog_reward_quests_by_item().get(_name_key(item_name), []) or [])
    names: list[str] = []
    for q in catalog_names:
        names.append(q)
    for q in extra_names or []:
        if q:
            names.append(str(q).strip())
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    def add_row(raw: str, *, source: str) -> None:
        name = (raw or "").strip()
        if not name:
            return
        key = _name_key(name)
        if not key or key in seen:
            return
        hub_name = hub.get(key)
        # Soft match: "Foo Quests" wiki category → hub quest named "Foo" when present.
        if not hub_name and key.endswith(" quests"):
            base = name
            for suffix in (" Quests", " Quest", " quests", " quest"):
                if name.endswith(suffix):
                    base = name[: -len(suffix)].strip()
                    break
            hub_name = hub.get(_name_key(base))
        in_hub = bool(hub_name)
        seen.add(key)
        if hub_name:
            seen.add(_name_key(hub_name))
        rows.append({
            "name": hub_name or name,
            "mentioned_as": name if hub_name and _name_key(hub_name) != key else None,
            "in_hub": in_hub,
            "source": source,
        })

    for q in catalog_names:
        add_row(q, source="catalog")
    for q in extra_names or []:
        if q:
            add_row(str(q).strip(), source="eqlwiki")
    return rows


def catalog_match(name: str, *, item_id: str | int | None = None) -> dict[str, Any]:
    """Resolve an inventory name/id against tools catalog + eqlwiki name index.

    Never invents stats. ``source`` is ``tools`` (has decoded stats when present),
    ``eqlwiki`` (name known from wiki category dump), or None.
    """
    key = _name_key(name)
    iid = str(item_id).strip() if item_id is not None and str(item_id).strip() else ""
    try:
        by_name = _flat_by_name()
        by_id = _flat_by_id()
        wiki = _wiki_display_names()
    except Exception:
        by_name, by_id, wiki = {}, {}, {}

    it = by_name.get(key) if key else None
    if it is None and iid:
        it = by_id.get(iid)
    if it is not None:
        s0 = it.get("stats_plus0") or {}
        s10 = it.get("stats_plus10") or {}
        return {
            "matched": True,
            "source": "tools",
            "has_stats": bool(s0 or s10),
            "name": it.get("name") or name,
            "itemID": it.get("itemID"),
        }
    if key and key in wiki and not str(key).startswith("__"):
        return {
            "matched": True,
            "source": "eqlwiki",
            "has_stats": False,
            "name": wiki[key],
            "itemID": None,
        }
    return {
        "matched": False,
        "source": None,
        "has_stats": False,
        "name": (name or "").strip() or None,
        "itemID": None,
    }


def get_item_by_name(name: str, *, enrich: bool = True) -> dict[str, Any] | None:
    """Return a public item row. Optionally enrich wiki-only rows from eqlwiki HTML."""
    key = _name_key(name)
    if not key:
        return None
    try:
        it = _flat_by_name().get(key)
    except Exception:
        it = None
    if not it:
        # Last chance: wiki name index alone (before pool rebuild)
        try:
            display = _wiki_name_index().get(key)
        except Exception:
            display = None
        if not display:
            return None
        title = display.replace(" ", "_")
        wiki_url = f"https://eqlwiki.com/{urllib.parse.quote(title)}"
        it = {
            "name": display,
            "slots": [],
            "classes": [],
            "stats_plus0": {},
            "stats_plus10": {},
            "tooltipLines": [],
            "url": wiki_url,
            "sourceUrl": wiki_url,
            "catalog_source": "eqlwiki",
            "has_stats": False,
        }
    try:
        pub = _public_item(it)
    except Exception:
        return None
    if not enrich:
        # Still attach catalog quest rewards even without wiki fetch.
        if not pub.get("quests"):
            pub["quests"] = _quests_payload_for_item(pub.get("name") or name)
        return pub
    needs = (
        pub.get("catalog_source") == "eqlwiki"
        or not (pub.get("tooltipLines") or [])
        or not (pub.get("stats_plus0") or pub.get("stats_plus10"))
        or not (pub.get("quests") or [])
    )
    if not needs:
        if not pub.get("quests"):
            pub["quests"] = _quests_payload_for_item(pub.get("name") or name)
        return pub
    try:
        extra = _enrich_item_from_eqlwiki(pub.get("name") or name)
    except Exception:
        extra = None
    if not extra:
        if not pub.get("quests"):
            pub["quests"] = _quests_payload_for_item(pub.get("name") or name)
        return pub
    # Fill gaps only — never overwrite real tools stats with empty wiki parses.
    merged = dict(pub)
    if extra.get("tooltipLines") and not merged.get("tooltipLines"):
        merged["tooltipLines"] = extra["tooltipLines"]
    elif extra.get("tooltipLines") and merged.get("catalog_source") == "eqlwiki":
        merged["tooltipLines"] = extra["tooltipLines"]
    if extra.get("description") and not merged.get("description"):
        merged["description"] = extra["description"]
    if extra.get("stats_plus0") and not (merged.get("stats_plus0") or {}):
        merged["stats_plus0"] = extra["stats_plus0"]
        merged["stats_plus10"] = extra.get("stats_plus10") or _scale_stats_plus10(extra["stats_plus0"])
    if extra.get("slots") and not merged.get("slots"):
        merged["slots"] = extra["slots"]
    if extra.get("classes") and not merged.get("classes"):
        merged["classes"] = extra["classes"]
        merged["classes_str"] = ", ".join(extra["classes"])
    if extra.get("zone") and not merged.get("zone"):
        merged["zone"] = extra["zone"]
    if extra.get("url") and not merged.get("url"):
        merged["url"] = extra["url"]
    merged["quests"] = _quests_payload_for_item(
        merged.get("name") or name,
        extra_names=list(extra.get("related_quests") or []),
    )
    merged["has_stats"] = bool(merged.get("stats_plus0") or merged.get("stats_plus10") or merged.get("tooltipLines"))
    merged["catalog_source"] = merged.get("catalog_source") or extra.get("catalog_source") or "eqlwiki"
    merged["wiki_enriched"] = True
    return merged


def name_in_catalog(name: str, item_id: str | int | None = None) -> bool:
    """True if name/id is known from tools catalog or eqlwiki item names."""
    try:
        return bool(catalog_match(name, item_id=item_id).get("matched"))
    except Exception:
        return False


def catalog_coverage() -> dict[str, Any]:
    """Sizes for UI notes — tools items vs eqlwiki name index."""
    try:
        tools_n = sum(
            1 for it in _all_flat_items()
            if (it.get("catalog_source") or "tools") == "tools"
        )
    except Exception:
        tools_n = 0
    try:
        wiki_n = len(_wiki_display_names())
    except Exception:
        wiki_n = 0
    try:
        total_n = len(_all_flat_items())
    except Exception:
        total_n = 0
    return {
        "tools_items": tools_n,
        "eqlwiki_names": wiki_n,
        "search_catalog": total_n,
        "index_path": (_wiki_name_index().get("__index_path__") if isinstance(_wiki_name_index(), dict) else "") or "",
        "note": (
            "Item Search covers tools stats plus every eqlwiki item name "
            "(equipable and non-equipable). Stats come from decoded data or the wiki page only."
        ),
    }


def _wiki_item_cache_dir() -> Path:
    return APP_ROOT / "data" / "eqlwiki-item-cache"


def _wiki_item_cache_path(name: str) -> Path:
    return _wiki_item_cache_dir() / f"{_slug(name)}.json"


def _load_wiki_item_cache(name: str) -> dict[str, Any] | None:
    path = _wiki_item_cache_path(name)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_wiki_item_cache(name: str, payload: dict[str, Any]) -> None:
    try:
        d = _wiki_item_cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        _wiki_item_cache_path(name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _html_fragment_to_lines(fragment: str) -> list[str]:
    t = fragment or ""
    t = re.sub(r"<script[\s\S]*?</script>", " ", t, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<div class=\"itemicon\"[\s\S]*?</div>", " ", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p\s*>", "\n", t, flags=re.I)
    t = re.sub(r"</li\s*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    try:
        import html as _html
        t = _html.unescape(t)
    except Exception:
        pass
    lines: list[str] = []
    for line in t.splitlines():
        s = re.sub(r"\s+", " ", line).strip()
        if s:
            lines.append(s)
    return lines


def _parse_eqlwiki_item_html(html: str, name: str) -> dict[str, Any] | None:
    """Extract real tooltip/description lines from an eqlwiki item page — never invent."""
    if not html or "does not exist" in html.lower() and "create the page" in html.lower():
        return None
    tip_lines: list[str] = []
    m = re.search(
        r'<div class="itemdata">(.*?)</div>\s*</div>\s*<div class="itembotbg"',
        html,
        re.I | re.S,
    )
    if m:
        tip_lines.extend(_html_fragment_to_lines(m.group(1)))
    # Short blurb after the item box (before Drops From / Sold by / next heading).
    desc_lines: list[str] = []
    m2 = re.search(
        r'<div class="itembotbg"></div>\s*(.*?)(?:<div class="mw-heading"|<h2\b)',
        html,
        re.I | re.S,
    )
    if m2:
        desc_lines.extend(_html_fragment_to_lines(m2.group(1)))
    if not tip_lines and not desc_lines:
        return None
    stats0 = _parse_tip_stats(tip_lines)
    slots, classes = _slots_classes_from_lines(tip_lines)
    zone = ""
    drops = re.search(
        r'<h2[^>]*>\s*Drops From\s*</h2>\s*<p>(.*?)</p>',
        html,
        re.I | re.S,
    )
    if drops:
        zlines = _html_fragment_to_lines(drops.group(1))
        if zlines:
            zone = zlines[0][:120]

    related_quests: list[str] = []
    m_q = re.search(
        r'id="Related_quests"[^>]*>[\s\S]*?</h2>\s*</div>\s*(<ul[\s\S]*?</ul>)',
        html,
        re.I,
    )
    if not m_q:
        m_q = re.search(
            r'(?:Related quests|Related Quests)</(?:span|h2)>[\s\S]*?(<ul[\s\S]*?</ul>)',
            html,
            re.I,
        )
    if m_q:
        for title in re.findall(r'title="([^"]+)"', m_q.group(1)):
            try:
                import html as _html
                title = _html.unescape(title)
            except Exception:
                pass
            title = title.strip()
            if title and title not in related_quests:
                related_quests.append(title)

    title = (name or "").replace(" ", "_")
    url = f"https://eqlwiki.com/{urllib.parse.quote(title)}"
    all_lines = list(tip_lines)
    for line in desc_lines:
        if line not in all_lines:
            all_lines.append(line)
    return {
        "name": name,
        "tooltipLines": all_lines[:80],
        "description": "\n".join(desc_lines[:20]),
        "stats_plus0": stats0,
        "stats_plus10": _scale_stats_plus10(stats0) if stats0 else {},
        "slots": slots,
        "classes": classes,
        "zone": zone,
        "related_quests": related_quests,
        "url": url,
        "sourceUrl": url,
        "catalog_source": "eqlwiki",
        "has_stats": bool(stats0) or bool(all_lines),
    }


def _enrich_item_from_eqlwiki(name: str) -> dict[str, Any] | None:
    """Load cached eqlwiki item parse or fetch the page once."""
    cached = _load_wiki_item_cache(name)
    # Older caches lack related_quests — re-fetch so Item Search can list quests.
    if cached and "related_quests" in cached and (
        cached.get("tooltipLines") or cached.get("description") or cached.get("related_quests") is not None
    ):
        return cached
    stub = {"name": name, "url": "", "sourceUrl": ""}
    title = (name or "").replace(" ", "_")
    stub["url"] = f"https://eqlwiki.com/{urllib.parse.quote(title)}"
    for url in _wiki_urls_for_item(stub):
        blob = _http_get(url, timeout=25.0)
        if not blob:
            continue
        try:
            html = blob.decode("utf-8", errors="ignore")
        except Exception:
            continue
        parsed = _parse_eqlwiki_item_html(html, name)
        if not parsed:
            continue
        parsed["source"] = url
        _write_wiki_item_cache(name, parsed)
        return parsed
    return cached


def _public_item(it: dict[str, Any]) -> dict[str, Any]:
    name = it.get("name") or ""
    local = None
    has_local = False
    try:
        local = local_image_path(name)
        has_local = bool(local and local.is_file())
    except Exception:
        local = None
        has_local = False
    try:
        image_url = f"/api/item-image?name={urllib.parse.quote(name)}" if name else ""
    except Exception:
        image_url = ""
    return {
        "name": name,
        "itemID": it.get("itemID"),
        "slots": it.get("slots") or [],
        "slot": it.get("slot") or "",
        "classes": it.get("classes") or [],
        "classes_str": it.get("classes_str") or ", ".join(it.get("classes") or []),
        "zone": it.get("zone") or "",
        "drops_mobs": it.get("drops_mobs") or "",
        "quest_source": it.get("quest_source") or it.get("source") or "",
        "url": it.get("url") or "",
        "sourceUrl": it.get("sourceUrl") or "",
        "zamUrl": it.get("zamUrl") or "",
        "stats_plus0": it.get("stats_plus0") or {},
        "stats_plus10": it.get("stats_plus10") or {},
        "ratio_plus0": it.get("ratio_plus0"),
        "ratio_plus10": it.get("ratio_plus10"),
        "tooltipLines": it.get("tooltipLines") or [],
        "description": it.get("description") or "",
        "quests": it.get("quests") or [],
        "image_url": image_url,
        "has_local_image": has_local,
        "catalog_source": it.get("catalog_source") or "tools",
        "has_stats": bool(
            it.get("has_stats")
            or it.get("stats_plus0")
            or it.get("stats_plus10")
            or it.get("tooltipLines")
        ),
    }


def _safe_resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except Exception:
        return p


def _find_image_file(name: str, directories: list[Path]) -> Path | None:
    slug = _slug(name)
    for img_dir in directories:
        try:
            for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                p = img_dir / f"{slug}{ext}"
                if p.is_file() and p.stat().st_size > 0:
                    return p
        except Exception:
            continue
    return None


def local_image_path(name: str) -> Path | None:
    """Prefer writable cache, then bundled/seed dirs."""
    try:
        img_dir = _images_dir()
    except Exception:
        img_dir = None
    dirs: list[Path] = []
    if img_dir is not None:
        try:
            img_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        dirs.append(img_dir)
    try:
        for seed in image_seed_dirs():
            if img_dir is None or _safe_resolve(seed) != _safe_resolve(img_dir):
                dirs.append(seed)
    except Exception:
        pass
    return _find_image_file(name, dirs)


def _copy_seed_into_cache(name: str) -> Path | None:
    """If icon exists only in a bundled seed dir, copy into writable cache."""
    img_dir = _images_dir()
    existing = _find_image_file(name, [img_dir])
    if existing:
        return existing
    seed_hit = _find_image_file(name, image_seed_dirs())
    if not seed_hit:
        return None
    try:
        img_dir.mkdir(parents=True, exist_ok=True)
        dest = img_dir / seed_hit.name
        if not dest.exists() or dest.stat().st_size == 0:
            dest.write_bytes(seed_hit.read_bytes())
        return dest if dest.is_file() and dest.stat().st_size > 0 else seed_hit
    except Exception:
        return seed_hit


def _ssl_context():
    try:
        import ssl
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            import ssl

            return ssl.create_default_context()
        except Exception:
            return None


def _http_get(url: str, timeout: float = 20.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    ctx = _ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def _wiki_urls_for_item(it: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("sourceUrl", "url"):
        u = (it.get(key) or "").strip()
        if u.startswith("http") and "eqlwiki" in u:
            urls.append(u)
    name = it.get("name") or ""
    if name:
        title = name.replace(" ", "_")
        for host in ("https://eqlwiki.com", "https://eqlwiki.org"):
            urls.append(f"{host}/{urllib.parse.quote(title)}")
            urls.append(f"{host}/{urllib.parse.quote(name)}")
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# eqlwiki icons live under hashed dirs, e.g. /images/6/61/Item_641.png
_IMG_RE = re.compile(
    r"(?:src|content)=[\"']((?:https?://[^\"']+)?/images/[^\"']+\.(?:png|jpg|jpeg|webp|gif))[\"']",
    re.I,
)
_ITEM_IMG_RE = re.compile(
    r"(?:https?://eqlwiki\.(?:com|org))?(/images/(?:[A-Za-z0-9._~-]+/)+Item_\d+\.(?:png|gif|jpe?g|webp))",
    re.I,
)


def _pick_wiki_image(html: str) -> str | None:
    # Prefer Item_### icon assets
    for m in _ITEM_IMG_RE.findall(html or ""):
        path = m if m.startswith("http") else f"https://eqlwiki.com{m if m.startswith('/') else '/' + m}"
        return path
    for m in _IMG_RE.findall(html or ""):
        url = m
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://eqlwiki.com" + url
        # skip logos
        if "logo" in url.lower() or "wiki" in url.lower() and "item" not in url.lower():
            continue
        if "/thumb/" in url and "Item_" not in url:
            continue
        return url
    return None


def _normalize_image_blob(blob: bytes, ext: str) -> bytes:
    """Re-encode icons to 8-bit PNG/JPEG so Chromium can display them.

    eqlwiki Item_### assets are often 16-bit RGBA PNGs; browsers leave those blank.
    """
    if not blob:
        return blob
    try:
        from PIL import Image
        import io

        im = Image.open(io.BytesIO(blob))
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in (im.mode or "") or im.mode == "P" else "RGB")
        # Force 8-bit channels via a fresh RGBA/RGB canvas
        if im.mode == "RGBA":
            out_im = Image.new("RGBA", im.size)
            out_im.paste(im, (0, 0))
        else:
            out_im = Image.new("RGB", im.size)
            out_im.paste(im.convert("RGB"), (0, 0))
        buf = io.BytesIO()
        if ext in (".jpg", ".jpeg"):
            out_im.convert("RGB").save(buf, format="JPEG", quality=92)
        else:
            out_im.save(buf, format="PNG", optimize=True)
        return buf.getvalue() or blob
    except Exception:
        return blob


def ensure_item_image(name: str, *, fetch: bool = True) -> dict[str, Any]:
    """Return local image path info; optionally fetch from eqlwiki and save."""
    with _lock_for(name):
        return _ensure_item_image_unlocked(name, fetch=fetch)


def _ensure_item_image_unlocked(name: str, *, fetch: bool = True) -> dict[str, Any]:
    img_dir = _images_dir()
    try:
        img_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # Still allow serving from read-only seed if present.
        seeded = _find_image_file(name, image_seed_dirs())
        if seeded:
            return {
                "name": name,
                "cached": True,
                "path": str(seeded),
                "url": f"/api/item-image?name={urllib.parse.quote(name)}",
                "images_dir": str(img_dir),
                "seed": True,
            }
        return {
            "name": name,
            "cached": False,
            "path": None,
            "url": None,
            "error": f"image cache not writable ({img_dir}): {e}",
            "images_dir": str(img_dir),
        }

    def _path_out(p: Path) -> str:
        try:
            return str(p.relative_to(APP_ROOT))
        except Exception:
            return str(p)

    existing = _copy_seed_into_cache(name) or local_image_path(name)
    if existing:
        # Re-encode legacy 16-bit wiki PNGs already on disk (Chromium blank otherwise).
        try:
            raw = existing.read_bytes()
            if existing.suffix.lower() == ".png" and len(raw) > 25 and raw[24] == 16:
                fixed = _normalize_image_blob(raw, ".png")
                if fixed and fixed != raw:
                    try:
                        existing.write_bytes(fixed)
                    except Exception:
                        # Seed may be read-only — write fixed copy into writable cache.
                        dest = img_dir / f"{_slug(name)}.png"
                        dest.write_bytes(fixed)
                        existing = dest
        except Exception:
            pass
        return {
            "name": name,
            "cached": True,
            "path": _path_out(existing),
            "url": f"/api/item-image?name={urllib.parse.quote(name)}",
            "images_dir": str(img_dir),
        }
    if not fetch:
        return {
            "name": name,
            "cached": False,
            "path": None,
            "url": None,
            "error": "not cached",
            "images_dir": str(img_dir),
        }

    it = None
    key = (name or "").strip().lower()
    for row in _all_flat_items():
        if (row.get("name") or "").strip().lower() == key:
            it = row
            break
    if not it:
        # Still try a bare wiki title lookup so BiS names outside flats can resolve.
        it = {"name": name}

    img_url = None
    wiki_tried = 0
    last_http_err = None
    for wiki in _wiki_urls_for_item(it):
        wiki_tried += 1
        html_b = _http_get(wiki)
        if not html_b:
            last_http_err = f"http failed: {wiki}"
            continue
        try:
            html = html_b.decode("utf-8", errors="ignore")
        except Exception:
            continue
        img_url = _pick_wiki_image(html)
        if img_url:
            break
    if not img_url:
        return {
            "name": name,
            "cached": False,
            "path": None,
            "url": None,
            "error": "no wiki image found",
            "wiki_tried": wiki_tried,
            "last_http_err": last_http_err,
            "images_dir": str(img_dir),
        }

    blob = _http_get(img_url)
    if not blob:
        return {
            "name": name,
            "cached": False,
            "path": None,
            "url": None,
            "error": f"failed download {img_url}",
            "images_dir": str(img_dir),
        }

    ext = ".png"
    low = img_url.lower()
    for e in (".jpg", ".jpeg", ".webp", ".gif", ".png"):
        if e in low:
            ext = e if e != ".jpeg" else ".jpg"
            break
    # Always store browser-safe 8-bit PNG for wiki icons (gif/webp → png).
    if ext in (".gif", ".webp", ".png"):
        ext = ".png"
        blob = _normalize_image_blob(blob, ".png")
    elif ext in (".jpg", ".jpeg"):
        blob = _normalize_image_blob(blob, ".jpg")
    dest = img_dir / f"{_slug(name)}{ext}"
    try:
        dest.write_bytes(blob)
    except Exception as e:
        return {
            "name": name,
            "cached": False,
            "path": None,
            "url": None,
            "error": f"failed write {dest}: {e}",
            "images_dir": str(img_dir),
        }
    return {
        "name": name,
        "cached": True,
        "fetched": True,
        "source": img_url,
        "path": _path_out(dest),
        "url": f"/api/item-image?name={urllib.parse.quote(name)}",
        "images_dir": str(img_dir),
    }
