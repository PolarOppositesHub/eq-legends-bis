"""Fight segmentation.

A fight starts on the first damage event between a friendly (self, group, or
pet) and an NPC. It ends when every engaged NPC is dead, or after ``idle``
seconds with no damage or miss. Heals do not keep a fight open: this log is
full of tiny out-of-combat self-heals.

Overlapping NPCs share one encounter. DPS is damage over the source's active
window. SDPS is the same damage over the fight's duration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import ParsedEvent
from .sources import ActorContext, canonical_name, involve_friendly, is_you, normalize_article

DAMAGE_KINDS = {"melee", "spell", "dot", "ds"}
MISS_KINDS = {"miss", "avoid"}
MIN_SECONDS = 1.0


def _canon(name: str | None, character: str) -> str | None:
    if name is None:
        return None
    named = canonical_name(name, character)
    if named is None:
        return None
    if named in {"himself", "herself", "itself"}:
        return named
    if is_you(name) or named == character:
        return character
    return normalize_article(named)


@dataclass
class SourceAgg:
    source: str
    source_kind: str
    owner: str | None = None
    damage: int = 0
    damage_taken: int = 0
    hits: int = 0
    misses: int = 0
    crits: int = 0
    max_hit: int = 0
    heals: int = 0
    heals_full: int = 0
    melee: int = 0
    spell_dmg: int = 0
    dot: int = 0
    ds: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    def add_damage(self, amount: int, kind: str, crit: bool, ts: datetime | None) -> None:
        self.damage += amount
        self.hits += 1
        if crit:
            self.crits += 1
        if amount > self.max_hit:
            self.max_hit = amount
        if kind == "melee":
            self.melee += amount
        elif kind == "spell":
            self.spell_dmg += amount
        elif kind == "dot":
            self.dot += amount
        elif kind == "ds":
            self.ds += amount
        if ts is not None:
            if self.first_ts is None or ts < self.first_ts:
                self.first_ts = ts
            if self.last_ts is None or ts > self.last_ts:
                self.last_ts = ts

    def to_row(self, fight_seconds: float) -> dict:
        active = MIN_SECONDS
        if self.first_ts and self.last_ts:
            active = max(MIN_SECONDS, (self.last_ts - self.first_ts).total_seconds())
        swings = self.hits + self.misses
        return {
            "source": self.source,
            "kind": self.source_kind,
            "owner": self.owner,
            "damage": self.damage,
            "damage_taken": self.damage_taken,
            "hits": self.hits,
            "misses": self.misses,
            "crits": self.crits,
            "max_hit": self.max_hit,
            "heals": self.heals,
            "heals_full": self.heals_full,
            "overheal": max(0, self.heals_full - self.heals) if self.heals_full else 0,
            "melee": self.melee,
            "spell": self.spell_dmg,
            "dot": self.dot,
            "ds": self.ds,
            "dps": self.damage / active if self.damage else 0.0,
            "sdps": self.damage / fight_seconds if self.damage else 0.0,
            "active_seconds": active if self.hits else 0.0,
            "hit_pct": (100.0 * self.hits / swings) if swings else 0.0,
            "crit_pct": (100.0 * self.crits / self.hits) if self.hits else 0.0,
            "first_ts": _iso(self.first_ts),
            "last_ts": _iso(self.last_ts),
        }


@dataclass
class FightState:
    character: str
    zone: str | None = None
    instance: dict | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    last_combat_ts: datetime | None = None
    targets: dict[str, bool] = field(default_factory=dict)
    sources: dict[str, SourceAgg] = field(default_factory=dict)
    player_died: bool = False
    open: bool = True
    db_id: int | None = None

    def seconds(self) -> float:
        if self.start_ts and self.end_ts:
            return max(MIN_SECONDS, (self.end_ts - self.start_ts).total_seconds())
        return MIN_SECONDS

    def touch(self, ts: datetime | None, offset: int | None) -> None:
        if ts is not None:
            if self.start_ts is None or ts < self.start_ts:
                self.start_ts = ts
            if self.end_ts is None or ts > self.end_ts:
                self.end_ts = ts
        if offset is not None:
            if self.start_offset is None or offset < self.start_offset:
                self.start_offset = offset
            if self.end_offset is None or offset > self.end_offset:
                self.end_offset = offset

    def agg(self, name: str, kind: str, owner: str | None) -> SourceAgg:
        row = self.sources.get(name)
        if row is None:
            row = SourceAgg(source=name, source_kind=kind, owner=owner)
            self.sources[name] = row
        else:
            if kind != "unknown":
                row.source_kind = kind
            if owner:
                row.owner = owner
        return row

    def living_targets(self) -> bool:
        return any(self.targets.values())

    def all_dead(self) -> bool:
        return bool(self.targets) and not self.living_targets()

    def summary(self) -> dict:
        seconds = self.seconds()
        rows = [agg.to_row(seconds) for agg in self.sources.values()]
        friendly = {"self", "group", "pet"}
        dealt = sum(r["damage"] for r in rows if r["kind"] in friendly)
        yours = next((r for r in rows if r["kind"] == "self"), None)
        return {
            "id": self.db_id,
            "character": self.character,
            "zone": self.zone,
            "instance": self.instance,
            "start_ts": _iso(self.start_ts),
            "end_ts": _iso(self.end_ts),
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "duration_seconds": seconds,
            "targets": sorted(self.targets),
            "open": self.open,
            "player_died": self.player_died,
            "damage": dealt,
            "your_dps": yours["dps"] if yours else 0.0,
            "your_sdps": yours["sdps"] if yours else 0.0,
            "your_damage": yours["damage"] if yours else 0,
        }


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _crit(event: ParsedEvent) -> bool:
    return any(part.lower() == "critical" or part.lower().startswith("critical") for part in event.modifiers) or any(
        "critical" in part.lower() for part in event.modifiers
    )


class Segmenter:
    def __init__(self, character: str, idle_seconds: float = 30.0, on_roster=None, on_close=None) -> None:
        self.character = character
        self.idle = idle_seconds
        self.ctx = ActorContext(character)
        self.fight: FightState | None = None
        self.closed: list[FightState] = []
        self.zone: str | None = None
        self.instance: dict | None = None
        self.pending_charm_until: datetime | None = None
        self._charm_spell_at: datetime | None = None
        self.on_roster = on_roster
        self.on_close = on_close

    def _roster(self, op: str, **payload) -> None:
        if self.on_roster:
            self.on_roster(op, payload)

    def load_open(self, fight: FightState | None) -> None:
        self.fight = fight

    def gap_too_wide(self, ts: datetime | None) -> bool:
        if self.fight is None or ts is None or self.fight.last_combat_ts is None:
            return False
        return (ts - self.fight.last_combat_ts).total_seconds() > self.idle

    def close(self, ts: datetime | None = None) -> FightState | None:
        fight = self.fight
        if fight is None or not fight.open:
            self.fight = None
            return None
        if ts is not None:
            fight.touch(ts, None)
        fight.open = False
        self.closed.append(fight)
        self.fight = None
        if self.on_close:
            self.on_close(fight)
        return fight

    def _ensure(self, ts: datetime | None, offset: int | None) -> FightState:
        if self.fight is None or not self.fight.open:
            self.fight = FightState(
                character=self.character,
                zone=self.zone,
                instance=dict(self.instance) if self.instance else None,
            )
        self.fight.touch(ts, offset)
        if self.zone and not self.fight.zone:
            self.fight.zone = self.zone
            self.fight.instance = dict(self.instance) if self.instance else None
        return self.fight

    def _note_target(self, name: str | None, kind: str) -> None:
        if not name or kind != "npc" or self.fight is None:
            return
        self.fight.targets.setdefault(name, True)

    def _mark_dead(self, name: str | None) -> None:
        if not name or self.fight is None:
            return
        canon = _canon(name, self.character)
        if canon and canon in self.fight.targets:
            self.fight.targets[canon] = False

    def observe(self, event: ParsedEvent, offset: int | None = None) -> FightState | None:
        """Fold one event. Returns a fight that just closed, if any."""
        ts = event.ts
        self._apply_context(event, ts)
        if event.kind == "zone":
            return self.close(ts)

        if self.gap_too_wide(ts):
            self.close(self.fight.last_combat_ts if self.fight else ts)

        if event.kind in DAMAGE_KINDS and event.amount:
            return self._damage(event, offset)
        if event.kind in MISS_KINDS and event.avoidance != "protected":
            return self._miss(event, offset)
        if event.kind == "heal":
            self._heal(event, offset)
            return None
        if event.kind in {"slain", "death"}:
            return self._death(event, offset)
        if event.kind == "knockout" and self.fight and self.fight.open:
            self.fight.player_died = True
        return None

    def _apply_context(self, event: ParsedEvent, ts: datetime | None) -> None:
        for pet, owner, evidence in self.ctx.note_name_pets(event.source, event.target, event.pet):
            self._roster("pet", pet=pet, owner=owner, evidence=evidence)
        if event.kind == "group_join" and event.target and not is_you(event.target) and event.target != "You":
            self.ctx.add_group(event.target)
            self._roster("group_add", name=event.target)
        elif event.kind == "group_leave":
            if is_you(event.target) or event.target == "You":
                self.ctx.clear_group()
                self._roster("group_clear")
            elif event.target:
                self.ctx.remove_group(event.target)
                self._roster("group_remove", name=event.target)
        elif event.kind == "group_invite" and event.target and not is_you(event.target):
            self.ctx.note_player(event.target)
            self._roster("player", name=event.target)
        elif event.kind == "who" and event.player_name:
            self.ctx.note_player(event.player_name)
            self._roster(
                "player",
                name=event.player_name,
                classes=event.player_classes,
                level=event.player_level,
            )
        elif event.kind == "pet_tell" and event.pet:
            owner = self.character if is_you(event.owner) or event.owner == "You" else (event.owner or self.character)
            if self.ctx.bind_pet(event.pet, owner, "tell"):
                self._roster("pet", pet=event.pet, owner=owner, evidence="tell")
        elif event.kind == "pet_leader" and event.pet and event.owner:
            owner = self.character if is_you(event.owner) else event.owner
            if self.ctx.bind_pet(event.pet, owner, "leader"):
                self._roster("pet", pet=event.pet, owner=owner, evidence="leader")
        elif event.kind == "cast" and event.source and is_you(event.source):
            spell = (event.spell or "").strip()
            if spell == "Charm" or spell.startswith("Charm "):
                self._charm_spell_at = ts
                self.pending_charm_until = ts
        elif event.kind == "charm" and event.pet:
            if self._charm_recent(ts) and self.ctx.bind_pet(event.pet, self.character, "charm"):
                self.ctx.charmed.add(event.pet)
                self._roster("pet", pet=event.pet, owner=self.character, evidence="charm")
        elif event.kind == "charm_break":
            self._drop_charm(event.pet)
        elif event.kind == "zone":
            self.zone = event.zone
            self.instance = dict(event.instance or {})
            for pet in list(self.ctx.charmed):
                self._drop_charm(pet)
            self._charm_spell_at = None

    def _charm_recent(self, ts: datetime | None) -> bool:
        if self._charm_spell_at is None:
            return False
        if ts is None:
            return True
        return (ts - self._charm_spell_at).total_seconds() <= 15

    def _drop_charm(self, pet: str | None) -> None:
        if pet and pet in self.ctx.charmed:
            if pet not in self.ctx.manual_pets:
                self.ctx.pets.pop(pet, None)
                self.ctx.pet_evidence.pop(pet, None)
                self._roster("pet_clear", pet=pet)
            self.ctx.charmed.discard(pet)
        elif pet is None:
            for name in list(self.ctx.charmed):
                self._drop_charm(name)

    def _sides(self, event: ParsedEvent) -> tuple[str | None, str, str | None, str | None, str]:
        self.ctx.note_name_pets(event.source, event.target)
        source = _canon(event.source, self.character) if event.source else None
        target = _canon(event.target, self.character) if event.target else None
        if event.kind == "heal" and target in {"himself", "herself", "itself"} and source:
            target = source
        source_kind = self.ctx.kind_of(source) if source else "unknown"
        target_kind = self.ctx.kind_of(target) if target else "unknown"
        owner = self.ctx.owner_of(source) if source else None
        if owner and is_you(owner):
            owner = self.character
        elif owner:
            owner = _canon(owner, self.character)
        return source, source_kind, owner, target, target_kind

    def _damage(self, event: ParsedEvent, offset: int | None) -> FightState | None:
        source, source_kind, owner, target, target_kind = self._sides(event)
        if not involve_friendly(source_kind, target_kind):
            return None
        # Sourceless non-melee (environmental) does not start a fight.
        if event.kind == "ds" and source is None and (self.fight is None or not self.fight.open):
            return None
        fight = self._ensure(event.ts, offset)
        if source and event.amount:
            fight.agg(source, source_kind, owner).add_damage(
                int(event.amount), event.kind, _crit(event), event.ts
            )
        if target and target_kind in {"self", "group", "pet"} and event.amount:
            fight.agg(target, target_kind, self.ctx.owner_of(target)).damage_taken += int(event.amount)
        if source_kind in {"self", "group", "pet"} and target_kind == "npc":
            self._note_target(target, "npc")
        if target_kind in {"self", "group", "pet"} and source_kind == "npc":
            self._note_target(source, "npc")
        fight.last_combat_ts = event.ts or fight.last_combat_ts
        return None

    def _miss(self, event: ParsedEvent, offset: int | None) -> FightState | None:
        if self.fight is None or not self.fight.open:
            return None
        if self.gap_too_wide(event.ts):
            return None
        source, source_kind, owner, target, target_kind = self._sides(event)
        if not involve_friendly(source_kind, target_kind):
            return None
        fight = self.fight
        fight.touch(event.ts, offset)
        if source and source_kind in {"self", "group", "pet", "other"}:
            fight.agg(source, source_kind, owner).misses += 1
        fight.last_combat_ts = event.ts or fight.last_combat_ts
        return None

    def _heal(self, event: ParsedEvent, offset: int | None) -> None:
        if self.fight is None or not self.fight.open:
            return
        if self.gap_too_wide(event.ts):
            return
        source, source_kind, owner, _target, _target_kind = self._sides(event)
        if not source or source_kind not in {"self", "group", "pet", "other"}:
            return
        row = self.fight.agg(source, source_kind, owner)
        row.heals += int(event.amount or 0)
        if event.amount_full is not None:
            row.heals_full += int(event.amount_full)
        else:
            row.heals_full += int(event.amount or 0)
        self.fight.touch(event.ts, offset)

    def _death(self, event: ParsedEvent, offset: int | None) -> FightState | None:
        if self.fight is None or not self.fight.open:
            return None
        if self.gap_too_wide(event.ts):
            self.close(self.fight.last_combat_ts)
            return self.closed[-1] if self.closed else None
        fight = self.fight
        fight.touch(event.ts, offset)
        if event.kind == "death" and (is_you(event.target) or event.target == self.character):
            fight.player_died = True
        if event.kind == "slain":
            self._mark_dead(event.target)
            if is_you(event.target):
                fight.player_died = True
        elif event.kind == "death" and event.target and not is_you(event.target):
            self._mark_dead(event.target)
        if event.pet and event.pet in self.ctx.charmed:
            self._drop_charm(event.pet)
        if fight.all_dead():
            return self.close(event.ts)
        return None

    def finish(self) -> FightState | None:
        """Close an open fight at end of a historical replay."""
        return self.close(self.fight.last_combat_ts if self.fight else None)


def merge_pet_rows(rows: list[dict]) -> list[dict]:
    """Roll pet damage into the owner's row and keep the pet as a nested sub-row."""
    by_name = {row["source"]: dict(row) for row in rows}
    pets_for: dict[str, list[dict]] = {}
    consumed: set[str] = set()
    for row in rows:
        if row.get("kind") == "pet" and row.get("owner"):
            owner = row["owner"]
            pets_for.setdefault(owner, []).append(dict(row))
            consumed.add(row["source"])
            host = by_name.get(owner)
            if host is None:
                host = {
                    "source": owner,
                    "kind": "self" if owner else "other",
                    "owner": None,
                    "damage": 0,
                    "damage_taken": 0,
                    "hits": 0,
                    "misses": 0,
                    "crits": 0,
                    "max_hit": 0,
                    "heals": 0,
                    "heals_full": 0,
                    "overheal": 0,
                    "melee": 0,
                    "spell": 0,
                    "dot": 0,
                    "ds": 0,
                    "dps": 0.0,
                    "sdps": 0.0,
                    "active_seconds": 0.0,
                    "hit_pct": 0.0,
                    "crit_pct": 0.0,
                }
                by_name[owner] = host
            for key in ("damage", "damage_taken", "hits", "misses", "crits", "heals", "heals_full", "overheal", "melee", "spell", "dot", "ds"):
                host[key] = int(host.get(key) or 0) + int(row.get(key) or 0)
            host["max_hit"] = max(int(host.get("max_hit") or 0), int(row.get("max_hit") or 0))
            host["first_ts"] = _earlier(host.get("first_ts"), row.get("first_ts"))
            host["last_ts"] = _later(host.get("last_ts"), row.get("last_ts"))
            host["active_seconds"] = _span_seconds(host.get("first_ts"), host.get("last_ts"))
    merged = []
    for name, host in by_name.items():
        if name in consumed:
            continue
        swings = int(host["hits"]) + int(host["misses"])
        active = max(MIN_SECONDS, float(host.get("active_seconds") or MIN_SECONDS)) if host["hits"] else MIN_SECONDS
        # SDPS is recomputed by the caller when fight duration is known; keep the
        # pre-merge sdps if this row had no pets added. Recompute DPS from the
        # combined active window.
        if name in pets_for or host.get("kind") == "pet":
            host["dps"] = (host["damage"] / active) if host["damage"] else 0.0
        host["hit_pct"] = (100.0 * host["hits"] / swings) if swings else 0.0
        host["crit_pct"] = (100.0 * host["crits"] / host["hits"]) if host["hits"] else 0.0
        host["pets"] = pets_for.get(name, [])
        merged.append(host)
    merged.sort(key=lambda row: (-int(row["damage"]), row["source"]))
    return merged


def _earlier(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return a if a <= b else b


def _later(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return a if a >= b else b


def _span_seconds(first: str | None, last: str | None) -> float:
    if not first or not last:
        return MIN_SECONDS
    start = datetime.strptime(first, "%Y-%m-%dT%H:%M:%S")
    end = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S")
    return max(MIN_SECONDS, (end - start).total_seconds())


def recompute_sdps(rows: list[dict], fight_seconds: float) -> None:
    seconds = max(MIN_SECONDS, fight_seconds)
    for row in rows:
        row["sdps"] = (row["damage"] / seconds) if row.get("damage") else 0.0
        for pet in row.get("pets") or []:
            pet["sdps"] = (pet["damage"] / seconds) if pet.get("damage") else 0.0
