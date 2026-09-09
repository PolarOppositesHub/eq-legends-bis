"""Quest Hub: catalog quest index + inventory ownership helpers.

Quest names come from decoded catalog rewardFromQuests / quest_source fields only.
Prerequisite quests are taken from eqlwiki text when present, plus documented
Plane of Sky island-access progression (never invented quest names).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import decoded_dir
from . import quest_guides as qg

_STOP = frozenset({"of", "the", "a", "an", "and", "or", "to", "for", "in", "on"})
_QUEST_SOURCE_RE = re.compile(r"(?:reward\s+from\s+(?:quest|the)\s*:?\s*)(.+)$", re.I)
_PREREQ_LINE = re.compile(
    r"(?:prerequisite|prerequisites|previous\s+quest|requires?\s+quest|must\s+(?:first\s+)?complete)\s*:?\s*(.+)",
    re.I,
)


def _name_key(name: str) -> str:
    s = (name or "").strip().lower()
    for ch in ("\u2019", "\u2018", "`", "\u02bc"):
        s = s.replace(ch, "'")
    return s


def _clean_quest_label(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    if qg.is_drop_source(s):
        return None
    m = _QUEST_SOURCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    # Strip trailing "Quest" duplication noise carefully
    if s.lower().startswith("player crafted"):
        return None
    if len(s) < 3:
        return None
    return s


def _add_quest(by_key: dict[str, dict[str, Any]], name: str, *, item: str | None = None) -> None:
    cleaned = _clean_quest_label(name)
    if not cleaned:
        return
    key = _name_key(cleaned)
    row = by_key.get(key)
    if not row:
        by_key[key] = {
            "name": cleaned,
            "item_count": 0,
            "sample_items": [],
            "reward_items": [],
        }
        row = by_key[key]
    if item:
        rewards = row.setdefault("reward_items", [])
        if item not in rewards:
            rewards.append(item)
        row["item_count"] = len(rewards)
        samples = row.setdefault("sample_items", [])
        if item not in samples and len(samples) < 8:
            samples.append(item)


@lru_cache(maxsize=1)
def list_quests() -> list[dict[str, Any]]:
    """Unique quest names from decoded catalog / flat item sources."""
    by_key: dict[str, dict[str, Any]] = {}
    try:
        decoded = decoded_dir()
    except Exception:
        return []
    if not decoded.exists():
        return []

    cat_path = decoded / "catalog.json"
    if cat_path.is_file():
        try:
            catalog = json.loads(cat_path.read_text(encoding="utf-8"))
        except Exception:
            catalog = {}
        if isinstance(catalog, dict):
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
                    item = (tip.get("name") or "").strip() or None
                    for q in tip.get("rewardFromQuests") or []:
                        if isinstance(q, str):
                            _add_quest(by_key, q, item=item)

    try:
        flats = sorted(decoded.glob("flat_*.json"))
    except OSError:
        flats = []
    for path in flats:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = (row.get("name") or "").strip() or None
            for fld in ("quest_source", "source", "quest_source_raw"):
                val = row.get(fld)
                if isinstance(val, str) and val.strip():
                    qn = qg.quest_name_from_source(val)
                    if qn:
                        _add_quest(by_key, qn, item=item)

    return sorted(by_key.values(), key=lambda r: (r.get("name") or "").lower())


def _quest_index_public(row: dict[str, Any]) -> dict[str, Any]:
    """Slim index row for /api/quests (omit full reward_items list)."""
    rewards = row.get("reward_items") or row.get("sample_items") or []
    return {
        "name": row.get("name") or "",
        "item_count": len(rewards) if rewards else int(row.get("item_count") or 0),
        "sample_items": list(row.get("sample_items") or [])[:8],
    }


def search_quests(q: str = "", *, limit: int = 200, offset: int = 0) -> dict[str, Any]:
    qn = (q or "").strip().lower()
    tokens = [t for t in re.split(r"[^a-z0-9']+", qn) if t and t not in _STOP]
    pool = list_quests()
    hits: list[dict[str, Any]] = []
    for row in pool:
        name = (row.get("name") or "").lower()
        reward_blob = " ".join(row.get("reward_items") or row.get("sample_items") or []).lower()
        if tokens:
            if not all(t in name for t in tokens):
                blob = f"{name} {reward_blob}"
                if not all(t in blob for t in tokens):
                    continue
        elif qn and qn not in name and qn not in reward_blob:
            continue
        hits.append(_quest_index_public(row))
    total = len(hits)
    page = hits[offset: offset + max(1, min(500, limit))]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": q or "",
        "quests": page,
        "catalog_size": len(pool),
        "note": (
            "Quest list is derived from decoded item rewardFromQuests / quest_source "
            "fields — not a full EQ encyclopedia. Guides fetch from eqlwiki when opened."
        ),
    }


def reward_item_names_for_quest(name: str) -> list[str]:
    """Unique catalog item names linked to this quest (rewardFromQuests / quest_source)."""
    key = _name_key(name)
    if not key:
        return []
    for row in list_quests():
        if _name_key(row.get("name") or "") == key:
            items = row.get("reward_items") or row.get("sample_items") or []
            out: list[str] = []
            seen: set[str] = set()
            for raw in items:
                n = (raw or "").strip()
                if not n:
                    continue
                nk = _name_key(n)
                if nk in seen:
                    continue
                seen.add(nk)
                out.append(n)
            return out
    return []


def rewards_for_quest(name: str, *, upgrade: int = 0) -> list[dict[str, Any]]:
    """Resolve quest reward items with +0..+10 scaled stats (never invent stats)."""
    from . import item_catalog as ic
    from .engine import ratio_at_level, scale_stats_to_level

    upgrade = max(0, min(10, int(upgrade)))
    out: list[dict[str, Any]] = []
    for iname in reward_item_names_for_quest(name):
        it = ic.get_item_by_name(iname)
        if not it:
            out.append({
                "kind": "item",
                "name": iname,
                "in_catalog": False,
                "note": "Linked as a quest reward in decoded data, but no catalog item row was found.",
            })
            continue
        s0 = dict(it.get("stats_plus0") or {})
        s10 = dict(it.get("stats_plus10") or scale_stats_to_level(s0, 10))
        stats_by: dict[str, dict[str, Any]] = {}
        ratio_by: dict[str, float] = {}
        raw_for_ratio = {
            "stats_plus0": s0,
            "ratio_plus0": it.get("ratio_plus0"),
            "ratio_plus10": it.get("ratio_plus10"),
        }
        for lvl in range(0, 11):
            stats_by[str(lvl)] = scale_stats_to_level(s0, lvl) if lvl else dict(s0)
            if lvl == 0:
                # Keep +0 keys numeric like scale_stats_to_level
                stats_by["0"] = {
                    k: (float(v) if isinstance(v, (int, float)) else v)
                    for k, v in s0.items()
                }
            r = ratio_at_level(raw_for_ratio, lvl)
            if r is not None:
                ratio_by[str(lvl)] = float(r)
        out.append({
            "kind": "item",
            "name": it.get("name") or iname,
            "in_catalog": True,
            "slots": it.get("slots") or [],
            "slot": it.get("slot") or "",
            "classes": it.get("classes") or [],
            "classes_str": it.get("classes_str") or "",
            "zone": it.get("zone") or "",
            "url": it.get("url") or "",
            "image_url": it.get("image_url") or "",
            "stats_plus0": s0,
            "stats_plus10": s10,
            "stats_at_upgrade": stats_by.get(str(upgrade), s0),
            "stats_by_upgrade": stats_by,
            "ratio_plus0": it.get("ratio_plus0"),
            "ratio_plus10": it.get("ratio_plus10"),
            "ratio_at_upgrade": ratio_by.get(str(upgrade)),
            "ratio_by_upgrade": ratio_by,
            "upgrade": upgrade,
        })
    return out


def _sky_island_from_guide(guide: dict[str, Any]) -> int | None:
    """Infer Plane of Sky island number from tags/where text (documented legend only)."""
    for c in guide.get("components") or []:
        tag = (c.get("wiki_tag") or "").strip().lower().replace(" ", "")
        if re.match(r"^\d+-", tag):
            try:
                return int(tag.split("-", 1)[0])
            except ValueError:
                pass
        where = (c.get("where") or "")
        m = re.search(r"Island\s+(\d+)", where, re.I)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    for step in guide.get("steps") or []:
        m = re.search(r"Island\s+(\d+)", str(step), re.I)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def _prereqs_from_wiki_html(html: str, quest_name: str) -> list[dict[str, Any]]:
    """Extract prerequisite quest names from eqlwiki HTML/text when explicitly listed."""
    if not html:
        return []
    text = qg._TAG_RE.sub(" ", html)
    text = qg._WS_RE.sub(" ", text)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Prefer section near the quest heading when present
    section = qg._extract_quest_section(html, quest_name) if quest_name else html
    scan = qg._TAG_RE.sub(" ", section or html)
    scan = qg._WS_RE.sub(" ", scan)
    for m in _PREREQ_LINE.finditer(scan):
        rest = m.group(1).strip()
        # Split on common delimiters; keep short quest-like phrases
        parts = re.split(r"\s*(?:,|;|\||/| and )\s*", rest)
        for part in parts[:8]:
            name = part.strip(" .")
            # Cut trailing sentence junk
            name = re.split(r"\.\s+|!\s+|\?\s+", name)[0].strip()
            if len(name) < 4 or len(name) > 90:
                continue
            if name.lower().startswith("http"):
                continue
            key = _name_key(name)
            if key in seen or key == _name_key(quest_name):
                continue
            seen.add(key)
            out.append({
                "name": name,
                "kind": "quest",
                "source": "eqlwiki",
            })
    return out


def _sky_access_prereqs(island: int) -> list[dict[str, Any]]:
    """Documented Plane of Sky island progression (eqlwiki Plane of Sky)."""
    if island is None or island <= 1:
        return [{
            "name": "Enter Plane of Sky (Island 1) — buy Efreeti's Key from the Key Master",
            "kind": "access",
            "source": "eqlwiki Plane of Sky",
            "island": 1,
        }]
    out = [{
        "name": "Enter Plane of Sky (Island 1) — buy Efreeti's Key from the Key Master",
        "kind": "access",
        "source": "eqlwiki Plane of Sky",
        "island": 1,
    }]
    if island >= 2:
        out.append({
            "name": f"Progress Plane of Sky access through Island {island - 1} (keys / teleports per eqlwiki Plane of Sky)",
            "kind": "access",
            "source": "eqlwiki Plane of Sky",
            "island": island - 1,
        })
    return out


def enrich_guide(
    guide: dict[str, Any],
    *,
    wiki_html: str | None = None,
) -> dict[str, Any]:
    """Attach prerequisites (wiki labels + walkthrough mentions + sky access).

    Does not invent quest names — only names that appear in eqlwiki/source text,
    resolved to Quest Hub titles when possible.
    """
    # Prefer the shared walkthrough-aware attacher in quest_guides.
    return qg._attach_prerequisites(guide, html=wiki_html)


def inventory_ownership(
    components: list[dict[str, Any]] | None,
    inventory_items: list[dict[str, Any] | str] | None,
) -> list[dict[str, Any]]:
    """Mark each quest component as owned if a matching name exists in imported inventory."""
    owned_keys: set[str] = set()
    owned_rows: list[dict[str, Any]] = []
    for raw in inventory_items or []:
        if isinstance(raw, str):
            name = raw.strip()
            loc = ""
            count = ""
        else:
            name = (raw.get("base_name") or raw.get("name") or "").strip()
            loc = (raw.get("location") or "").strip()
            count = str(raw.get("count") or "").strip()
        if not name or name.lower() == "empty":
            continue
        key = _name_key(name)
        owned_keys.add(key)
        # also index without upgrade suffix already stripped in base_name
        owned_rows.append({"name": name, "location": loc, "count": count, "key": key})

    out: list[dict[str, Any]] = []
    for c in components or []:
        item = (c.get("item") or "").strip()
        # Strip sky tags "Woven Skull Cap (4-KoS)" for matching
        bare = re.sub(r"\s*\([^)]*\)\s*$", "", item).strip() or item
        key = _name_key(bare)
        hits = [r for r in owned_rows if r["key"] == key or key in r["key"] or r["key"] in key]
        # Prefer exact key match
        exact = [r for r in owned_rows if r["key"] == key]
        use = exact or hits
        out.append({
            **c,
            "item": item,
            "have": bool(use),
            "have_locations": [
                f"{r['location']}" + (f" ×{r['count']}" if r.get("count") else "")
                for r in use[:6]
                if r.get("location")
            ],
        })
    return out


def quest_detail(
    name: str,
    *,
    fetch: bool = True,
    inventory_items: list[Any] | None = None,
    upgrade: int = 0,
) -> dict[str, Any]:
    guide = qg.ensure_quest_guide(name, fetch=fetch)
    enriched = enrich_guide(guide, wiki_html=None)
    # Merge prerequisites already on guide (from fetch) with enrich_guide access notes.
    base_prereqs = list(guide.get("prerequisites") or [])
    extra = list(enriched.get("prerequisites") or [])
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in base_prereqs + extra:
        key = _name_key(p.get("name") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(p)
    enriched["prerequisites"] = merged
    enriched["prerequisites_note"] = (
        ""
        if merged
        else (
            enriched.get("prerequisites_note")
            or "No prerequisite quests listed in available eqlwiki/source text for this quest."
        )
    )

    components = inventory_ownership(enriched.get("components") or [], inventory_items)
    enriched["components"] = components
    have_n = sum(1 for c in components if c.get("have"))
    enriched["inventory"] = {
        "checked": inventory_items is not None,
        "have_count": have_n,
        "need_count": max(0, len(components) - have_n),
        "imported": bool(inventory_items),
    }

    upgrade_n = max(0, min(10, int(upgrade)))
    rewards = rewards_for_quest(name, upgrade=upgrade_n)
    enriched["rewards"] = rewards
    enriched["reward_upgrade"] = upgrade_n
    enriched["rewards_note"] = (
        ""
        if rewards
        else (
            "No item rewards linked in the decoded catalog for this quest "
            "(rewardFromQuests / quest_source)."
        )
    )
    return enriched
