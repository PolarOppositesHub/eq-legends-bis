"""REST and SSE endpoints under ``/api/parser``."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .service import LogRejected, ParserService

router = APIRouter(prefix="/api/parser", tags=["parser"])

_service: ParserService | None = None


def get_service() -> ParserService:
    global _service
    if _service is None:
        db = os.environ.get("EQ_PARSER_DB") or None
        _service = ParserService(db_path=db)
    return _service


def reset_service(service: ParserService | None = None) -> None:
    """Test hook. Production callers leave the process-wide service in place."""
    global _service
    _service = service


class ConfigBody(BaseModel):
    eq_install_folder: str | None = None
    idle_seconds: float | None = Field(default=None, gt=0, le=3600)


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
    return get_service().list_fights(character=character, limit=limit, offset=offset)


@router.get("/fights/{fight_id}")
def get_fight(fight_id: int, merge_pets: bool = True) -> dict[str, Any]:
    detail = get_service().fight_detail(fight_id, merge_pets=merge_pets)
    if detail is None:
        raise HTTPException(404, "Fight not found")
    return detail


@router.post("/pets")
def post_pets(body: PetBody) -> dict[str, Any]:
    if not body.character.strip() or not body.pet.strip():
        raise HTTPException(400, "character and pet are required")
    owner = body.owner.strip() if isinstance(body.owner, str) and body.owner.strip() else None
    return get_service().set_pet_owner(body.character.strip(), body.pet.strip(), owner)


@router.get("/pets")
def get_pets(character: str) -> dict[str, Any]:
    return {"character": character, "pets": get_service().list_pets(character)}


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent Events for replay progress and live fight updates."""
    hub = get_service().hub
    queue = hub.subscribe()

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
