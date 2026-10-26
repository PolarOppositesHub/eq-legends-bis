"""REST and SSE endpoints under ``/api/parser``."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .service import LogRejected, ParserBusy, ParserService

router = APIRouter(prefix="/api/parser", tags=["parser"])

_service: ParserService | None = None


_service_lock = threading.Lock()


def get_service() -> ParserService:
    """Process-wide parser service.

    FastAPI runs sync endpoints on a thread pool, so the Parser tab's first
    requests arrive together. Without the lock each one built its own
    ParserService (own SQLite connection, own 1.1.0 -> 1.1.1 rebuild thread)
    and all but one rebuild failed with "database is locked".
    """
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                db = os.environ.get("EQ_PARSER_DB") or None
                _service = ParserService(db_path=db)
    return _service


def busy_response(exc: ParserBusy) -> JSONResponse:
    """503 with a hint the Parser tab uses to wait for the rebuild quietly."""
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "rebuilding": True},
        headers={"Retry-After": "2"},
    )


def reset_service(service: ParserService | None = None) -> None:
    """Test hook. Production callers leave the process-wide service in place."""
    global _service
    _service = service


class ConfigBody(BaseModel):
    eq_install_folder: str | None = None
    idle_seconds: float | None = Field(default=None, gt=0, le=3600)
    # 0 keeps every saved fight. A positive value is a maximum age in days.
    fight_retention_days: int | None = Field(default=None, ge=0, le=36500)


class ClearHistoryBody(BaseModel):
    character: str


class LoadBody(BaseModel):
    path: str
    idle_seconds: float | None = Field(default=None, gt=0, le=3600)


class LiveBody(BaseModel):
    path: str | None = None
    on: bool = True
    from_end: bool = True
    backfill_seconds: float | None = Field(default=None, ge=0)


class PetBody(BaseModel):
    character: str
    pet: str
    owner: str | None = None


class CandidateBody(BaseModel):
    character: str
    pet: str
    action: str
    owner: str | None = None


class GroupBody(BaseModel):
    character: str
    member: str
    action: str


class FavouriteBody(BaseModel):
    character: str
    kind: str
    name: str
    starred: bool = True


class CompanionDurationBody(BaseModel):
    character: str
    loadout: str
    spell: str
    seconds: int | None = None


class CompanionManualBody(BaseModel):
    character: str
    loadout: str
    spell: str
    target: str = "You"
    seconds: int | None = None
    action: str = "start"


class CompanionRespawnBody(BaseModel):
    character: str
    zone: str = ""
    mob: str
    seconds: int | None = None


class CompanionExaltationBody(BaseModel):
    character: str = ""
    loadout: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class CompanionExaltationNoteBody(BaseModel):
    character: str
    loadout: str
    key: str
    target: str = ""


class CompanionResistBody(BaseModel):
    character: str = ""
    loadout: str
    classes: list[str] = Field(default_factory=list)
    level: int | None = None
    race: str | None = None
    worn: list[dict[str, Any]] = Field(default_factory=list)
    assume_max_aas: bool = False
    save_as: str | None = None


class CompanionExportBody(BaseModel):
    character: str = ""
    ui: dict[str, Any] | None = None


class CompanionImportBody(BaseModel):
    character: str
    profile: dict[str, Any]


class LockoutBody(BaseModel):
    character: str
    mob: str
    note: str | None = None
    clear: bool = False


class MoteGradeBody(BaseModel):
    grade: int | None = Field(default=None, ge=1, le=10)


class WishesBody(BaseModel):
    character: str
    wishes: list[str] = Field(default_factory=list)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, LogRejected):
        return HTTPException(400, str(exc))
    return HTTPException(400, str(exc))


@router.get("/config")
def get_config() -> dict[str, Any]:
    return get_service().config()


@router.post("/config")
def post_config(body: ConfigBody) -> dict[str, Any]:
    service = get_service()
    if body.eq_install_folder is not None:
        service.set_eq_folder(body.eq_install_folder)
    if body.idle_seconds is not None:
        service.set_idle(body.idle_seconds)
    if body.fight_retention_days is not None:
        service.set_retention_days(body.fight_retention_days)
    return service.config()


@router.get("/logs")
def get_logs(root: str | None = None) -> dict[str, Any]:
    return get_service().list_logs(root)


@router.post("/load")
def post_load(body: LoadBody) -> dict[str, Any]:
    try:
        return get_service().replay(body.path, idle_seconds=body.idle_seconds, finalize=True)
    except (FileNotFoundError, LogRejected, OSError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/live")
def post_live(body: LiveBody) -> dict[str, Any]:
    service = get_service()
    if not body.on:
        return service.stop_live()
    path = body.path
    if not path:
        logs = service.list_logs().get("logs") or []
        if not logs:
            raise HTTPException(404, "No eqlog_*.txt found under the EQ install Logs folder")
        path = logs[0]["path"]
    try:
        return service.start_live(path, from_end=body.from_end, backfill_seconds=body.backfill_seconds)
    except (FileNotFoundError, LogRejected, OSError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/fights")
def get_fights(
    character: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    service = get_service()
    with service.read_guard():
        return service.list_fights(character=character, limit=limit, offset=offset)


@router.get("/loot")
def get_loot(
    character: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Loot, give, and merge events already stored while the log is read."""
    service = get_service()
    with service.read_guard():
        return service.list_economy(character=character, limit=limit, offset=offset)


