"""Mobs hub: eqlwiki NPC index + on-demand page detail + catalog drop reverse-index.

Mob names and kinds come from decoded/eqlwiki_mob_names.json (eqlwiki categories).
Detail fields are parsed from the real eqlwiki page when available — never invented.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import APP_ROOT, decoded_dir

USER_AGENT = "EQ-Legends-BiS/1.0.12 (local; mobs-hub)"
KINDS = ("raid", "mini_boss", "named", "standard", "merchant")
KIND_LABELS = {
    "raid": "Raid",
    "mini_boss": "Mini Boss",
    "named": "Named",
    "standard": "Standard",
    "merchant": "Merchant",
}
# Filter buckets shown in the UI. Raw index may also store fear/hate/sky.
ERA_FILTERS = ("classic", "kunark", "velious", "planes", "untagged")
ERA_LABELS = {
    "classic": "Classic",
    "kunark": "Kunark",
    "velious": "Velious",
    "planes": "Planes (Fear / Hate / Sky)",
    "untagged": "No era tag",
}
_PLANE_ERAS = frozenset({"fear", "hate", "sky"})


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_PLACEHOLDER_MOBS = frozenset({
    "various mobs",
    "class-specific mini-bosses",
    "class specific mini-bosses",
    "trash",
    "unknown",
})


def _name_key(name: str) -> str:
    s = (name or "").strip().lower()
    for ch in ("\u2019", "\u2018", "`", "\u02bc"):
        s = s.replace(ch, "'")
    return s


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@lru_cache(maxsize=1)
def _mob_index_payload() -> dict[str, Any]:
    """Load eqlwiki_mob_names.json from any known decoded / resources location."""
    candidates: list[Path] = []
    try:
        decoded = decoded_dir()
        candidates.append(decoded / "eqlwiki_mob_names.json")
    except Exception:
        decoded = None
    root = APP_ROOT
    candidates.extend(
        [
            root / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
            root / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
            root / "data" / "decoded" / "eqlwiki_mob_names.json",
            Path(__file__).resolve().parents[2] / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
            Path(__file__).resolve().parents[2] / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
            Path(__file__).resolve().parents[1] / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
        ]
    )
    # Also walk sibling decoded dirs when EQ_DATA_ROOT points at a thin tree.
    if decoded and decoded.is_dir():
        for sibling in (
            decoded.parent / "decoded" / "eqlwiki_mob_names.json",
            decoded.parent.parent / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
            decoded.parent.parent / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
        ):
            candidates.append(sibling)

    seen: set[str] = set()
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
        raw = _load_json(path)
        if isinstance(raw, dict) and isinstance(raw.get("mobs"), list) and raw.get("mobs"):
            out = dict(raw)
            out["_index_path"] = str(path)
            return out

    return {
        "mobs": [],
        "counts": {},
        "note": (
            "eqlwiki_mob_names.json missing from decoded data — "
            "run scripts/refresh_eqlwiki_mob_names.py and ensure the file ships in resources/data/decoded."
        ),
        "warning": "mob index file not found",
    }


@lru_cache(maxsize=1)
def list_mobs() -> list[dict[str, Any]]:
    payload = _mob_index_payload()
    rows = payload.get("mobs") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        kinds = [k for k in (row.get("kinds") or []) if k in KINDS]
        eras = [e for e in (row.get("eras") or []) if isinstance(e, str) and e.strip()]
        out.append({
            "name": name,
            "kinds": kinds,
            "primary_kind": kinds[0] if kinds else "named",
            "eras": eras,
            "wiki_categories": list(row.get("wiki_categories") or []),
            "url": row.get("url") or _wiki_url(name),
        })
    out.sort(key=lambda r: (r["name"] or "").lower())
    return out


def _wiki_url(name: str) -> str:
    return f"https://eqlwiki.com/{urllib.parse.quote((name or '').replace(' ', '_'))}"


def _era_match(eras: list[str], era_f: str | None) -> bool:
    """True if row passes the era filter bucket."""
    if not era_f:
        return True
    if era_f == "untagged":
        return not eras
    if era_f == "planes":
        return any(e in _PLANE_ERAS for e in eras)
    return era_f in eras


def search_mobs(
    q: str = "",
    *,
    kind: str | None = None,
    era: str | None = None,
    limit: int = 120,
    offset: int = 0,
) -> dict[str, Any]:
    qn = (q or "").strip().lower()
    kind_f = (kind or "").strip().lower() or None
    if kind_f in ("", "all", "any"):
        kind_f = None
    if kind_f == "mini":
        kind_f = "mini_boss"
    if kind_f and kind_f not in KINDS:
        kind_f = None

    era_f = (era or "").strip().lower() or None
    if era_f in ("", "all", "any"):
        era_f = None
    if era_f and era_f not in ERA_FILTERS:
        era_f = None

    pool = list_mobs()
    hits: list[dict[str, Any]] = []
    for row in pool:
        kinds = row.get("kinds") or []
        eras = list(row.get("eras") or [])
        # Default list hides merchants unless explicitly filtered or searched.
        if kind_f:
            if kind_f not in kinds:
                continue
        elif "merchant" in kinds and not any(k in kinds for k in ("raid", "mini_boss", "named", "standard")):
            if not qn:
                continue
        if not _era_match(eras, era_f):
            continue
        if qn:
            era_blob = " ".join(eras)
            if any(e in _PLANE_ERAS for e in eras):
                era_blob = f"{era_blob} planes"
            blob = f"{row.get('name') or ''} {' '.join(kinds)} {era_blob}".lower()
            if qn not in blob and not all(t in blob for t in qn.split() if t):
                # token AND match
                tokens = [t for t in re.split(r"[^a-z0-9']+", qn) if t]
                name_l = (row.get("name") or "").lower()
                if not tokens or not all(t in name_l for t in tokens):
                    continue
        era_labels = []
        for e in eras:
            if e in _PLANE_ERAS:
                if ERA_LABELS["planes"] not in era_labels:
                    era_labels.append("Planes")
            elif e in ERA_LABELS:
                era_labels.append(ERA_LABELS[e])
            else:
                era_labels.append(e.capitalize())
        hits.append({
            "name": row["name"],
            "kinds": kinds,
            "primary_kind": row.get("primary_kind"),
            "kind_labels": [KIND_LABELS.get(k, k) for k in kinds if k != "merchant" or kind_f == "merchant"],
            "eras": eras,
            "era_labels": era_labels,
            "url": row.get("url"),
        })

    total = len(hits)
    page = hits[offset: offset + max(1, min(500, int(limit)))]
    payload = _mob_index_payload()
    counts = payload.get("counts") or {}
    era_counts = counts.get("era") if isinstance(counts.get("era"), dict) else {}
    eras_meta = payload.get("eras")
    if not isinstance(eras_meta, list) or not eras_meta:
        eras_meta = [
            {"id": eid, "label": ERA_LABELS[eid], "count": int(era_counts.get(eid, 0) or 0)}
            for eid in ERA_FILTERS
        ]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": q,
        "kind": kind_f or "all",
        "era": era_f or "all",
        "mobs": page,
        "catalog_size": len(pool),
        "counts": counts,
        "kinds": [{"id": k, "label": KIND_LABELS[k], "count": counts.get(k, 0)} for k in ("raid", "mini_boss", "named", "standard")],
        "eras": eras_meta,
        "note": payload.get("note") or (
            "Mob names from eqlwiki NPC categories. Mini bosses from Plane of Hate Map Locations."
        ),
        "era_note": payload.get("era_note") or (
            "Era filter uses eqlwiki Classic / Kunark / Velious (+ Fear/Hate/Sky) era categories."
        ),
        "source": payload.get("source") or "eqlwiki",
        "index_path": payload.get("_index_path") or "",
        "warning": payload.get("warning"),
    }


@lru_cache(maxsize=1)
def _drops_by_mob() -> dict[str, list[dict[str, Any]]]:
    """Reverse index: mob key → [{item, zone}] from decoded catalog dropsFrom."""
    out: dict[str, list[dict[str, Any]]] = {}
    try:
        decoded = decoded_dir()
    except Exception:
        return {}
    catalog = _load_json(decoded / "catalog.json")
    if not isinstance(catalog, dict):
        catalog = {}

    def add(mob: str, item: str, zone: str = "") -> None:
        m = (mob or "").strip()
        if not m or _name_key(m) in _PLACEHOLDER_MOBS:
            return
        key = _name_key(m)
        bucket = out.setdefault(key, [])
        entry = {"item": item, "zone": zone, "mob": m}
        if not any(e.get("item") == item and e.get("zone") == zone for e in bucket):
            bucket.append(entry)

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
            if not item:
                continue
            for e in tip.get("dropsFrom") or []:
                if isinstance(e, dict):
                    add(e.get("npc") or e.get("mob") or "", item, e.get("location") or e.get("zone") or "")

    for section in ("weapons", "proc", "focus", "bardResonance", "clickies", "worn"):
        for row in catalog.get(section) or []:
            if not isinstance(row, dict):
                continue
            item = (row.get("name") or "").strip()
            if not item:
                continue
            for e in row.get("dropsFromEntries") or []:
                if isinstance(e, dict):
                    add(e.get("npc") or e.get("mob") or "", item, e.get("location") or "")

    agg = _load_json(decoded / "aggregate.json")
    if isinstance(agg, list):
        for row in agg:
            if not isinstance(row, dict):
                continue
            item = (row.get("name") or "").strip()
            if not item:
                continue
            for e in row.get("dropsFrom") or []:
                if isinstance(e, dict):
                    add(e.get("npc") or e.get("mob") or "", item, e.get("location") or "")

    return out


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


def _http_get(url: str, timeout: float = 25.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    ctx = _ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except Exception:
        return None


def _mob_cache_dir() -> Path:
    return APP_ROOT / "data" / "eqlwiki-mob-cache"


def _mob_cache_path(name: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-").lower() or "mob"
    return _mob_cache_dir() / f"{slug}.json"


def _load_mob_cache(name: str) -> dict[str, Any] | None:
    path = _mob_cache_path(name)
    if not path.is_file():
        return None
    data = _load_json(path)
    return data if isinstance(data, dict) else None


def _write_mob_cache(name: str, payload: dict[str, Any]) -> None:
    try:
        d = _mob_cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        _mob_cache_path(name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _parse_namedmobpage(html: str) -> dict[str, Any]:
    """Extract visible Namedmobpage / mobStatsBox fields from eqlwiki HTML — never invent."""
    if not html:
        return {}
    fields: dict[str, str] = {}

    def _set(key: str, val: str) -> None:
        key = re.sub(r"[^a-z0-9]+", "_", (key or "").lower()).strip("_")
        val = (val or "").strip()
        if not key or not val or len(val) > 160:
            return
        # Drop trailing section headers accidentally glued on
        val = re.split(r"\b(?:Spawn|Stats|Special|Casts)\b", val, maxsplit=1)[0].strip(" :")
        if val and key not in fields:
            fields[key] = val

    box = re.search(
        r'<table[^>]*class="[^"]*mobStatsBox[^"]*"[^>]*>([\s\S]*?)</table>',
        html,
        re.I,
    )
    if box:
        rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", box.group(1), re.I)
        for row in rows:
            cells = [
                _WS_RE.sub(" ", _TAG_RE.sub(" ", c)).strip()
                for c in re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", row, re.I)
            ]
            cells = [c for c in cells if c]
            if not cells:
                continue
            if len(cells) >= 2:
                _set(cells[0].rstrip(":"), cells[1])
            else:
                m = re.match(r"^([A-Za-z][A-Za-z ]+?)\s*:\s*(.+)$", cells[0])
                if m:
                    _set(m.group(1), m.group(2))

    if not fields.get("level") or not fields.get("zone"):
        chunk = html
        m = re.search(r'id="mw-content-text"[^>]*>([\s\S]{0,12000})', html, re.I)
        if m:
            chunk = m.group(1)
        text = _WS_RE.sub(" ", _TAG_RE.sub(" ", chunk))
        for label, key in (
            ("Level", "level"),
            ("Zone", "zone"),
            ("Location", "location"),
            ("Race", "race"),
            ("Class", "class"),
        ):
            if fields.get(key):
                continue
            m2 = re.search(
                rf"\b{label}\s*:\s*([A-Za-z0-9(\-][\w'’ \-.,/%()]{{0,60}}?)(?=\s+(?:Race|Class|Level|Zone|Location|Stats|AC|HP|Damage|Special|Casts|Spawn)\b|$)",
                text,
                re.I,
            )
            if m2:
                _set(key, m2.group(1))

    desc = ""
    m3 = re.search(
        r'<div class="eql-mobpage"[^>]*>[\s\S]*?<p>([^<]{40,600})</p>',
        html,
        re.I,
    )
    if not m3:
        m3 = re.search(r'<p>([^<]{40,600})</p>', html, re.I)
    if m3:
        desc = _WS_RE.sub(" ", _TAG_RE.sub(" ", m3.group(1))).strip()

    return {"fields": fields, "description": desc}


def _enrich_from_wiki(name: str) -> dict[str, Any] | None:
    cached = _load_mob_cache(name)
    if cached and (cached.get("fields") or cached.get("description")):
        return cached
    url = _wiki_url(name)
    blob = _http_get(url)
    if not blob:
        return cached
    try:
        html = blob.decode("utf-8", errors="ignore")
    except Exception:
        return cached
    if "does not exist" in html.lower() and "create the page" in html.lower():
        return cached
    parsed = _parse_namedmobpage(html)
    if not parsed:
        return cached
    payload = {
        "name": name,
        "url": url,
        "fields": parsed.get("fields") or {},
        "description": parsed.get("description") or "",
        "source": url,
    }
    _write_mob_cache(name, payload)
    return payload


def mob_detail(name: str, *, fetch: bool = True) -> dict[str, Any]:
    n = (name or "").strip()
    if not n:
        return {"name": "", "error": "empty name", "drops": [], "kinds": []}

    index_row = None
    for row in list_mobs():
        if _name_key(row.get("name") or "") == _name_key(n):
            index_row = row
            break

    kinds = list((index_row or {}).get("kinds") or [])
    url = (index_row or {}).get("url") or _wiki_url(n)
    drops_raw = _drops_by_mob().get(_name_key(n), [])
    # Fuzzy: also try without zone parenthetical
    if not drops_raw and "(" in n:
        bare = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
        drops_raw = _drops_by_mob().get(_name_key(bare), [])

    zones = sorted({d.get("zone") for d in drops_raw if d.get("zone")})
    items = sorted({d.get("item") for d in drops_raw if d.get("item")})

    wiki = None
    if fetch:
        try:
            wiki = _enrich_from_wiki(n)
        except Exception:
            wiki = None

    fields = (wiki or {}).get("fields") or {}
    return {
        "name": (index_row or {}).get("name") or n,
        "kinds": kinds,
        "kind_labels": [KIND_LABELS.get(k, k) for k in kinds],
        "wiki_categories": (index_row or {}).get("wiki_categories") or [],
        "url": url,
        "fields": fields,
        "level": fields.get("level") or "",
        "zone": fields.get("zone") or (zones[0] if len(zones) == 1 else ""),
        "location": fields.get("location") or "",
        "description": (wiki or {}).get("description") or "",
        "drops": drops_raw[:80],
        "drop_items": items[:80],
        "drop_zones": zones[:40],
        "drop_count": len(drops_raw),
        "in_index": bool(index_row),
        "note": (
            "Detail from eqlwiki page when available; drops reverse-indexed from decoded catalog "
            "(never invented)."
        ),
        "cached": bool(wiki),
    }
