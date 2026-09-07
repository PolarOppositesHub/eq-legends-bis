"""EQ Legends BiS + build-sim FastAPI - engine-backed, UI-compatible."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import engine
from . import inventory as inventory_mod
from . import zones as zones_mod
from . import item_catalog as item_catalog_mod
from .races import get_races_payload

from .paths import APP_ROOT, decoded_dir, frontend_dist, legends_root, packaged_mode, xlsx_dir

LEGENDS = legends_root()
FRONTEND_DIST = frontend_dist()

app = FastAPI(title="EQ Legends BiS + Build Sim", version="1.0.5")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BisRequest(BaseModel):
    classes: list[str] = Field(default_factory=list)
    mode: str = "priority"
    priority_stat: str = "INT"
    primary_stats: list[str] = Field(default_factory=list)
    secondary_stats: list[str] = Field(default_factory=list)
    tertiary_stats: list[str] = Field(default_factory=list)
    maximize_hp_regen: bool = False
    alts: int = 5
    upgrade: int = 10
    usable_by: str = "any"  # weapons/gear: any selected class (union)
    prefer_ranged_damage: bool = True
    character_level: int = 50


class SimulateRequest(BaseModel):
    classes: list[str] = Field(default_factory=list)
    race: str | None = "Human"
    upgrade: int = 10
    character_level: int | None = 50
    equipment: dict[str, Any] = Field(default_factory=dict)
    slots: dict[str, Any] | None = None
    equipped: dict[str, Any] | None = None
    # Cast Buffs: off | quick (max lines for trio) | manual
    cast_buffs: str = "off"
    active_buff_ids: list[str] = Field(default_factory=list)
    assume_max_aas: bool = True


class ExportRequest(BaseModel):
    classes: list[str] = Field(default_factory=list)


class InventoryParseRequest(BaseModel):
    text: str = ""


class UpgradeSuggestRequest(BaseModel):
    classes: list[str] = Field(default_factory=list)
    equipment: dict[str, Any] = Field(default_factory=dict)
    upgrade: int = 10
    character_level: int = 50
    prefer_ranged_damage: bool = True
    inventory_text: str | None = None
    mode: str = "ai"
    primary_stats: list[str] = Field(default_factory=list)
    secondary_stats: list[str] = Field(default_factory=list)
    tertiary_stats: list[str] = Field(default_factory=list)
    maximize_hp_regen: bool = False
    priority_stat: str = "HP"
    fetch_quest_guides: bool = True


def _norm_classes(classes: list[str] | None, *, allow_empty: bool = True) -> list[str]:
    """Normalize class names. Empty list is allowed (UI starts with no selection).
    Does NOT force DEFAULT_TRIO into API responses / UI."""
    cleaned = []
    for c in classes or []:
        c = (c or "").strip()
        match = next((a for a in engine.ALL_CLASSES if a.lower() == c.lower()), None)
        if match and match not in cleaned:
            cleaned.append(match)
    if not cleaned and not allow_empty:
        raise HTTPException(400, "Select at least one class (up to 3)")
    if len(cleaned) > 3:
        raise HTTPException(400, "Select at most 3 classes")
    return cleaned


def _equipment_map(body: SimulateRequest) -> dict[str, str]:
    raw: dict[str, str] = {}
    for src in (body.equipment, body.slots, body.equipped):
        for k, v in (src or {}).items():
            if v is None or v == "":
                continue
            name = v.get("name") if isinstance(v, dict) else str(v)
            if name:
                raw[str(k).upper()] = name
    return raw


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "classes": engine.ALL_CLASSES,
        "default_trio": engine.DEFAULT_TRIO,
        "data": str(decoded_dir()),
        "packaged": packaged_mode(),
    }


@app.get("/api/meta")
def meta():
    return engine.meta_payload()


@app.get("/api/classes")
def get_classes():
    m = engine.meta_payload()
    return {
        "classes": m["classes"],
        "default_trio": m["default_trio"],
        "ui_default_classes": m.get("ui_default_classes") or [],
        "priority_stats": m["priority_stats"],
        "slots": m["slots"],
        "planner_slots": m["slots"],
        "modes": m.get("modes") or [
            {"id": "priority", "label": "Priority Stat"},
            {"id": "max", "label": "Max All Stats"},
            {"id": "ai", "label": "AI Choice"},
        ],
        "haste_note": m["haste_rule"],
        "notes": {
            "haste": m["haste_rule"],
            "weapons": m.get("weapon_rule") or "Weapons ranked by ratio (any selected class).",
            "scoring": m.get("scoring") or {},
        },
        "races": m["races"],
        "class_roles": m.get("class_roles"),
        "upgrade_levels": m["upgrade_levels"],
        "character_levels": m.get("character_levels") or list(range(1, 51)),
        "prefer_ranged_damage_default": m.get("prefer_ranged_damage_default", True),
        "catalog_weapons": m["catalog_weapons"],
        "version": m.get("version") or "1.0.9",
        "scoring": m.get("scoring"),
    }


@app.get("/api/races")
def get_races():
    return get_races_payload()


@app.post("/api/bis")
def post_bis(body: BisRequest):
    classes = _norm_classes(body.classes, allow_empty=True)
    if not classes:
        raise HTTPException(400, "Select at least one class (up to 3)")
    try:
        level = max(1, min(50, int(body.character_level or 50)))
        return engine.recommend_bis(
            classes,
            mode=body.mode,
            priority_stat=body.priority_stat,
            alts=body.alts,
            upgrade=body.upgrade,
            prefer_ranged_damage=body.prefer_ranged_damage,
            character_level=level,
            primary_stats=body.primary_stats,
            secondary_stats=body.secondary_stats,
            tertiary_stats=body.tertiary_stats,
            maximize_hp_regen=bool(body.maximize_hp_regen),
        )
    except AssertionError as e:
        raise HTTPException(500, f"BiS haste assertion failed: {e}") from e
    except Exception as e:
        raise HTTPException(500, f"BiS failed: {e}") from e


@app.get("/api/priority-defaults")
def api_priority_defaults(classes: Optional[list[str]] = Query(default=None)):
    """Suggested primary/secondary/tertiary priority stats for the selected trio."""
    cls_list: list[str] = []
    for entry in classes or []:
        for part in str(entry).split(","):
            part = part.strip()
            if part:
                cls_list.append(part)
    cleaned = _norm_classes(cls_list, allow_empty=True)
    from . import class_roles as cr
    tiers = cr.trio_default_priority_tiers(cleaned)
    return {
        "classes": cleaned,
        "primary_stats": tiers["primary"],
        "secondary_stats": tiers["secondary"],
        "tertiary_stats": tiers["tertiary"],
        "note": "Defaults from races.json classStats ranking across the trio; user may override.",
    }


@app.get("/api/item-search")
def api_item_search(
    q: str = Query(default=""),
    slot: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Search all catalog items (full game DB union of flat_* + aggregate)."""
    return item_catalog_mod.search_items(q, slot=slot, limit=limit, offset=offset)


