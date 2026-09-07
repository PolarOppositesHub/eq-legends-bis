"""Item catalog search + image cache (eqlwiki / local).

Looks up item icons from eqlwiki when missing and saves under data/item-images/
for reuse across BiS, Simulator, and Item Search. Never invents item stats.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import APP_ROOT, decoded_dir

IMAGES_DIR = APP_ROOT / "data" / "item-images"
USER_AGENT = "EQLegendsBiS/1.0.4 (local; josh; item-icon-cache)"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-").lower()
    return s or "item"


def _merge_row(by_name: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    name = (row.get("name") or "").strip()
    if not name:
        return
    key = name.lower()
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
    for fld in ("url", "sourceUrl", "zamUrl", "zone", "itemID", "classes_str"):
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


@lru_cache(maxsize=1)
def _all_flat_items() -> list[dict[str, Any]]:
    """Union of flat_* + aggregate + catalog.json (weapons/focus/clickies/worn/proc)."""
    decoded = decoded_dir()
    by_name: dict[str, dict[str, Any]] = {}
    for path in sorted(decoded.glob("flat_*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            _merge_row(by_name, row)
    agg = decoded / "aggregate.json"
    if agg.is_file():
        try:
            rows = json.loads(agg.read_text(encoding="utf-8"))
        except Exception:
            rows = []
        for row in rows if isinstance(rows, list) else []:
            name = (row.get("name") or "").strip()
            if not name:
                continue
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
    cat_path = decoded / "catalog.json"
    if cat_path.is_file():
        try:
            catalog = json.loads(cat_path.read_text(encoding="utf-8"))
        except Exception:
            catalog = {}
        for w in catalog.get("weapons") or []:
            norm = _weapon_row_from_catalog(w)
            if norm:
                _merge_row(by_name, norm)
        for w in catalog.get("proc") or []:
            norm = _weapon_row_from_catalog(w)
            if norm:
                _merge_row(by_name, norm)
        for kind in ("focus", "bardResonance", "clickies", "worn"):
            for row in catalog.get(kind) or []:
                norm = _named_catalog_row(row if isinstance(row, dict) else {}, kind=kind)
                if norm:
                    _merge_row(by_name, norm)
    return list(by_name.values())


def search_items(
    q: str = "",
    *,
    slot: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    qn = (q or "").strip().lower()
    slot_u = (slot or "").strip().upper() or None
    hits: list[dict[str, Any]] = []
    for it in _all_flat_items():
        name = it.get("name") or ""
        if qn and qn not in name.lower():
            # also match classes_str
            blob = f"{name} {it.get('classes_str') or ''} {it.get('zone') or ''}".lower()
            if qn not in blob:
                continue
        if slot_u:
            slots = {str(s).upper() for s in (it.get("slots") or [])}
            slot_field = str(it.get("slot") or "").upper()
            if slot_u not in slots and slot_u not in slot_field.replace("/", " ").split():
                # EAR matches EAR1 etc loosely
                if not any(slot_u in str(s).upper() for s in slots) and slot_u not in slot_field:
                    continue
        hits.append(_public_item(it))
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
        "catalog_size": len(_all_flat_items()),
    }


def get_item_by_name(name: str) -> dict[str, Any] | None:
    key = (name or "").strip().lower()
    if not key:
        return None
    for it in _all_flat_items():
        if (it.get("name") or "").strip().lower() == key:
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
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    existing = local_image_path(name)
    if existing:
        # Re-encode legacy 16-bit wiki PNGs already on disk (Chromium blank otherwise).
        try:
            raw = existing.read_bytes()
            if existing.suffix.lower() == ".png" and len(raw) > 25 and raw[24] == 16:
                fixed = _normalize_image_blob(raw, ".png")
                if fixed and fixed != raw:
                    existing.write_bytes(fixed)
        except Exception:
            pass
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
    # Always store browser-safe 8-bit PNG for wiki icons (gif/webp → png).
    if ext in (".gif", ".webp", ".png"):
        ext = ".png"
        blob = _normalize_image_blob(blob, ".png")
    elif ext in (".jpg", ".jpeg"):
        blob = _normalize_image_blob(blob, ".jpg")
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
