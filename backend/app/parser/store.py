"""SQLite storage for parser events, fights, and roster.

Keys are ``(file, generation, byte offset)``. Re-reading a log inserts nothing
new. A truncation bumps ``generation`` so the recycled offsets are a new session.
Raw log lines are not stored.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .breakdown import Breakdown
from .fights import FightState, SourceAgg
from .models import ParsedEvent

# 1 is a 1.1.0 database: fights exist, fight breakdowns do not. Bump this when
# derived aggregates change so the next launch rebuilds them from the logs.
SCHEMA_VERSION = 2
SCHEMA_VERSION_KEY = "schema_version"

_DERIVED_TABLES = (
    "events",
    "fight_sources",
    "fight_breakdown",
    "fights",
    "loot_events",
    "give_events",
    "merge_events",
    "xp_events",
    "level_events",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS log_files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    character TEXT,
    server TEXT,
    generation INTEGER NOT NULL DEFAULT 1,
    last_offset INTEGER NOT NULL DEFAULT 0,
    last_size INTEGER NOT NULL DEFAULT 0,
    mtime REAL,
    zone TEXT,
    instance_json TEXT
);

CREATE TABLE IF NOT EXISTS events (
    file_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    ts TEXT,
    kind TEXT NOT NULL,
    source TEXT,
    target TEXT,
    amount INTEGER,
    amount_full INTEGER,
    spell TEXT,
    verb TEXT,
    damage_type TEXT,
    modifiers TEXT,
    extra TEXT,
    PRIMARY KEY (file_id, generation, offset)
);

CREATE TABLE IF NOT EXISTS fights (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    character TEXT,
    zone TEXT,
    instance_json TEXT,
    start_ts TEXT,
    end_ts TEXT,
    start_offset INTEGER,
    end_offset INTEGER,
    last_combat_ts TEXT,
    targets_json TEXT,
    open INTEGER NOT NULL DEFAULT 1,
    player_died INTEGER NOT NULL DEFAULT 0,
    UNIQUE (file_id, generation, start_offset)
);

CREATE TABLE IF NOT EXISTS fight_breakdown (
    fight_id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fight_sources (
    fight_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_kind TEXT,
    owner TEXT,
    damage INTEGER NOT NULL DEFAULT 0,
    damage_taken INTEGER NOT NULL DEFAULT 0,
    hits INTEGER NOT NULL DEFAULT 0,
    misses INTEGER NOT NULL DEFAULT 0,
    crits INTEGER NOT NULL DEFAULT 0,
    max_hit INTEGER NOT NULL DEFAULT 0,
    heals INTEGER NOT NULL DEFAULT 0,
    heals_full INTEGER NOT NULL DEFAULT 0,
    melee INTEGER NOT NULL DEFAULT 0,
    spell_dmg INTEGER NOT NULL DEFAULT 0,
    dot INTEGER NOT NULL DEFAULT 0,
    ds INTEGER NOT NULL DEFAULT 0,
    first_ts TEXT,
    last_ts TEXT,
    PRIMARY KEY (fight_id, source)
);

CREATE TABLE IF NOT EXISTS loot_events (
    file_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    ts TEXT,
    character TEXT,
    item TEXT,
    qty INTEGER,
    from_name TEXT,
    mode TEXT,
    coin_copper INTEGER,
    coin_text TEXT,
    is_mote INTEGER NOT NULL DEFAULT 0,
    is_wind_rune INTEGER NOT NULL DEFAULT 0,
    result_item TEXT,
    result_tier INTEGER,
    PRIMARY KEY (file_id, generation, offset)
);

CREATE TABLE IF NOT EXISTS give_events (
    file_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    ts TEXT,
    character TEXT,
    item TEXT,
    qty INTEGER,
    npc TEXT,
    is_mote INTEGER NOT NULL DEFAULT 0,
    is_wind_rune INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (file_id, generation, offset)
);

CREATE TABLE IF NOT EXISTS merge_events (
    file_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    ts TEXT,
    character TEXT,
    result_item TEXT,
    result_tier INTEGER,
    PRIMARY KEY (file_id, generation, offset)
);

CREATE TABLE IF NOT EXISTS xp_events (
    file_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    ts TEXT,
    character TEXT,
    pct REAL,
    party INTEGER NOT NULL DEFAULT 0,
    bonus INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (file_id, generation, offset)
);

CREATE TABLE IF NOT EXISTS level_events (
    file_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    ts TEXT,
    character TEXT,
    level INTEGER,
    classes TEXT,
    evidence TEXT,
    ability_points INTEGER,
    ability_total INTEGER,
    PRIMARY KEY (file_id, generation, offset)
);

CREATE TABLE IF NOT EXISTS pet_bindings (
    character TEXT NOT NULL,
    pet TEXT NOT NULL,
    owner TEXT,
    evidence TEXT,
    manual INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (character, pet)
);

CREATE TABLE IF NOT EXISTS group_members (
    character TEXT NOT NULL,
    member TEXT NOT NULL,
    PRIMARY KEY (character, member)
);

CREATE TABLE IF NOT EXISTS known_players (
    character TEXT NOT NULL,
    name TEXT NOT NULL,
    class_line TEXT,
    level INTEGER,
    PRIMARY KEY (character, name)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")


class ParserDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add loadout columns when a database was created before them."""
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(level_events)")}
        if "classes" not in cols:
            self.conn.execute("ALTER TABLE level_events ADD COLUMN classes TEXT")
        if "evidence" not in cols:
            self.conn.execute("ALTER TABLE level_events ADD COLUMN evidence TEXT")

    def close(self) -> None:
        with self.lock:
            conn = self.conn
            if conn is None:
                return
            conn.close()
            self.conn = None

    def begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self.conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self.conn.commit()

    def stored_schema_version(self) -> int | None:
        """Aggregate version stored with this database.

        ``None`` means the key was never written (a 1.1.0 database).
        """
        raw = self.get_setting(SCHEMA_VERSION_KEY)
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def set_schema_version(self, version: int) -> None:
        self.set_setting(SCHEMA_VERSION_KEY, str(int(version)))

    def list_log_paths(self) -> list[str]:
        with self.lock:
            rows = self.conn.execute("SELECT path FROM log_files ORDER BY id").fetchall()
        return [str(row["path"]) for row in rows]

    def clear_derived(self) -> None:
        """Drop rebuilt parser output and rewind known logs to offset 0.

        Settings, the chosen log paths, group/player notes, and manual pet
        bindings stay. Automatic pet bindings are removed so the replay can
        derive them again.
        """
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for table in _DERIVED_TABLES:
                    self.conn.execute(f"DELETE FROM {table}")
                self.conn.execute("UPDATE log_files SET last_offset=0")
                self.conn.execute("DELETE FROM pet_bindings WHERE manual=0")
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def upsert_file(self, path: str, character: str, server: str, size: int, mtime: float) -> sqlite3.Row:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO log_files(path, character, server, last_size, mtime)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    character=excluded.character,
                    server=excluded.server,
                    last_size=excluded.last_size,
                    mtime=excluded.mtime
                """,
                (path, character, server, size, mtime),
            )
            self.conn.commit()
            row = self.conn.execute("SELECT * FROM log_files WHERE path=?", (path,)).fetchone()
        return row

    def mark_offset(self, file_id: int, offset: int, size: int) -> None:
        self.conn.execute(
            "UPDATE log_files SET last_offset=?, last_size=? WHERE id=?",
            (offset, size, file_id),
        )

    def bump_generation(self, file_id: int) -> int:
        with self.lock:
            self.conn.execute(
                "UPDATE log_files SET generation=generation+1, last_offset=0 WHERE id=?",
                (file_id,),
            )
            self.conn.commit()
            row = self.conn.execute("SELECT generation FROM log_files WHERE id=?", (file_id,)).fetchone()
        return int(row["generation"])

    def file_row(self, file_id: int) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM log_files WHERE id=?", (file_id,)).fetchone()

    def insert_event(self, file_id: int, generation: int, offset: int, event: ParsedEvent) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO events(
                file_id, generation, offset, ts, kind, source, target, amount, amount_full,
                spell, verb, damage_type, modifiers, extra
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                generation,
                offset,
                _iso(event.ts),
                event.kind,
                event.source,
                event.target,
                event.amount,
                event.amount_full,
                event.spell,
                event.verb,
                event.damage_type,
                " ".join(event.modifiers),
                json.dumps(event.extra) if event.extra else None,
            ),
        )
        changed = self.conn.execute("SELECT changes()").fetchone()[0]
        return int(changed) == 1

    def insert_specialized(self, file_id: int, generation: int, offset: int, character: str, event: ParsedEvent) -> None:
        extra = event.extra or {}
        if event.kind == "loot":
            self.conn.execute(
                """
                INSERT OR IGNORE INTO loot_events(
                    file_id, generation, offset, ts, character, item, qty, from_name, mode,
                    coin_copper, coin_text, is_mote, is_wind_rune, result_item, result_tier
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id, generation, offset, _iso(event.ts), character, event.item, event.qty,
                    event.target, event.mode, event.coin_copper, event.coin_text,
                    1 if extra.get("is_mote") else 0,
                    1 if extra.get("is_wind_rune") else 0,
                    event.result_item, event.result_tier,
                ),
            )
        elif event.kind == "give":
            self.conn.execute(
                """
                INSERT OR IGNORE INTO give_events(
                    file_id, generation, offset, ts, character, item, qty, npc, is_mote, is_wind_rune
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id, generation, offset, _iso(event.ts), character, event.item, event.qty,
                    event.target, 1 if extra.get("is_mote") else 0, 1 if extra.get("is_wind_rune") else 0,
                ),
            )
        elif event.kind == "merge":
            self.conn.execute(
                """
                INSERT OR IGNORE INTO merge_events(
                    file_id, generation, offset, ts, character, result_item, result_tier
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, generation, offset, _iso(event.ts), character, event.result_item, event.result_tier),
            )
        elif event.kind == "xp":
            self.conn.execute(
                """
                INSERT OR IGNORE INTO xp_events(
                    file_id, generation, offset, ts, character, pct, party, bonus
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id, generation, offset, _iso(event.ts), character, event.xp_pct,
                    1 if event.party_xp else 0, 1 if extra.get("bonus") else 0,
                ),
            )
        elif event.kind == "level":
            # A drop from 50 to 29 is a class-loadout swap, not a bad parse.
            # Welcome lines name no trio, so classes stays null.
            evidence = "ability" if event.level is None and event.ability_points is not None else "level_line"
            self.conn.execute(
                """
                INSERT OR IGNORE INTO level_events(
                    file_id, generation, offset, ts, character, level, classes, evidence,
                    ability_points, ability_total
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id, generation, offset, _iso(event.ts), character,
                    event.level, None, evidence, event.ability_points, event.ability_total,
                ),
            )
        elif (
            event.kind == "who"
            and event.player_name
            and event.player_name.lower() == character.lower()
            and event.player_classes
        ):
            # /who is the log's evidence of which trio is on, and at what level.
            self.conn.execute(
                """
                INSERT OR IGNORE INTO level_events(
                    file_id, generation, offset, ts, character, level, classes, evidence,
                    ability_points, ability_total
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id, generation, offset, _iso(event.ts), character,
                    event.player_level, event.player_classes, "who", None, None,
                ),
            )

    def save_fight(self, file_id: int, generation: int, fight: FightState) -> int:
        payload = (
            fight.zone,
            json.dumps(fight.instance) if fight.instance else None,
            _iso(fight.start_ts),
            _iso(fight.end_ts),
            fight.start_offset,
            fight.end_offset,
            _iso(fight.last_combat_ts),
            json.dumps({name: bool(alive) for name, alive in fight.targets.items()}),
            1 if fight.open else 0,
            1 if fight.player_died else 0,
        )
        if fight.db_id:
            self.conn.execute(
                """
                UPDATE fights SET zone=?, instance_json=?, start_ts=?, end_ts=?, start_offset=?,
                    end_offset=?, last_combat_ts=?, targets_json=?, open=?, player_died=?
                WHERE id=?
                """,
                (*payload, fight.db_id),
            )
            fight_id = fight.db_id
        else:
            cur = self.conn.execute(
                """
                INSERT INTO fights(
                    file_id, generation, character, zone, instance_json, start_ts, end_ts,
                    start_offset, end_offset, last_combat_ts, targets_json, open, player_died
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id, generation, fight.character, *payload,
                ),
            )
            fight_id = int(cur.lastrowid)
            fight.db_id = fight_id
        self.conn.execute("DELETE FROM fight_sources WHERE fight_id=?", (fight_id,))
        for agg in fight.sources.values():
            self.conn.execute(
                """
                INSERT INTO fight_sources(
                    fight_id, source, source_kind, owner, damage, damage_taken, hits, misses,
                    crits, max_hit, heals, heals_full, melee, spell_dmg, dot, ds, first_ts, last_ts
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fight_id, agg.source, agg.source_kind, agg.owner, agg.damage, agg.damage_taken,
                    agg.hits, agg.misses, agg.crits, agg.max_hit, agg.heals, agg.heals_full,
                    agg.melee, agg.spell_dmg, agg.dot, agg.ds, _iso(agg.first_ts), _iso(agg.last_ts),
                ),
            )
        self.conn.execute(
            """
            INSERT INTO fight_breakdown(fight_id, payload) VALUES(?, ?)
            ON CONFLICT(fight_id) DO UPDATE SET payload=excluded.payload
            """,
            (fight_id, json.dumps(fight.breakdown.to_state())),
        )
        return fight_id

    def load_open_fight(self, file_id: int, generation: int) -> FightState | None:
        row = self.conn.execute(
            "SELECT * FROM fights WHERE file_id=? AND generation=? AND open=1 ORDER BY id DESC LIMIT 1",
            (file_id, generation),
        ).fetchone()
        if row is None:
            return None
        fight = FightState(
            character=row["character"],
            zone=row["zone"],
            instance=json.loads(row["instance_json"]) if row["instance_json"] else None,
            start_ts=_parse_iso(row["start_ts"]),
            end_ts=_parse_iso(row["end_ts"]),
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
            last_combat_ts=_parse_iso(row["last_combat_ts"]),
            player_died=bool(row["player_died"]),
            open=True,
            db_id=row["id"],
        )
        raw_targets = json.loads(row["targets_json"] or "{}")
        if isinstance(raw_targets, dict):
            fight.targets = {name: bool(alive) for name, alive in raw_targets.items()}
        else:
            fight.targets = {name: True for name in raw_targets}
        for src in self.conn.execute("SELECT * FROM fight_sources WHERE fight_id=?", (row["id"],)):
            fight.sources[src["source"]] = SourceAgg(
                source=src["source"],
                source_kind=src["source_kind"] or "unknown",
                owner=src["owner"],
                damage=src["damage"],
                damage_taken=src["damage_taken"],
                hits=src["hits"],
                misses=src["misses"],
                crits=src["crits"],
                max_hit=src["max_hit"],
                heals=src["heals"],
                heals_full=src["heals_full"],
                melee=src["melee"],
                spell_dmg=src["spell_dmg"],
                dot=src["dot"],
                ds=src["ds"],
                first_ts=_parse_iso(src["first_ts"]),
                last_ts=_parse_iso(src["last_ts"]),
            )
        fight.breakdown = Breakdown.from_state(self.breakdown_state(row["id"]))
        return fight

    def load_roster(self, character: str) -> tuple[dict[str, str], dict[str, str | None], set[str], set[str]]:
        group = {
            row["member"].lower(): row["member"]
            for row in self.conn.execute("SELECT member FROM group_members WHERE character=?", (character,))
        }
        pets: dict[str, str | None] = {}
        manual: set[str] = set()
        for row in self.conn.execute("SELECT pet, owner, manual FROM pet_bindings WHERE character=?", (character,)):
            pets[row["pet"]] = row["owner"]
            if row["manual"]:
                manual.add(row["pet"])
        players = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM known_players WHERE character=?", (character,))
        }
        return group, pets, manual, players

    def add_group(self, character: str, member: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO group_members(character, member) VALUES(?, ?)",
            (character, member),
        )

    def clear_group(self, character: str) -> None:
        self.conn.execute("DELETE FROM group_members WHERE character=?", (character,))

    def remove_group(self, character: str, member: str) -> None:
        self.conn.execute(
            "DELETE FROM group_members WHERE character=? AND lower(member)=lower(?)",
            (character, member),
        )

    def note_player(self, character: str, name: str, classes: str | None = None, level: int | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO known_players(character, name, class_line, level) VALUES(?, ?, ?, ?)
            ON CONFLICT(character, name) DO UPDATE SET
                class_line=COALESCE(excluded.class_line, known_players.class_line),
                level=COALESCE(excluded.level, known_players.level)
            """,
            (character, name, classes, level),
        )

    def bind_pet(self, character: str, pet: str, owner: str | None, evidence: str, manual: bool) -> bool:
        row = self.conn.execute(
            "SELECT manual FROM pet_bindings WHERE character=? AND pet=?",
            (character, pet),
        ).fetchone()
        if row is not None and row["manual"] and not manual:
            return False
        self.conn.execute(
            """
            INSERT INTO pet_bindings(character, pet, owner, evidence, manual)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(character, pet) DO UPDATE SET
                owner=excluded.owner,
                evidence=excluded.evidence,
                manual=excluded.manual
            """,
            (character, pet, owner, evidence, 1 if manual else 0),
        )
        return True

    def clear_pet(self, character: str, pet: str) -> None:
        row = self.conn.execute(
            "SELECT manual FROM pet_bindings WHERE character=? AND pet=?",
            (character, pet),
        ).fetchone()
        if row is not None and row["manual"]:
            return
        self.conn.execute("DELETE FROM pet_bindings WHERE character=? AND pet=?", (character, pet))

    def count_events(self, file_id: int | None = None) -> int:
        if file_id is None:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM events WHERE file_id=?", (file_id,)).fetchone()
        return int(row["n"])

    def count_where(self, table: str, file_id: int | None = None) -> int:
        if table not in {"loot_events", "give_events", "merge_events", "xp_events", "level_events", "fights"}:
            raise ValueError(table)
        if file_id is None:
            row = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        else:
            row = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE file_id=?", (file_id,)).fetchone()
        return int(row["n"])

    def list_level_events(self, character: str | None = None) -> list[dict]:
        """Level observations in log order. ``classes`` is set only from /who evidence."""
        sql = """
            SELECT ts, character, level, classes, evidence, ability_points, ability_total, offset
            FROM level_events
        """
        args: list = []
        if character:
            sql += " WHERE character=?"
            args.append(character)
        sql += " ORDER BY COALESCE(ts, ''), offset"
        return [dict(row) for row in self.conn.execute(sql, args)]

    def list_fights(self, character: str | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
        sql = "SELECT * FROM fights"
        args: list = []
        if character:
            sql += " WHERE character=?"
            args.append(character)
        sql += " ORDER BY COALESCE(start_ts, '') DESC, id DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        rows = []
        for fight in self.conn.execute(sql, args):
            sources = list(self.conn.execute(
                "SELECT * FROM fight_sources WHERE fight_id=?", (fight["id"],)
            ))
            yours = next((s for s in sources if s["source_kind"] == "self"), None)
            friendly = {"self", "group", "pet"}
            damage = sum(s["damage"] for s in sources if s["source_kind"] in friendly)
            start = _parse_iso(fight["start_ts"])
            end = _parse_iso(fight["end_ts"])
            seconds = 1.0
            if start and end:
                seconds = max(1.0, (end - start).total_seconds())
            active = 1.0
            your_damage = 0
            if yours:
                your_damage = yours["damage"]
                a = _parse_iso(yours["first_ts"])
                b = _parse_iso(yours["last_ts"])
                if a and b:
                    active = max(1.0, (b - a).total_seconds())
            raw_targets = json.loads(fight["targets_json"] or "[]")
            target_names = list(raw_targets) if isinstance(raw_targets, dict) else list(raw_targets)
            rows.append({
                "id": fight["id"],
                "file_id": fight["file_id"],
                "character": fight["character"],
                "zone": fight["zone"],
                "instance": json.loads(fight["instance_json"]) if fight["instance_json"] else None,
                "start_ts": fight["start_ts"],
                "end_ts": fight["end_ts"],
                "duration_seconds": seconds,
                "targets": target_names,
                "open": bool(fight["open"]),
                "player_died": bool(fight["player_died"]),
                "damage": damage,
                "your_damage": your_damage,
                "your_dps": (your_damage / active) if your_damage else 0.0,
                "your_sdps": (your_damage / seconds) if your_damage else 0.0,
            })
        return rows

    def get_fight_row(self, fight_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM fights WHERE id=?", (fight_id,)).fetchone()

    def fight_source_rows(self, fight_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM fight_sources WHERE fight_id=?", (fight_id,)))

    def breakdown_state(self, fight_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT payload FROM fight_breakdown WHERE fight_id=?",
            (fight_id,),
        ).fetchone()
        if row is None or not row["payload"]:
            return None
        try:
            data = json.loads(row["payload"])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _list_economy(self, table: str, character: str | None, limit: int, offset: int) -> list[sqlite3.Row]:
        if table not in {"loot_events", "give_events", "merge_events"}:
            raise ValueError(table)
        sql = f"SELECT * FROM {table}"
        args: list = []
        if character:
            sql += " WHERE character=?"
            args.append(character)
        sql += " ORDER BY COALESCE(ts, ''), offset LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        return list(self.conn.execute(sql, args))

    def list_loot(self, character: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
        rows = []
        for row in self._list_economy("loot_events", character, limit, offset):
            rows.append({
                "ts": row["ts"],
                "character": row["character"],
                "item": row["item"],
                "qty": row["qty"],
                "from": row["from_name"],
                "mode": row["mode"],
                "coin_value": row["coin_copper"],
                "coin_text": row["coin_text"],
                "is_mote": bool(row["is_mote"]),
                "is_wind_rune": bool(row["is_wind_rune"]),
                "result_item": row["result_item"],
                "result_tier": row["result_tier"],
            })
        return rows

    def list_gives(self, character: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
        return [
            {
                "ts": row["ts"],
                "character": row["character"],
                "item": row["item"],
                "qty": row["qty"],
                "npc": row["npc"],
                "is_mote": bool(row["is_mote"]),
                "is_wind_rune": bool(row["is_wind_rune"]),
            }
            for row in self._list_economy("give_events", character, limit, offset)
        ]

    def list_merges(self, character: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
        return [
            {
                "ts": row["ts"],
                "character": row["character"],
                "result_item": row["result_item"],
                "result_tier": row["result_tier"],
            }
            for row in self._list_economy("merge_events", character, limit, offset)
        ]