@app.get("/api/item-detail")
def api_item_detail(name: str = Query(...)):
    it = item_catalog_mod.get_item_by_name(name)
    if not it:
        raise HTTPException(404, f"Item not found: {name}")
    # Best-effort icon fetch/cache (non-fatal if wiki unavailable)
    try:
        img = item_catalog_mod.ensure_item_image(name, fetch=True)
        it = {**it, "image": img}
    except Exception as e:
        it = {**it, "image": {"error": str(e)}}
    return it


@app.get("/api/item-image")
def api_item_image(name: str = Query(...), fetch: bool = Query(default=True)):
    """Serve cached item icon; optionally look up on eqlwiki and save."""
    info = item_catalog_mod.ensure_item_image(name, fetch=fetch)
    path = item_catalog_mod.local_image_path(name)
    if path and path.is_file():
        return FileResponse(path)
    raise HTTPException(404, info.get("error") or f"No image for {name}")


@app.post("/api/item-image/ensure")
def api_ensure_item_image(name: str = Query(...)):
    return item_catalog_mod.ensure_item_image(name, fetch=True)


@app.get("/api/items")
def get_items(
    classes: Optional[list[str]] = Query(default=None),
    c1: Optional[str] = Query(default=None),
    c2: Optional[str] = Query(default=None),
    c3: Optional[str] = Query(default=None),
    mode: str = Query(default="priority"),
    stat: str = Query(default="HP"),
    upgrade: int = Query(default=10),
    slot: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    usable_by: str = Query(default="any"),
    prefer_ranged: Optional[bool] = Query(default=True),
    prefer_ranged_damage: Optional[bool] = Query(default=None),
    character_level: int = Query(default=50, ge=1, le=50),
    include_loadout: bool = Query(default=False),
):
    cls_list: list[str] = []
    if classes:
        # Accept repeated ?classes=A&classes=B or a single comma-separated value
        for entry in classes:
            for part in str(entry).split(","):
                part = part.strip()
                if part:
                    cls_list.append(part)
    else:
        for c in (c1, c2, c3):
            if c:
                cls_list.append(c)
    cls = _norm_classes(cls_list, allow_empty=True)
    if not cls:
        raise HTTPException(400, "Select at least one class (up to 3)")

    prefer = prefer_ranged_damage if prefer_ranged_damage is not None else (
        True if prefer_ranged is None else prefer_ranged
    )

    if slot:
        items = engine.items_for_slot(
            cls,
            slot=slot,
            q=q,
            upgrade=upgrade,
            prefer_ranged_damage=bool(prefer),
        )[:limit]
        return {
            "classes": cls,
            "slot": slot.upper(),
            "upgrade": upgrade,
            "prefer_ranged_damage": bool(prefer),
            "items": items,
            "count": len(items),
        }

    mode_l = "max" if mode in ("max", "max_all", "weapons") else "priority"
    bis = engine.recommend_bis(
        cls,
        mode=mode_l,
        priority_stat=stat,
        alts=min(8, limit),
        upgrade=upgrade,
        prefer_ranged_damage=bool(prefer),
        character_level=character_level or 50,
    )
    by_slot: dict[str, list] = {}
    for row in bis["slots"]:
        s = row["slot"]
        primary = {k: v for k, v in row.items() if k != "alts"}
        by_slot[s] = [primary] + (row.get("alts") or [])[: max(0, limit - 1)]
    out: dict[str, Any] = {
        "classes": cls,
        "mode": mode,
        "stat": bis.get("priority_stat_key"),
        "upgrade": upgrade,
        "usable_by": usable_by,
        "prefer_ranged_damage": bool(prefer),
        "pool_size": bis["pool_size"],
        "by_slot": by_slot,
        "recommended": {r["slot"]: r for r in bis["slots"] if r.get("name")},
        "recommended_haste_items": bis.get("haste_in_loadout") or [],
        "recommended_haste_ok": len(bis.get("haste_in_loadout") or []) <= 1,
    }
    if include_loadout:
        out["suggested_loadout"] = out["recommended"]
    return out


