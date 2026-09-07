"""Zone research loader — reads only zone-research JSON/CSV. Never invents data."""
from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import app_root, legends_root


def zone_research_dir() -> Path:
    root = app_root()
    for cand in (
        root / "data" / "zone-research",
        root / "resources" / "data" / "zone-research",
        legends_root().parent / "eq-legends" / "zone-research",
        Path("/workspace/eq-legends/zone-research"),
        legends_root() / "zone-research",
    ):
        if (cand / "zones_index.json").exists() or (cand / "zones").is_dir():
            return cand.resolve()
    return (root / "data" / "zone-research").resolve()


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


@lru_cache(maxsize=1)
def load_zones_index() -> dict[str, Any]:
    p = zone_research_dir() / "zones_index.json"
    if not p.exists():
        return {"zones": [], "generated": None}
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_mobs_csv() -> list[dict[str, str]]:
    p = zone_research_dir() / "mobs.csv"
    if not p.exists():
        return []
    rows: list[dict[str, str]] = []
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def list_zones() -> list[dict[str, Any]]:
    idx = load_zones_index()
    out = []
    for z in idx.get("zones") or []:
        out.append({
            "zone": z.get("zone") or "",
            "slug": z.get("slug") or _slugify(z.get("zone") or ""),
            "status": z.get("status"),
            "mobs_total": z.get("mobs_total"),
            "mobs_with_level": z.get("mobs_with_level"),
            "mobs_with_spawn": z.get("mobs_with_spawn"),
            "level_requirement": z.get("level_requirement"),
        })
    return out


def _zone_json_path(slug_or_name: str) -> Path | None:
    raw = (slug_or_name or "").strip()
    if not raw:
        return None
    zdir = zone_research_dir() / "zones"
    slug = _slugify(raw)
    candidates = [
        zdir / f"{slug}.json",
        zdir / f"{raw}.json",
    ]
    # Try index lookup by exact name / case-insensitive
    for z in (load_zones_index().get("zones") or []):
        name = (z.get("zone") or "").strip()
        zslug = (z.get("slug") or _slugify(name)).strip()
        if raw.lower() == name.lower() or slug == zslug or raw.lower() == zslug.lower():
            p = zdir / f"{zslug}.json"
            if p.exists():
                return p
            # path field may be absolute from research machine
            path_field = z.get("path")
            if path_field:
                pp = Path(path_field)
                if pp.exists():
                    return pp
                # remap /workspace/eq-legends/zone-research/... → local
                local = zone_research_dir() / "zones" / f"{zslug}.json"
                if local.exists():
                    return local
    for c in candidates:
        if c.exists():
            return c
    # fuzzy: slug contains
    if zdir.is_dir():
        for f in zdir.glob("*.json"):
            if f.stem == slug or slug in f.stem or f.stem in slug:
                return f
    return None


def _csv_levels_for_zone(zone_name: str) -> dict[str, dict[str, str]]:
    """mob name lower → {level, spawn_known, spawn_notes} from mobs.csv."""
    want = (zone_name or "").strip().lower()
    out: dict[str, dict[str, str]] = {}
    for row in load_mobs_csv():
        if (row.get("zone") or "").strip().lower() != want:
            continue
        mob = (row.get("mob") or "").strip()
        if not mob:
            continue
        out[mob.lower()] = {
            "level": row.get("level") or "",
            "spawn_known": row.get("spawn_known") or "",
            "spawn_notes": row.get("spawn_notes") or "",
        }
    return out


