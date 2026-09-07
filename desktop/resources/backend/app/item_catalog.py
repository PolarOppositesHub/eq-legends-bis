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

from .paths import APP_ROOT, decoded_dir

IMAGES_DIR = APP_ROOT / "data" / "item-images"
USER_AGENT = "EQLegendsBiS/1.0.6 (local; josh; item-icon-cache)"

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


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-").lower()
    return s or "item"


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
            # "Drops From: Zone: mob"
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
    # Prefer explicit stats dict when present (already decoded) — still real data only
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
    """Casefold + normalize curly/backtick apostrophes for dedupe."""
    s = (name or "").strip().lower()
    for ch in ("\u2019", "\u2018", "`", "\u02bc"):
        s = s.replace(ch, "'")
    return s


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
    if not decoded.exists():
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
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": q,
        "slot": slot_u,
        "items": page,
        "catalog_size": len(pool),
        "decoded_dir": str(decoded_dir()),
        "warning": None if pool else "Item catalog empty — decoded data missing or unreadable.",
    }


def get_item_by_name(name: str) -> dict[str, Any] | None:
    key = _name_key(name)
    if not key:
        return None
    try:
        pool = _all_flat_items()
    except Exception:
        return None
    for it in pool:
        if _name_key(it.get("name") or "") == key:
            return _public_item(it)
    return None


def _public_item(it: dict[str, Any]) -> dict[str, Any]:
    name = it.get("name") or ""
    local = local_image_path(name)
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
        "image_url": f"/api/item-image?name={urllib.parse.quote(name)}" if local or True else "",
        "has_local_image": local is not None and local.is_file(),
    }


def local_image_path(name: str) -> Path | None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        p = IMAGES_DIR / f"{_slug(name)}{ext}"
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def _http_get(url: str, timeout: float = 20.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


def _wiki_urls_for_item(it: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("sourceUrl", "url"):
        u = (it.get(key) or "").strip()
        if u.startswith("http") and "eqlwiki" in u:
            urls.append(u)
    name = it.get("name") or ""
    if name:
        # Classic wiki title form
        title = name.replace(" ", "_")
        urls.append(f"https://eqlwiki.com/{urllib.parse.quote(title)}")
        urls.append(f"https://eqlwiki.com/{urllib.parse.quote(name)}")
    # dedupe
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


_IMG_RE = re.compile(
    r"(?:src|content)=[\"']([^\"']+/images/[^\"']+\.(?:png|jpg|jpeg|webp|gif))[\"']",
    re.I,
)
_ITEM_IMG_RE = re.compile(r"/images/[a-z0-9]/f]/[A-Za-z0-9._-]*Item_[^\"'\s>]+\.(?:png|jpg|jpeg|webp)", re.I)


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


def ensure_item_image(name: str, *, fetch: bool = True) -> dict[str, Any]:
    """Return local image path info; optionally fetch from eqlwiki and save."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    existing = local_image_path(name)
    if existing:
        return {
            "name": name,
            "cached": True,
            "path": str(existing.relative_to(APP_ROOT)),
            "url": f"/api/item-image?name={urllib.parse.quote(name)}",
        }
    if not fetch:
        return {"name": name, "cached": False, "path": None, "url": None, "error": "not cached"}

    it = None
    key = (name or "").strip().lower()
    for row in _all_flat_items():
        if (row.get("name") or "").strip().lower() == key:
            it = row
            break
    if not it:
        return {"name": name, "cached": False, "path": None, "url": None, "error": "item not in catalog"}

    img_url = None
    for wiki in _wiki_urls_for_item(it):
        html_b = _http_get(wiki)
        if not html_b:
            continue
        try:
            html = html_b.decode("utf-8", errors="ignore")
        except Exception:
            continue
        img_url = _pick_wiki_image(html)
        if img_url:
            break
    if not img_url:
        return {"name": name, "cached": False, "path": None, "url": None, "error": "no wiki image found"}

    blob = _http_get(img_url)
    if not blob:
        return {"name": name, "cached": False, "path": None, "url": None, "error": f"failed download {img_url}"}

    ext = ".png"
    low = img_url.lower()
    for e in (".jpg", ".jpeg", ".webp", ".gif", ".png"):
        if e in low:
            ext = e if e != ".jpeg" else ".jpg"
            break
    dest = IMAGES_DIR / f"{_slug(name)}{ext}"
    dest.write_bytes(blob)
    return {
        "name": name,
        "cached": True,
        "fetched": True,
        "source": img_url,
        "path": str(dest.relative_to(APP_ROOT)),
        "url": f"/api/item-image?name={urllib.parse.quote(name)}",
    }
