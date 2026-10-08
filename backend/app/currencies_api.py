"""REST routes for the per-character currency ledger."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .currencies import get_book
from .parser.api import get_service
from .parser.service import ParserBusy

router = APIRouter(prefix="/api/currencies", tags=["currencies"])


class AnchorBody(BaseModel):
    character: str
    currency: str
    count: int = Field(ge=0)
    ts: str | None = None


class UsedBody(BaseModel):
    character: str
    currency: str
    qty: int = Field(ge=0)
    ts: str | None = None


class CondenseBody(BaseModel):
    character: str
    currency: str
    ts: str | None = None


class UndoBody(BaseModel):
    character: str
    entry_id: str


class ReconcileBody(BaseModel):
    character: str
    bag_counts: dict[str, Any] = Field(default_factory=dict)
    imported_at: str | None = None


def _view_or_400(character: str, warning: str | None = None) -> dict[str, Any]:
    try:
        return get_book().view(character, warning=warning)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _sync(character: str) -> str | None:
    """Apply the parser feed. A rebuild leaves the ledger readable."""
    try:
        events = get_service().currency_feed(character)
        get_book().sync(character, events)
    except ParserBusy as exc:
        return str(exc)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        return f"parser feed unavailable: {exc}"
    return None


@router.get("")
def get_currencies(character: str = Query(default="")) -> dict[str, Any]:
    if not (character or "").strip():
        raise HTTPException(400, "character is required")
    warning = _sync(character)
    return _view_or_400(character, warning)


@router.post("/anchor")
def post_anchor(body: AnchorBody) -> dict[str, Any]:
    try:
        get_book().set_anchor(body.character, body.currency, body.count, body.ts)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _view_or_400(body.character)


@router.post("/used")
def post_used(body: UsedBody) -> dict[str, Any]:
    try:
        get_book().use(body.character, body.currency, body.qty, body.ts)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _view_or_400(body.character)


@router.post("/condense")
def post_condense(body: CondenseBody) -> dict[str, Any]:
    try:
        get_book().condense(body.character, body.currency, body.ts)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _view_or_400(body.character)


@router.post("/undo")
def post_undo(body: UndoBody) -> dict[str, Any]:
    try:
        get_book().undo(body.character, body.entry_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _view_or_400(body.character)


@router.post("/reconcile")
def post_reconcile(body: ReconcileBody) -> dict[str, Any]:
    try:
        get_book().reconcile(body.character, body.bag_counts, body.imported_at)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _view_or_400(body.character)
