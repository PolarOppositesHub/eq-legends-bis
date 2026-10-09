"""REST routes for the BiS mote path and Plane of Sky tracker."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .requirements import build_upgrade_plan, ledger_holdings, merge_rune_counts, offers_from_text, plane_of_sky

router = APIRouter(prefix="/api/requirements", tags=["requirements"])


class UpgradeItem(BaseModel):
    id: str = ""
    name: str
    slot: str = ""
    score: float | None = None
    target_tier: int = Field(default=10, ge=0, le=10)
    current_tier: int | None = None
    progress: int = Field(default=0, ge=0)


class CopyRow(BaseModel):
    name: str = ""
    tier: int | None = None
    count: int = 1


class UpgradeBody(BaseModel):
    character: str = ""
    items: list[UpgradeItem] = Field(default_factory=list)
    copies: list[CopyRow] = Field(default_factory=list)
    holdings: dict[str, int] | None = None
    void_touched: int | None = None


class OfferRow(BaseModel):
    item: str = ""
    qty: int = 1
    npc: str = ""


class OwnedRow(BaseModel):
    name: str = ""
    count: int = 1


class PosBody(BaseModel):
    character: str = ""
    achievements_text: str = ""
    offers: list[OfferRow] = Field(default_factory=list)
    offer_text: str = ""
    owned: list[OwnedRow] = Field(default_factory=list)
    manual: dict[str, str] = Field(default_factory=dict)
    ignored: list[str] = Field(default_factory=list)
    goal_classes: list[str] = Field(default_factory=list)
    linked_names: list[str] = Field(default_factory=list)
    wind_runes: dict[str, int] | None = None
    inventory_runes: dict[str, int] | None = None


@router.post("/upgrades")
def post_upgrades(body: UpgradeBody) -> dict[str, Any]:
    holdings = body.holdings
    void_touched = body.void_touched
    return build_upgrade_plan(
        [item.model_dump() for item in body.items],
        [row.model_dump() for row in body.copies],
        character=body.character,
        holdings=holdings,
        void_touched=void_touched,
    )


@router.post("/pos")
def post_pos(body: PosBody) -> dict[str, Any]:
    offers = [row.model_dump() for row in body.offers]
    offers.extend(offers_from_text(body.offer_text))
    runes = body.wind_runes
    if runes is None and body.character.strip():
        runes = ledger_holdings(body.character).get("wind_runes") or {}
    runes = merge_rune_counts(runes or {}, body.inventory_runes)
    return plane_of_sky(
        achievements_text=body.achievements_text,
        offers=offers,
        owned=[row.model_dump() for row in body.owned],
        wind_runes=runes or {},
        manual=body.manual,
        ignored=body.ignored,
        goal_classes=body.goal_classes,
        linked_names=body.linked_names,
    )
