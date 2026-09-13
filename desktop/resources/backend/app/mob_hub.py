"""Mobs hub: eqlwiki NPC index + on-demand page detail + catalog drop reverse-index.

Mob names and kinds come from decoded/eqlwiki_mob_names.json (eqlwiki categories).
Detail fields and Known Loot are parsed from the real eqlwiki page when available —
never invented. Catalog reverse-index drops are unioned with wiki loot (deduped by name).
"""
from __future__ import annotations

import html as html_lib
import json
import re
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

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
# Title/kind disambiguators only — do not merge zone/race/gender parentheticals.
_TITLE_PAREN_LABELS = frozenset({
    "god",
    "npc",
    "mob",
    "raid",
    "raid boss",
    "named",
    "mini",
    "mini boss",
    "mini-boss",
    "rare",
    "rare drop",
})
_SKIP_LOOT_LINK_NAMES = frozenset({
    "edit",
    "edit section",
    "known loot",
    "unique loot",
    "common loot",
})
_SKIP_LOOT_TITLE_PREFIXES = (
    "category:",
    "file:",
    "image:",
    "special:",
    "talk:",
    "template:",
    "user:",
    "help:",
)
# High safety cap — god/raid lists are tens of items, not hundreds.
DROP_LIST_CAP = 400


def _name_key(name: str) -> str:
    s = (name or "").strip().lower()
    for ch in ("\u2019", "\u2018", "`", "\u02bc"):
        s = s.replace(ch, "'")
    return s


def _clean_wiki_text(val: str) -> str:
    return _WS_RE.sub(" ", html_lib.unescape(_TAG_RE.sub(" ", val or ""))).strip()


def _strip_title_parens(name: str) -> str:
    """Strip trailing (God)/(NPC)/… kind labels; leave zone/race/gender parens."""
    s = (name or "").strip()
    while True:
        m = re.search(r"\s*\(([^)]*)\)\s*$", s)
        if not m:
            return s
        inner = _WS_RE.sub(" ", m.group(1)).strip().lower()
        if inner not in _TITLE_PAREN_LABELS:
            return s
        s = s[: m.start()].strip()


def _catalog_lookup_keys(name: str, index_keys: Iterable[str] | None = None) -> list[str]:
    """Exact catalog key plus title-parenthetical variants (Innoruuk (God) ↔ Innoruuk)."""
    out: list[str] = []
    seen: set[str] = set()

    def add(key: str) -> None:
        k = (key or "").strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)

    add(_name_key(name))
    stripped = _name_key(_strip_title_parens(name))
    add(stripped)
    if index_keys is not None and stripped:
        prefix = f"{stripped} ("
        for k in index_keys:
            if not k.startswith(prefix) or not k.endswith(")"):
                continue
            inner = k[len(prefix) : -1].strip()
            if inner in _TITLE_PAREN_LABELS:
                add(k)
    return out


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

    return {
        "fields": fields,
        "description": desc,
        "known_loot": _parse_known_loot(html),
    }


def _skip_loot_name(name: str) -> bool:
    key = _name_key(name)
    if not key or key in _SKIP_LOOT_LINK_NAMES or key in _PLACEHOLDER_MOBS:
        return True
    return any(key.startswith(p) for p in _SKIP_LOOT_TITLE_PREFIXES)


def _first_item_link(fragment: str) -> str:
    """Visible item name from the first wiki link in a loot-list row — never invented."""
    if not fragment:
        return ""
    m = re.search(r"<a\b([^>]*)>(.*?)</a>", fragment, re.I | re.S)
    if not m:
        return ""
    attrs, inner = m.group(1), m.group(2)
    href_m = re.search(r'\bhref="([^"]*)"', attrs, re.I)
    href = (href_m.group(1) if href_m else "").strip()
    if href.startswith("#"):
        return ""
    title_m = re.search(r'\btitle="([^"]*)"', attrs, re.I)
    title = html_lib.unescape(title_m.group(1)).strip() if title_m else ""
    visible = _clean_wiki_text(inner)
    name = visible or title
    if _skip_loot_name(name):
        return ""
    return name


def _loot_section_chunks(html: str) -> list[str]:
    """eqlwiki Known / Unique / Common Loot bodies (stop at the next heading)."""
    chunks: list[str] = []
    for m in re.finditer(
        r'<h2\b[^>]*id="((?:Known|Unique|Common)_Loot)"[^>]*>[\s\S]*?</h2>'
        r'([\s\S]*?)(?=<h2\b|<div class="eql-mobpage-section(?![^"]*loot)|</body>|\Z)',
        html,
        re.I,
    ):
        chunks.append(m.group(2))
    if chunks:
        return chunks
    box = re.search(
        r'<div class="[^"]*eql-mobpage-loot[^"]*"[^>]*>([\s\S]*?)'
        r'(?=<div class="eql-mobpage-section(?![^"]*loot)|<h2[^>]*id="Description")',
        html,
        re.I,
    )
    if box:
        chunks.append(box.group(1))
    return chunks


def _parse_known_loot(html: str) -> list[dict[str, str]]:
    """Item links from eqlwiki Known Loot (and Unique/Common Loot) — sourced only."""
    if not html:
        return []
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = (name or "").strip()
        if not name or _skip_loot_name(name):
            return
        key = _name_key(name)
        if key in seen:
            return
        seen.add(key)
        items.append({"item": name})

    for chunk in _loot_section_chunks(html):
        lists = re.findall(r"<(ul|ol)\b[^>]*>([\s\S]*?)</\1>", chunk, re.I)
        rows: list[str] = []
        for _tag, body in lists:
            rows.extend(re.findall(r"<li\b[^>]*>([\s\S]*?)</li>", body, re.I))
        if not rows:
            rows = re.findall(
                r'<div class="hbdiv">\s*(<a\b[\s\S]*?</a>)',
                chunk,
                re.I,
            )
        for row in rows:
            add(_first_item_link(row))
    return items