@router.get("/fights/{fight_id}")
def get_fight(fight_id: int, merge_pets: bool = True) -> dict[str, Any]:
    service = get_service()
    with service.read_guard():
        detail = service.fight_detail(fight_id, merge_pets=merge_pets)
    if detail is None:
        raise HTTPException(404, "Fight not found")
    return detail


@router.get("/fights/{fight_id}/timeline")
def get_fight_timeline(fight_id: int, ability: str | None = None) -> dict[str, Any]:
    """Per-second damage and healing, re-read from the fight's log byte range."""
    service = get_service()
    with service.read_guard():
        detail = service.fight_timeline(fight_id, ability=ability)
    if detail is None:
        raise HTTPException(404, "Fight not found")
    return detail


@router.get("/fights/{fight_id}/lines")
def get_fight_lines(fight_id: int) -> dict[str, Any]:
    """Drill-down text re-read from the fight's log byte range."""
    service = get_service()
    with service.read_guard():
        detail = service.fight_lines(fight_id)
    if detail is None:
        raise HTTPException(404, "Fight not found")
    return detail


@router.post("/history/clear")
def post_clear_history(body: ClearHistoryBody) -> dict[str, Any]:
    if not body.character.strip():
        raise HTTPException(400, "character is required")
    return get_service().clear_character_history(body.character.strip())


@router.post("/pets")
def post_pets(body: PetBody) -> dict[str, Any]:
    if not body.character.strip() or not body.pet.strip():
        raise HTTPException(400, "character and pet are required")
    owner = body.owner.strip() if isinstance(body.owner, str) and body.owner.strip() else None
    return get_service().set_pet_owner(body.character.strip(), body.pet.strip(), owner)


@router.get("/pets")
def get_pets(character: str) -> dict[str, Any]:
    service = get_service()
    with service.read_guard():
        return {"character": character, "pets": service.list_pets(character)}


@router.get("/roster")
def get_roster(character: str) -> dict[str, Any]:
    if not character.strip():
        raise HTTPException(400, "character is required")
    service = get_service()
    with service.read_guard():
        return service.roster(character.strip())