def get_zone(name_or_slug: str) -> dict[str, Any] | None:
    path = _zone_json_path(name_or_slug)
    if not path or not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    zone_name = data.get("zone") or name_or_slug
    csv_map = _csv_levels_for_zone(zone_name)
    overview = data.get("overview") or {}
    mobs_out = []
    for m in data.get("mobs") or []:
        name = (m.get("name") or "").strip()
        spawn = m.get("spawn") or {}
        level = m.get("level")
        csv = csv_map.get(name.lower()) or {}
        if level in (None, "") and csv.get("level"):
            level = csv["level"]
        spawn_known = bool(spawn.get("known"))
        coords = spawn.get("coords")
        notes = spawn.get("notes") or ""
        if csv.get("spawn_known", "").lower() == "true":
            spawn_known = True
            if not notes and csv.get("spawn_notes"):
                notes = csv["spawn_notes"]
        if not spawn_known and not coords:
            notes = notes or "mob location unknown"
        mobs_out.append({
            "name": name,
            "level": level,
            "spawn_known": spawn_known,
            "spawn_notes": notes if notes else ("mob location unknown" if not spawn_known else ""),
            "coords": coords,
            "map_url": spawn.get("map_url") or "",
            "sources": m.get("sources") or [],
        })
    map_urls = overview.get("map_urls") or []
    map_url = ""
    if map_urls:
        first = map_urls[0]
        map_url = first.get("url") if isinstance(first, dict) else str(first)
    return {
        "zone": zone_name,
        "slug": data.get("slug") or _slugify(zone_name),
        "overview": {
            "brief": overview.get("brief") or "",
            "level_requirement": overview.get("level_requirement") or "",
            "access_keys": overview.get("access_keys") or [],
            "walkthrough_urls": overview.get("walkthrough_urls") or [],
            "map_urls": map_urls,
            "sources": overview.get("sources") or [],
        },
        "map_url": map_url,
        "mobs": mobs_out,
        "coverage": data.get("coverage") or {},
        "research_notes": data.get("research_notes") or {},
        "source": "zone-research",
    }


def parse_drops_mobs(drops_mobs: str) -> list[str]:
    """Split item drops_mobs string into mob name candidates (no invention)."""
    raw = (drops_mobs or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s*(?:,|;|\band\b)\s*", raw, flags=re.I)
    names = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # strip trailing (Zone Name)
        p = re.sub(r"\s*\([^)]*\)\s*$", "", p).strip()
        if p:
            names.append(p)
    return names


def zone_detail_for_item(zone: str, drops_mobs: str = "") -> dict[str, Any]:
    """Build zone panel payload for an item's zone + drop mobs."""
    z = get_zone(zone) if zone else None
    wanted = {n.lower() for n in parse_drops_mobs(drops_mobs)}
    if not z:
        return {
            "found": False,
            "zone": zone or "",
            "message": "Zone not in zone-research yet." if zone else "No zone on item.",
            "drop_mobs": [{"name": n, "level": None, "spawn_notes": "mob location unknown"} for n in parse_drops_mobs(drops_mobs)],
            "overview": {},
            "map_url": "",
            "mobs": [],
            "walkthrough_urls": [],
            "access_keys": [],
        }
    mob_by_lower = { (m.get("name") or "").lower(): m for m in z.get("mobs") or [] }
    drop_rows = []
    for n in parse_drops_mobs(drops_mobs):
        hit = mob_by_lower.get(n.lower())
        if hit:
            drop_rows.append({
                "name": hit["name"],
                "level": hit.get("level"),
                "spawn_known": hit.get("spawn_known"),
                "spawn_notes": hit.get("spawn_notes") or "mob location unknown",
                "coords": hit.get("coords"),
                "map_url": hit.get("map_url") or "",
            })
        else:
            # try csv-only
            csv_map = _csv_levels_for_zone(z["zone"])
            csv = csv_map.get(n.lower()) or {}
            drop_rows.append({
                "name": n,
                "level": csv.get("level") or None,
                "spawn_known": (csv.get("spawn_known") or "").lower() == "true",
                "spawn_notes": csv.get("spawn_notes") or "mob location unknown",
                "coords": None,
                "map_url": "",
            })
    # If no drops_mobs, still return full zone with overview/map
    return {
        "found": True,
        "zone": z["zone"],
        "slug": z["slug"],
        "overview": z["overview"],
        "map_url": z.get("map_url") or "",
        "access_keys": (z.get("overview") or {}).get("access_keys") or [],
        "walkthrough_urls": (z.get("overview") or {}).get("walkthrough_urls") or [],
        "drop_mobs": drop_rows,
        "mobs": z.get("mobs") or [],
        "coverage": z.get("coverage") or {},
        "filter_mobs": sorted(wanted),
    }