def _enrich_from_wiki(name: str, url: str | None = None) -> dict[str, Any] | None:
    cached = _load_mob_cache(name)
    # Older caches lack known_loot — refetch so Known Loot is parsed.
    if cached and "known_loot" in cached:
        return cached
    page_url = (url or "").strip() or _wiki_url(name)
    blob = _http_get(page_url)
    if not blob and page_url != _wiki_url(name):
        blob = _http_get(_wiki_url(name))
        if blob:
            page_url = _wiki_url(name)
    if not blob:
        return cached
    try:
        page_html = blob.decode("utf-8", errors="ignore")
    except Exception:
        return cached
    if "does not exist" in page_html.lower() and "create the page" in page_html.lower():
        return cached
    parsed = _parse_namedmobpage(page_html)
    if not parsed:
        return cached
    payload = {
        "name": name,
        "url": page_url,
        "fields": parsed.get("fields") or {},
        "description": parsed.get("description") or "",
        "known_loot": parsed.get("known_loot") or [],
        "source": page_url,
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

    wiki = None
    if fetch:
        try:
            wiki = _enrich_from_wiki(n, url=url)
        except Exception:
            wiki = None
    else:
        cached = _load_mob_cache(n)
        if cached and "known_loot" in cached:
            wiki = cached

    fields = (wiki or {}).get("fields") or {}
    wiki_loot = list((wiki or {}).get("known_loot") or [])
    catalog_drops = _catalog_drops_for_name(n)
    wiki_zone = (fields.get("zone") or "").strip()
    drops_raw = _union_drops(wiki_loot, catalog_drops, default_zone=wiki_zone)

    zones = sorted({d.get("zone") for d in drops_raw if d.get("zone")})
    items = [d.get("item") for d in drops_raw if d.get("item")]
    cap = DROP_LIST_CAP

    return {
        "name": (index_row or {}).get("name") or n,
        "kinds": kinds,
        "kind_labels": [KIND_LABELS.get(k, k) for k in kinds],
        "wiki_categories": (index_row or {}).get("wiki_categories") or [],
        "url": (wiki or {}).get("url") or url,
        "fields": fields,
        "level": fields.get("level") or "",
        "zone": fields.get("zone") or (zones[0] if len(zones) == 1 else ""),
        "location": fields.get("location") or "",
        "description": (wiki or {}).get("description") or "",
        "drops": drops_raw[:cap],
        "drop_items": items[:cap],
        "drop_zones": zones[:40],
        "drop_count": len(drops_raw),
        "wiki_loot_count": len(wiki_loot),
        "catalog_drop_count": len({_name_key(d.get("item") or "") for d in catalog_drops if d.get("item")}),
        "in_index": bool(index_row),
        "note": (
            "Detail from eqlwiki page when available. Known drops union eqlwiki Known Loot "
            "and decoded catalog reverse-index (never invented)."
        ),
        "cached": bool(wiki),
    }


def _catalog_drops_for_name(name: str) -> list[dict[str, Any]]:
    """Reverse-index hits for this mob name and title-parenthetical variants."""
    index = _drops_by_mob()
    keys = _catalog_lookup_keys(name, index.keys())
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for key in keys:
        for e in index.get(key) or []:
            if not isinstance(e, dict):
                continue
            item = (e.get("item") or "").strip()
            if not item:
                continue
            zone = (e.get("zone") or "").strip()
            sig = (_name_key(item), _name_key(zone))
            if sig in seen:
                continue
            seen.add(sig)
            row = dict(e)
            row["source"] = ["catalog"]
            out.append(row)
    return out


def _union_drops(
    wiki_loot: list[Any],
    catalog_drops: list[dict[str, Any]],
    *,
    default_zone: str = "",
) -> list[dict[str, Any]]:
    """Dedupe by item name. Prefer wiki display name; tag eqlwiki / catalog / both."""
    by_item: dict[str, dict[str, Any]] = {}

    for raw in wiki_loot:
        if isinstance(raw, dict):
            item = (raw.get("item") or "").strip()
        else:
            item = str(raw or "").strip()
        if not item or _skip_loot_name(item):
            continue
        key = _name_key(item)
        if not key or key in by_item:
            continue
        by_item[key] = {
            "item": item,
            "zone": default_zone,
            "source": ["eqlwiki"],
        }

    for e in catalog_drops:
        item = (e.get("item") or "").strip()
        if not item:
            continue
        key = _name_key(item)
        zone = (e.get("zone") or "").strip()
        if key in by_item:
            existing = by_item[key]
            if zone and not existing.get("zone"):
                existing["zone"] = zone
            src = existing.setdefault("source", [])
            if "catalog" not in src:
                src.append("catalog")
            if e.get("mob") and not existing.get("mob"):
                existing["mob"] = e.get("mob")
        else:
            by_item[key] = {
                "item": item,
                "zone": zone or default_zone,
                "mob": e.get("mob") or "",
                "source": ["catalog"],
            }

    return sorted(by_item.values(), key=lambda r: (r.get("item") or "").lower())
