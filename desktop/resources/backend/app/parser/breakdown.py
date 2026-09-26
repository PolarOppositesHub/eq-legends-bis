"""Per-fight aggregates for damage, healing, tanking, deaths, resists, and swings.

Multi-attack is an estimate. The log's timestamp resolves to one second, so
melee hits and misses that share a source and a timestamp are one swing
cluster: 1 single, 2 double, 3 triple, 4 or more a flurry. A swing whose
modifier is Flurry makes that cluster a flurry even when it is shorter.
Riposte swings are left out of the cluster. They still count as damage.

Procs per minute use the fight's duration and the verified
``Your <item> shimmers briefly.`` / ``feels alive with power.`` lines.

Rune rows are the absorption printed on ``You gain a rune for N points of
absorption.`` The log does not say how much of that rune was later consumed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

DEATH_LOOKBACK = 10
_MIN_SECONDS = 1.0

# Third-person melee verbs from the classifier, folded back to the base form
# so "slashes" and "slash" are one ability.
_BASE_FROM_THIRD = {
    "frenzies on": "frenzy on",
    "backstabs": "backstab",
    "crushes": "crush",
    "slashes": "slash",
    "pierces": "pierce",
    "bashes": "bash",
    "kicks": "kick",
    "bites": "bite",
    "claws": "claw",
    "gores": "gore",
    "mauls": "maul",
    "punches": "punch",
    "strikes": "strike",
    "slices": "slice",
    "slams": "slam",
    "stings": "sting",
    "rends": "rend",
    "smashes": "smash",
    "gnaws": "gnaw",
    "lashes": "lash",
    "smites": "smite",
    "cleaves": "cleave",
    "reaves": "reave",
    "shoots": "shoot",
    "flurries": "flurry",
    "hits": "hit",
    "hit": "hit",
}

MULTI_NOTE = (
    "Estimate from melee hits and misses that share a timestamp second. "
    "Riposte swings are excluded. A cluster of 4 or more, or any swing tagged "
    "Flurry, counts as a flurry."
)


def ability_name(kind: str, verb: str | None, spell: str | None) -> str:
    if kind in {"melee", "miss"}:
        raw = (verb or "hit").lower()
        return _BASE_FROM_THIRD.get(raw, raw)
    if kind == "ds":
        return spell or "(non-melee)"
    if kind in {"spell", "dot"}:
        return spell or "(unknown spell)"
    if kind == "self_damage":
        return "hurt yourself"
    return spell or verb or "(unknown)"


def modifier_is(modifiers: tuple[str, ...] | list[str], word: str) -> bool:
    needle = word.lower()
    return any(part.lower() == needle for part in modifiers)


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class Ability:
    source: str
    category: str
    ability: str
    damage: int = 0
    hits: int = 0
    crits: int = 0
    misses: int = 0
    max_hit: int = 0

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "category": self.category,
            "ability": self.ability,
            "damage": self.damage,
            "hits": self.hits,
            "crits": self.crits,
            "misses": self.misses,
            "max_hit": self.max_hit,
        }


@dataclass
class HealSpell:
    source: str
    target: str
    spell: str
    over_time: bool
    actual: int = 0
    full: int = 0
    hits: int = 0
    crits: int = 0

    @property
    def overheal(self) -> int:
        return max(0, self.full - self.actual)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "spell": self.spell,
            "over_time": self.over_time,
            "actual": self.actual,
            "full": self.full,
            "overheal": self.overheal,
            "hits": self.hits,
            "crits": self.crits,
        }


@dataclass
class IncomingHit:
    target: str
    source: str | None
    category: str
    ability: str
    damage: int = 0
    hits: int = 0
    max_hit: int = 0

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "source": self.source,
            "category": self.category,
            "ability": self.ability,
            "damage": self.damage,
            "hits": self.hits,
            "max_hit": self.max_hit,
        }


@dataclass
class Multi:
    singles: int = 0
    doubles: int = 0
    triples: int = 0
    flurries: int = 0

    def add_cluster(self, swings: int, flurry: bool) -> None:
        if flurry or swings >= 4:
            self.flurries += 1
        elif swings == 3:
            self.triples += 1
        elif swings == 2:
            self.doubles += 1
        elif swings == 1:
            self.singles += 1

    @property
    def rounds(self) -> int:
        return self.singles + self.doubles + self.triples + self.flurries


@dataclass
class OpenRound:
    second: str
    swings: int = 0
    flurry: bool = False


@dataclass
class Breakdown:
    abilities: dict[tuple, Ability] = field(default_factory=dict)
    heals: dict[tuple, HealSpell] = field(default_factory=dict)
    incoming: dict[tuple, IncomingHit] = field(default_factory=dict)
    avoidance: dict[tuple, int] = field(default_factory=dict)
    runes: dict[str, list[int]] = field(default_factory=dict)
    self_damage: dict[str, list[int]] = field(default_factory=dict)
    resists: dict[tuple, int] = field(default_factory=dict)
    procs: dict[tuple, int] = field(default_factory=dict)
    multi: dict[str, Multi] = field(default_factory=dict)
    open_rounds: dict[str, OpenRound] = field(default_factory=dict)
    recent: dict[str, deque] = field(default_factory=dict)
    deaths: list[dict] = field(default_factory=list)

    def add_outgoing(self, source: str, category: str, name: str, amount: int, crit: bool) -> None:
        row = self.abilities.setdefault((source, category, name), Ability(source, category, name))
        row.damage += amount
        row.hits += 1
        if crit:
            row.crits += 1
        if amount > row.max_hit:
            row.max_hit = amount

    def add_ability_miss(self, source: str, category: str, name: str) -> None:
        row = self.abilities.setdefault((source, category, name), Ability(source, category, name))
        row.misses += 1

    def add_incoming(
        self,
        target: str,
        source: str | None,
        category: str,
        name: str,
        amount: int,
    ) -> None:
        row = self.incoming.setdefault(
            (target, source, category, name),
            IncomingHit(target, source, category, name),
        )
        row.damage += amount
        row.hits += 1
        if amount > row.max_hit:
            row.max_hit = amount

    def add_avoidance(self, target: str, kind: str) -> None:
        if not target or not kind:
            return
        key = (target, kind)
        self.avoidance[key] = self.avoidance.get(key, 0) + 1

    def add_heal(
        self,
        source: str,
        target: str,
        spell: str,
        over_time: bool,
        actual: int,
        full: int,
        crit: bool,
    ) -> None:
        row = self.heals.setdefault(
            (source, target, spell, over_time),
            HealSpell(source, target, spell, over_time),
        )
        row.actual += actual
        row.full += full
        row.hits += 1
        if crit:
            row.crits += 1

    def add_resist(self, source: str | None, target: str | None, spell: str) -> None:
        key = (source, target, spell)
        self.resists[key] = self.resists.get(key, 0) + 1

    def add_proc(self, source: str, item: str) -> None:
        key = (source, item)
        self.procs[key] = self.procs.get(key, 0) + 1

    def add_rune(self, source: str, absorption: int) -> None:
        row = self.runes.setdefault(source, [0, 0])
        row[0] += absorption
        row[1] += 1

    def add_self_damage(self, target: str, amount: int) -> None:
        row = self.self_damage.setdefault(target, [0, 0])
        row[0] += amount
        row[1] += 1

    def note_swing(self, source: str, ts: datetime | None, *, flurry: bool, riposte: bool) -> None:
        if not source or ts is None or riposte:
            return
        second = ts.strftime("%Y-%m-%dT%H:%M:%S")
        current = self.open_rounds.get(source)
        if current is None or current.second != second:
            if current is not None:
                self._commit(source, current)
            self.open_rounds[source] = OpenRound(second=second, swings=1, flurry=flurry)
            return
        current.swings += 1
        if flurry:
            current.flurry = True

    def _commit(self, source: str, rnd: OpenRound) -> None:
        row = self.multi.setdefault(source, Multi())
        row.add_cluster(rnd.swings, rnd.flurry)

    def finalize(self) -> None:
        for source, rnd in list(self.open_rounds.items()):
            self._commit(source, rnd)
        self.open_rounds.clear()

    def push_incoming(self, target: str | None, event: dict) -> None:
        if not target:
            return
        bucket = self.recent.get(target)
        if bucket is None:
            bucket = deque(maxlen=DEATH_LOOKBACK)
            self.recent[target] = bucket
        bucket.append(event)

    def add_death(self, who: str, killer: str | None, ts: datetime | None, kind: str) -> None:
        self.deaths.append({
            "ts": _iso(ts),
            "who": who,
            "killer": killer,
            "kind": kind,
            "incoming": list(self.recent.get(who, ())),
        })

    def _folded_multi(self) -> dict[str, Multi]:
        folded = {
            source: Multi(row.singles, row.doubles, row.triples, row.flurries)
            for source, row in self.multi.items()
        }
        for source, rnd in self.open_rounds.items():
            row = folded.setdefault(source, Multi())
            row.add_cluster(rnd.swings, rnd.flurry)
        return folded

    def to_api(self, fight_seconds: float) -> dict:
        abilities = [row.as_dict() for row in self.abilities.values()]
        abilities.sort(key=lambda row: (-row["damage"], -row["hits"], row["source"], row["category"], row["ability"]))

        heal_rows = [row.as_dict() for row in self.heals.values()]
        heal_rows.sort(key=lambda row: (-row["actual"], row["source"], row["spell"], row["target"], row["over_time"]))

        incoming = [row.as_dict() for row in self.incoming.values()]
        incoming.sort(key=lambda row: (-row["damage"], row["target"], row["source"] or "", row["ability"]))

        avoidance = [
            {"target": target, "kind": kind, "count": count}
            for (target, kind), count in self.avoidance.items()
        ]
        avoidance.sort(key=lambda row: (row["target"], row["kind"]))

        runes = [
            {"source": source, "absorption": points, "count": count}
            for source, (points, count) in self.runes.items()
        ]
        runes.sort(key=lambda row: row["source"])

        self_rows = [
            {"target": target, "damage": damage, "hits": hits}
            for target, (damage, hits) in self.self_damage.items()
        ]
        self_rows.sort(key=lambda row: row["target"])

        resists = [
            {"source": source, "target": target, "spell": spell, "count": count}
            for (source, target, spell), count in self.resists.items()
        ]
        resists.sort(key=lambda row: (-row["count"], row["source"] or "", row["spell"], row["target"] or ""))

        items = [
            {"source": source, "item": item, "count": count}
            for (source, item), count in self.procs.items()
        ]
        items.sort(key=lambda row: (-row["count"], row["item"], row["source"]))
        proc_count = sum(row["count"] for row in items)
        seconds = fight_seconds if fight_seconds and fight_seconds > 0 else _MIN_SECONDS
        per_minute = (proc_count * 60.0 / seconds) if proc_count else 0.0

        multi_rows = []
        for source, row in self._folded_multi().items():
            rounds = row.rounds
            if not rounds:
                continue
            multi_rows.append({
                "source": source,
                "rounds": rounds,
                "singles": row.singles,
                "doubles": row.doubles,
                "triples": row.triples,
                "flurries": row.flurries,
                "double_rate": row.doubles / rounds,
                "triple_rate": row.triples / rounds,
                "flurry_rate": row.flurries / rounds,
            })
        multi_rows.sort(key=lambda row: (-row["rounds"], row["source"]))

        direct = [row for row in heal_rows if not row["over_time"]]
        hot = [row for row in heal_rows if row["over_time"]]

        def _sum(rows: list[dict], key: str) -> int:
            return sum(int(row[key]) for row in rows)

        return {
            "abilities": abilities,
            "healing": {
                "rows": heal_rows,
                "totals": {
                    "actual": _sum(heal_rows, "actual"),
                    "full": _sum(heal_rows, "full"),
                    "overheal": _sum(heal_rows, "overheal"),
                    "direct_actual": _sum(direct, "actual"),
                    "direct_full": _sum(direct, "full"),
                    "direct_overheal": _sum(direct, "overheal"),
                    "hot_actual": _sum(hot, "actual"),
                    "hot_full": _sum(hot, "full"),
                    "hot_overheal": _sum(hot, "overheal"),
                },
            },
            "tanking": {
                "incoming": incoming,
                "avoidance": avoidance,
                "runes": runes,
                "self_damage": self_rows,
            },
            "deaths": list(self.deaths),
            "resists": resists,
            "procs": {
                "count": proc_count,
                "per_minute": per_minute,
                "items": items,
            },
            "multi_attack": {
                "estimate": True,
                "note": MULTI_NOTE,
                "sources": multi_rows,
            },
        }

    def to_state(self) -> dict:
        return {
            "v": 1,
            "abilities": [row.as_dict() for row in self.abilities.values()],
            "heals": [row.as_dict() for row in self.heals.values()],
            "incoming": [row.as_dict() for row in self.incoming.values()],
            "avoidance": [
                {"target": target, "kind": kind, "count": count}
                for (target, kind), count in self.avoidance.items()
            ],
            "runes": [
                {"source": source, "absorption": points, "count": count}
                for source, (points, count) in self.runes.items()
            ],
            "self_damage": [
                {"target": target, "damage": damage, "hits": hits}
                for target, (damage, hits) in self.self_damage.items()
            ],
            "resists": [
                {"source": source, "target": target, "spell": spell, "count": count}
                for (source, target, spell), count in self.resists.items()
            ],
            "procs": [
                {"source": source, "item": item, "count": count}
                for (source, item), count in self.procs.items()
            ],
            "multi": [
                {
                    "source": source,
                    "singles": row.singles,
                    "doubles": row.doubles,
                    "triples": row.triples,
                    "flurries": row.flurries,
                }
                for source, row in self.multi.items()
            ],
            "open_rounds": [
                {"source": source, "second": rnd.second, "swings": rnd.swings, "flurry": rnd.flurry}
                for source, rnd in self.open_rounds.items()
            ],
            "recent": {target: list(events) for target, events in self.recent.items()},
            "deaths": list(self.deaths),
        }

    @classmethod
    def from_state(cls, data: dict | None) -> Breakdown:
        parsed = cls()
        if not data:
            return parsed
        for row in data.get("abilities") or []:
            ability = Ability(
                source=row["source"],
                category=row["category"],
                ability=row["ability"],
                damage=int(row.get("damage") or 0),
                hits=int(row.get("hits") or 0),
                crits=int(row.get("crits") or 0),
                misses=int(row.get("misses") or 0),
                max_hit=int(row.get("max_hit") or 0),
            )
            parsed.abilities[(ability.source, ability.category, ability.ability)] = ability
        for row in data.get("heals") or []:
            heal = HealSpell(
                source=row["source"],
                target=row["target"],
                spell=row["spell"],
                over_time=bool(row.get("over_time")),
                actual=int(row.get("actual") or 0),
                full=int(row.get("full") or 0),
                hits=int(row.get("hits") or 0),
                crits=int(row.get("crits") or 0),
            )
            parsed.heals[(heal.source, heal.target, heal.spell, heal.over_time)] = heal
        for row in data.get("incoming") or []:
            hit = IncomingHit(
                target=row["target"],
                source=row.get("source"),
                category=row["category"],
                ability=row["ability"],
                damage=int(row.get("damage") or 0),
                hits=int(row.get("hits") or 0),
                max_hit=int(row.get("max_hit") or 0),
            )
            parsed.incoming[(hit.target, hit.source, hit.category, hit.ability)] = hit
        for row in data.get("avoidance") or []:
            parsed.avoidance[(row["target"], row["kind"])] = int(row.get("count") or 0)
        for row in data.get("runes") or []:
            parsed.runes[row["source"]] = [int(row.get("absorption") or 0), int(row.get("count") or 0)]
        for row in data.get("self_damage") or []:
            parsed.self_damage[row["target"]] = [int(row.get("damage") or 0), int(row.get("hits") or 0)]
        for row in data.get("resists") or []:
            parsed.resists[(row.get("source"), row.get("target"), row["spell"])] = int(row.get("count") or 0)
        for row in data.get("procs") or []:
            parsed.procs[(row["source"], row["item"])] = int(row.get("count") or 0)
        for row in data.get("multi") or []:
            parsed.multi[row["source"]] = Multi(
                singles=int(row.get("singles") or 0),
                doubles=int(row.get("doubles") or 0),
                triples=int(row.get("triples") or 0),
                flurries=int(row.get("flurries") or 0),
            )
        for row in data.get("open_rounds") or []:
            parsed.open_rounds[row["source"]] = OpenRound(
                second=row["second"],
                swings=int(row.get("swings") or 0),
                flurry=bool(row.get("flurry")),
            )
        for target, events in (data.get("recent") or {}).items():
            parsed.recent[target] = deque(list(events), maxlen=DEATH_LOOKBACK)
        parsed.deaths = list(data.get("deaths") or [])
        return parsed
