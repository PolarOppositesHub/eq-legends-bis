"""Settings and sync routes. The event log lives in the sidecar; Electron does OneDrive sign-in."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .currencies import get_book
from .parser.discover import default_user_data
from .sync.engine import SyncEngine
from .sync.layout import SyncError

router = APIRouter(prefix="/api/sync", tags=["sync"])

_engine: SyncEngine | None = None
_lock = threading.Lock()


def get_engine() -> SyncEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                engine = SyncEngine(default_user_data())
                book = get_book()
                book.sync_listener = engine.on_currency
                try:
                    from .parser.api import get_service
                    get_service().sync_listener = _identity_listener(engine)
                except Exception:
                    pass
                _engine = engine
    return _engine


def _identity_listener(engine: SyncEngine):
    def listener(character: str, hint: dict[str, Any]) -> None:
        engine.on_currency(character, hint) if hint.get("type") == "currency" else _queue_identity(engine, character, hint)
    return listener


def _queue_identity(engine: SyncEngine, character: str, hint: dict[str, Any]) -> None:
    """Parser identity uses the same queue as other manual events."""
    from .sync.model import make_event, new_id
    payload = dict(hint.get("payload") or {})
    event = make_event(
        event_id=new_id(),
        ts=str(hint.get("ts") or ""),
        device_id=engine.device_id,
        source="manual",
        event_type="parser_identity",
        payload=payload,
    )
    try:
        engine._queue_event(character, event)
    except Exception:
        return


class SettingsBody(BaseModel):
    provider: str | None = None
    folder: str | None = None
    device_name: str | None = None


class OneDriveBody(BaseModel):
    access_token: str = ""
    account: str = ""


class OneDriveNotice(BaseModel):
    error: str = ""
    auth_expired: bool = False
    reauth: bool = False


class SnapshotBody(BaseModel):
    characters: dict[str, Any] = Field(default_factory=dict)


def _fill_local(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Currency rows and the parser override already live in the sidecar."""
    characters = snapshot.setdefault("characters", {})
    if not isinstance(characters, dict):
        characters = {}
        snapshot["characters"] = characters
    try:
        book = get_book()
        stored = book._data.get("characters") or {}
        for name, state in stored.items():
            row = characters.setdefault(name, {})
            if "currency_entries" not in row:
                row["currency_entries"] = list(state.get("entries") or [])
    except Exception:
        pass
    try:
        from .parser.api import get_service
        service = get_service()
        names = list(characters.keys())
        with service.db.lock:
            extra = [
                row[0]
                for row in service.db.conn.execute("SELECT character FROM class_overrides").fetchall()
            ]
        for name in list(dict.fromkeys([*names, *extra])):
            with service.db.lock:
                override = service.db.get_override(name)
            if not override:
                continue
            row = characters.setdefault(name, {})
            if "identity" not in row:
                row["identity"] = {
                    "classes": override.get("classes"),
                    "level": override.get("level"),
                    "ts": override.get("ts"),
                    "cleared": False,
                }
    except Exception:
        pass
    return snapshot


def _apply(engine: SyncEngine) -> None:
    try:
        engine.apply_currency(get_book())
    except Exception:
        pass
    try:
        from .parser.api import get_service
        service = get_service()
        engine.apply_identity(service.apply_synced_identity)
    except Exception:
        pass


@router.get("/status")
def sync_status() -> dict[str, Any]:
    return get_engine().status()


@router.post("/settings")
def sync_settings(body: SettingsBody) -> dict[str, Any]:
    try:
        return get_engine().configure(
            provider=body.provider,
            folder=body.folder,
            device_name=body.device_name,
        )
    except SyncError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/onedrive")
def sync_onedrive(body: OneDriveBody) -> dict[str, Any]:
    return get_engine().set_onedrive_session(body.access_token, body.account)


@router.post("/onedrive/sign-out")
def sync_onedrive_out() -> dict[str, Any]:
    return get_engine().clear_onedrive_session()


@router.post("/onedrive/notice")
def sync_onedrive_notice(body: OneDriveNotice) -> dict[str, Any]:
    return get_engine().note_onedrive_error(body.error, auth_expired=body.auth_expired, reauth=body.reauth)


@router.post("/onedrive/test")
def sync_onedrive_test() -> dict[str, Any]:
    return get_engine().test_onedrive()


@router.post("/capture")
def sync_capture(body: SnapshotBody) -> dict[str, Any]:
    engine = get_engine()
    snapshot = _fill_local({"characters": body.characters})
    try:
        result = engine.capture(snapshot)
    except SyncError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@router.post("/now")
def sync_now() -> dict[str, Any]:
    engine = get_engine()
    status = engine.sync()
    if status.get("status") in {"ok", "waiting"}:
        _apply(engine)
    status["projection"] = engine.projection()
    return status


@router.get("/projection")
def sync_projection() -> dict[str, Any]:
    return get_engine().projection()