@app.get("/api/items/{item_key:path}")
def item_detail(item_key: str):
    pool = engine.build_pool_for_classes(list(engine.DEFAULT_TRIO), mode="any")
    item = engine.get_item_by_name(pool, item_key.replace("%20", " ").replace("+", " "))
    if not item:
        raise HTTPException(404, f"Item not found: {item_key}")
    return engine._public_item(item, 10)


@app.post("/api/simulate")
def post_simulate(body: SimulateRequest):
    classes = _norm_classes(body.classes, allow_empty=True)
    if not classes:
        raise HTTPException(400, "Select at least one class (up to 3)")
    equipment = _equipment_map(body)
    try:
        level = None if body.character_level is None else max(1, min(50, int(body.character_level)))
        return engine.simulate(
            classes,
            body.race,
            equipment,
            upgrade=body.upgrade,
            character_level=level if level is not None else 50,
            cast_buffs=body.cast_buffs or "off",
            active_buff_ids=list(body.active_buff_ids or []),
            assume_max_aas=bool(body.assume_max_aas),
        )
    except Exception as e:
        raise HTTPException(500, f"Simulate failed: {e}") from e


@app.get("/api/spell-buffs")
def api_spell_buffs(classes: Optional[list[str]] = Query(default=None)):
    """Buff catalog filtered to selected trio classes (eqlegendstools spellBuffs)."""
    from . import spell_buffs as sb

    cls_list: list[str] = []
    for entry in classes or []:
        for part in str(entry).split(","):
            part = part.strip()
            if part:
                cls_list.append(part)
    cleaned = _norm_classes(cls_list, allow_empty=True)
    return sb.cast_buffs_payload(cleaned, mode="off")