@router.post("/candidates")
def post_candidates(body: CandidateBody) -> dict[str, Any]:
    character = body.character.strip()
    pet = body.pet.strip()
    action = body.action.strip().lower()
    if not character or not pet:
        raise HTTPException(400, "character and pet are required")
    service = get_service()
    if action == "dismiss":
        return service.dismiss_candidate(character, pet)
    if action == "confirm":
        owner = body.owner.strip() if isinstance(body.owner, str) and body.owner.strip() else character
        return service.set_pet_owner(character, pet, owner)
    raise HTTPException(400, "action must be confirm or dismiss")


@router.post("/group")
def post_group(body: GroupBody) -> dict[str, Any]:
    character = body.character.strip()
    member = body.member.strip()
    action = body.action.strip().lower()
    if not character or not member:
        raise HTTPException(400, "character and member are required")
    service = get_service()
    try:
        if action == "add":
            return service.add_allow(character, member)
        if action == "remove":
            return service.remove_allow(character, member)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    raise HTTPException(400, "action must be add or remove")


class IdentityBody(BaseModel):
    character: str
    classes: Any = None
    level: int | None = None
    action: str = "set"


class AlertRuleBody(BaseModel):
    rule: dict[str, Any]


class AlertShareBody(BaseModel):
    text: str


@router.post("/identity")
def post_identity(body: IdentityBody) -> dict[str, Any]:
    character = body.character.strip()
    if not character:
        raise HTTPException(400, "character is required")
    service = get_service()
    try:
        if body.action.strip().lower() == "clear":
            return service.clear_identity(character)
        return service.set_identity(character, body.classes, body.level)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/meters")
def get_meters(character: str, scope: str = "fight") -> dict[str, Any]:
    if not character.strip():
        raise HTTPException(400, "character is required")
    service = get_service()
    with service.read_guard():
        return service.meters(character.strip(), scope)


@router.get("/alerts")
def get_alerts() -> dict[str, Any]:
    service = get_service()
    with service.read_guard():
        return service.list_alert_rules()


@router.post("/alerts")
def post_alert(body: AlertRuleBody) -> dict[str, Any]:
    try:
        return get_service().save_alert_rule(body.rule or {})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/alerts/import")
