"""Typed combat-log events.

Amounts are integers, matching the log. ``amount_full`` is the parenthetical
heal total when the line prints ``actual (full)``; overheal is full - actual.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedEvent:
    kind: str
    source: str | None = None
    target: str | None = None
    amount: int | None = None
    amount_full: int | None = None
    spell: str | None = None
    verb: str | None = None
    damage_type: str | None = None
    modifiers: tuple[str, ...] = ()
    over_time: bool = False
    avoidance: str | None = None
    item: str | None = None
    qty: int | None = None
    mode: str | None = None
    coin_text: str | None = None
    coin_copper: int | None = None
    result_item: str | None = None
    result_tier: int | None = None
    zone: str | None = None
    instance: dict | None = None
    xp_pct: float | None = None
    party_xp: bool = False
    level: int | None = None
    ability_points: int | None = None
    ability_total: int | None = None
    pet: str | None = None
    owner: str | None = None
    evidence: str | None = None
    player_name: str | None = None
    player_classes: str | None = None
    player_level: int | None = None
    ts: datetime | None = None
    text: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def overheal(self) -> int | None:
        if self.amount is None or self.amount_full is None:
            return None
        return self.amount_full - self.amount