@app.get("/api/zones")
def api_list_zones():
    return {
        "zones": zones_mod.list_zones(),
        "count": len(zones_mod.list_zones()),
        "research_dir": str(zones_mod.zone_research_dir()),
    }


@app.get("/api/zones/{name}")
def api_get_zone(name: str, drops_mobs: Optional[str] = Query(default=None)):
    if drops_mobs is not None:
        return zones_mod.zone_detail_for_item(name, drops_mobs)
    z = zones_mod.get_zone(name)
    if not z:
        raise HTTPException(404, f"Zone not in zone-research: {name}")
    return z


@app.get("/api/zone-detail")
def api_zone_detail(
    zone: str = Query(...),
    drops_mobs: str = Query(default=""),
):
    return zones_mod.zone_detail_for_item(zone, drops_mobs)


@app.post("/api/inventory/parse")
def api_inventory_parse(body: InventoryParseRequest):
    if not (body.text or "").strip():
        raise HTTPException(400, "Provide Inventory.txt contents in text")
    try:
        return inventory_mod.parse_inventory_tsv(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/inventory/import")
def api_inventory_import(body: InventoryParseRequest):
    """Alias for parse — UI/desktop call this after file picker reads Inventory.txt."""
    if not (body.text or "").strip():
        raise HTTPException(
            400,
            "Provide Inventory.txt contents in text. "
            "Use Inventory.txt from in-game /outputfile inventory "
            "(not inventory.exe or other binaries).",
        )
    try:
        parsed = inventory_mod.parse_inventory_tsv(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "ok": True,
        "equipment": parsed.get("equipment") or {},
        "upgrade_hints": parsed.get("upgrade_hints") or {},
        "worn": parsed.get("worn") or [],
        "all_items": parsed.get("all_items") or [],
        "unmatched": parsed.get("unmatched") or [],
        "unmatched_count": parsed.get("unmatched_count", 0),
        "skipped_count": parsed.get("skipped_count", 0),
        "skipped": parsed.get("skipped") or [],
        "warnings": parsed.get("warnings") or [],
        "note": parsed.get("note") or "",
    }


@app.post("/api/inventory/upgrade-suggestions")
def api_upgrade_suggestions(body: UpgradeSuggestRequest):
    classes = _norm_classes(body.classes, allow_empty=True)
    if not classes:
        raise HTTPException(400, "Select at least one class (up to 3)")
    equipment = dict(body.equipment or {})
    parsed = None
    if body.inventory_text:
        try:
            parsed = inventory_mod.parse_inventory_tsv(body.inventory_text)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        equipment = {**equipment, **(parsed.get("equipment") or {})}
    level = max(1, min(50, int(body.character_level or 50)))
    try:
        out = inventory_mod.suggest_upgrades(
            classes,
            equipment,
            upgrade=max(0, min(10, int(body.upgrade))),
            character_level=level,
            prefer_ranged_damage=bool(body.prefer_ranged_damage),
            mode=body.mode or "ai",
            priority_stat=body.priority_stat or "HP",
            primary_stats=body.primary_stats,
            secondary_stats=body.secondary_stats,
            tertiary_stats=body.tertiary_stats,
            maximize_hp_regen=bool(body.maximize_hp_regen),
            fetch_quest_guides=bool(body.fetch_quest_guides),
        )
    except Exception as e:
        # Never 500 the UI after inventory import — return empty suggestions with note
        out = {
            "suggestions": [],
            "equipment_compare": [],
            "bis_summary": None,
            "equipment": {str(k).upper(): v for k, v in (equipment or {}).items() if v},
            "error": f"Upgrade suggestions unavailable: {e}",
            "note": (
                "Quest wiki / zone research failures should not block this; "
                "retry after selecting classes. No invented stats."
            ),
        }
    if parsed is not None:
        out["parsed"] = {
            "equipment": parsed.get("equipment"),
            "upgrade_hints": parsed.get("upgrade_hints"),
            "worn_count": len(parsed.get("worn") or []),
            "skipped_count": parsed.get("skipped_count"),
        }
    return out


@app.get("/api/quest-guide")
def api_quest_guide(name: str = Query(...), fetch: bool = Query(default=True)):
    """Quest steps from cache/eqlwiki for a quest name (never invented)."""
    from . import quest_guides as qg
    return qg.ensure_quest_guide(name, fetch=fetch)


@app.get("/api/help/inventory")
def api_help_inventory():
    """Serve HELP_BUTTON.md content from data/ or frontend/public."""
    for cand in (
        APP_ROOT / "data" / "HELP_BUTTON.md",
        APP_ROOT / "frontend" / "public" / "HELP_BUTTON.md",
        APP_ROOT / "data" / "log-research" / "HELP_BUTTON.md",
        Path("/workspace/eq-legends/log-research/HELP_BUTTON.md"),
    ):
        if cand.exists():
            return {"markdown": cand.read_text(encoding="utf-8"), "path": str(cand)}
    raise HTTPException(404, "HELP_BUTTON.md not found")


@app.post("/api/export/xlsx")
def export_xlsx(body: ExportRequest | None = None):
    classes = _norm_classes(body.classes if body else None, allow_empty=True)
    if not classes:
        classes = list(engine.DEFAULT_TRIO)  # export convenience only — not UI default
    helper = APP_ROOT / "scripts" / "run_planner_export.py"
    venv_py = APP_ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    cmd = [py, str(helper), *classes] if helper.exists() else [py, str(LEGENDS / "build_planner.py")]
    try:
        export_cwd = str(LEGENDS) if (LEGENDS / "build_planner.py").exists() else str(APP_ROOT)
        proc = subprocess.run(cmd, cwd=export_cwd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, f"Export timed out: {e}") from e
    xlsx = xlsx_dir() / "EQ_Legends_BiS.xlsx"
    return {
        "ok": proc.returncode == 0,
        "path": str(xlsx) if xlsx.exists() else None,
        "classes": classes,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1500:],
        "download": "/api/export/xlsx/file" if xlsx.exists() else None,
        "outputs": {
            "xlsx": str(xlsx) if xlsx.exists() else None,
            "xlsx_fixed": str(xlsx_dir() / "EQ_Legends_BiS_fixed.xlsx")
            if (xlsx_dir() / "EQ_Legends_BiS_fixed.xlsx").exists()
            else None,
            "xlsx_size": xlsx.stat().st_size if xlsx.exists() else None,
        },
    }


@app.get("/api/export/xlsx/file")
def download_xlsx():
    xlsx = xlsx_dir() / "EQ_Legends_BiS.xlsx"
    if not xlsx.exists():
        raise HTTPException(404, "XLSX not found")
    return FileResponse(
        xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="EQ_Legends_BiS.xlsx",
    )


def _mount_spa() -> None:
    """Serve built frontend when EQ_PACKAGED=1 or frontend/dist exists."""
    dist = frontend_dist()
    if not dist.exists() or not (dist / "index.html").exists():
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    def spa_index():
        # Avoid stale Electron/Chromium caches of the SPA shell after updates
        return FileResponse(
            dist / "index.html",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise HTTPException(404, "Not found")
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(
            dist / "index.html",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )


if packaged_mode() or FRONTEND_DIST.exists():
    _mount_spa()