def post_alert_import(body: AlertShareBody) -> dict[str, Any]:
    try:
        return get_service().import_alert_share(body.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/alerts/recent")
def get_alert_recent() -> dict[str, Any]:
    service = get_service()
    with service.read_guard():
        return service.recent_alerts()


def _wishes(wish: list[str] | None) -> list[str] | None:
    if not wish:
        return None
    return [item for item in wish if isinstance(item, str) and item.strip()]


@router.get("/dashboards/overview")
def get_dashboard_overview(
    character: str = "",
    wish: list[str] = Query(default=[]),
) -> dict[str, Any]:
    return get_service().dashboard_overview(character, wishes=_wishes(wish))


@router.get("/dashboards/loot")
def get_dashboard_loot(
    character: str = "",
    wish: list[str] = Query(default=[]),
    limit: int = Query(default=300, ge=1, le=2000),
) -> dict[str, Any]:
    return get_service().dashboard_loot(character, wishes=_wishes(wish), limit=limit)


@router.get("/dashboards/leveling")
def get_dashboard_leveling(character: str = "") -> dict[str, Any]:
    return get_service().dashboard_leveling(character)


@router.get("/dashboards/raids")
def get_dashboard_raids(character: str = "") -> dict[str, Any]:
    return get_service().dashboard_raids(character)


@router.get("/dashboards/considered")
def get_dashboard_considered(
    character: str = "",
    limit: int = Query(default=40, ge=1, le=200),
) -> dict[str, Any]:
    return get_service().dashboard_considered(character, limit=limit)


@router.get("/dashboards/mob")
def get_dashboard_mob(character: str = "", name: str = "") -> dict[str, Any]:
    if not name.strip():
        raise HTTPException(400, "name is required")
    return get_service().dashboard_mob(character, name)


@router.get("/dashboards/overlay")
def get_dashboard_overlay(character: str = "", kind: str = "xp") -> dict[str, Any]:
    return get_service().dashboard_overlay(character, kind)


@router.post("/dashboards/favourites")
def post_dashboard_favourite(body: FavouriteBody) -> dict[str, Any]:
    try:
        return get_service().set_favourite(body.character, body.kind, body.name, body.starred)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/dashboards/lockouts")
def post_dashboard_lockout(body: LockoutBody) -> dict[str, Any]:
    try:
        return get_service().set_user_lockout(body.character, body.mob, body.note, clear=body.clear)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/dashboards/mote-grade")
def post_dashboard_mote_grade(body: MoteGradeBody) -> dict[str, Any]:
    return get_service().set_mote_notable_grade(body.grade)


@router.post("/dashboards/wishes")
def post_dashboard_wishes(body: WishesBody) -> dict[str, Any]:
    if not body.character.strip():
        raise HTTPException(400, "character is required")
    return get_service().remember_wishes(body.character, body.wishes)


def _loadout(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        raise HTTPException(400, "loadout is required")
    return cleaned


@router.get("/companion/buffs")
def get_companion_buffs(character: str = "", loadout: str = "") -> dict[str, Any]:
    return get_service().companion_buffs(character, _loadout(loadout))


@router.post("/companion/duration")
def post_companion_duration(body: CompanionDurationBody) -> dict[str, Any]:
    try:
        return get_service().companion_set_duration(body.character, _loadout(body.loadout), body.spell, body.seconds)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/companion/manual")
def post_companion_manual(body: CompanionManualBody) -> dict[str, Any]:
    try:
        return get_service().companion_manual_buff(
            body.character,
            _loadout(body.loadout),
            body.spell,
            body.target,
            body.seconds,
            "clear" if body.action == "clear" else "start",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/companion/respawns")
def get_companion_respawns(character: str = "") -> dict[str, Any]:
    return get_service().companion_respawns(character)


@router.post("/companion/respawn")
def post_companion_respawn(body: CompanionRespawnBody) -> dict[str, Any]:
    try:
        return get_service().companion_set_respawn(body.character, body.zone, body.mob, body.seconds)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/companion/maps")
def get_companion_maps(character: str = "") -> dict[str, Any]:
    return get_service().companion_maps(character)


@router.post("/companion/exaltations")
def post_companion_exaltations(body: CompanionExaltationBody) -> dict[str, Any]:
    return get_service().companion_exaltations(body.character, _loadout(body.loadout), body.items)


@router.post("/companion/exaltation-note")
def post_companion_exaltation_note(body: CompanionExaltationNoteBody) -> dict[str, Any]:
    try:
        return get_service().companion_set_exaltation_note(body.character, _loadout(body.loadout), body.key, body.target)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/companion/resists")
def post_companion_resists(body: CompanionResistBody) -> dict[str, Any]:
    return get_service().companion_resists(
        body.character,
        _loadout(body.loadout),
        body.classes,
        body.level,
        body.race,
        body.worn,
        body.assume_max_aas,
        body.save_as,
    )


@router.post("/companion/export")
def post_companion_export(body: CompanionExportBody) -> dict[str, Any]:
    return get_service().companion_export(body.character, body.ui)


@router.post("/companion/import")
def post_companion_import(body: CompanionImportBody) -> dict[str, Any]:
    try:
        return get_service().companion_import(body.character, body.profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/companion/perf")
def get_companion_perf() -> dict[str, Any]:
    from .companion import perf_readout

    return perf_readout()


@router.get("/companion/feedback")
def get_companion_feedback():
    from fastapi.responses import Response

    data = get_service().companion_feedback()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=eq-legends-bis-feedback.zip"},
    )


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent Events for replay progress and live fight updates."""
    hub = get_service().hub
    raw = (request.query_params.get("events") or "").strip()
    types = [part.strip() for part in raw.split(",") if part.strip()] or None
    queue = hub.subscribe(types)

    async def generate():
        yield _frame("hello", {"ok": True})
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield _frame(str(item.get("type") or "message"), item)
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"
