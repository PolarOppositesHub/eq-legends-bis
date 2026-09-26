"""Replay, live tail, and query facade used by the REST API."""

from __future__ import annotations

import threading
import time
from collections import Counter
from pathlib import Path

from .classify import classify_log_line
from .discover import (
    DEFAULT_EQ_INSTALL,
    default_user_data,
    discover_logs,
    parse_log_name,
    read_eq_install,
    write_settings,
)
from .fights import MIN_SECONDS, Segmenter, SourceAgg, merge_pet_rows, recompute_sdps
from .store import ParserDB, _parse_iso
from .tail import LogTail, TailBatch, backfill_offset

CHUNK_LINES = 50_000
_TEXT_SUFFIXES = {".txt", ".log"}


class LogRejected(ValueError):
    """The path is not a text combat log we are willing to read."""


def _check_log(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        raise LogRejected("Only .txt and .log combat logs can be read")
    with open(path, "rb") as handle:
        sig = handle.read(2)
    if sig == b"MZ":
        raise LogRejected("Refusing to read a binary file")


def iter_log_bytes(path: Path):
    offset = 0
    with open(path, "rb") as handle:
        for raw in handle:
            yield offset, raw.decode("utf-8", errors="replace")
            offset += len(raw)


def _skeleton(message: str) -> str:
    import re
    text = re.sub(r"\d+(?:\.\d+)?", "N", message)
    text = re.sub(r"[A-Za-z][A-Za-z'`.-]*", "W", text)
    return text[:160]


class ParserService:
    def __init__(self, user_data: Path | None = None, db_path: Path | None = None, idle_seconds: float = 30.0) -> None:
        self.user_data = Path(user_data) if user_data else default_user_data()
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.db = ParserDB(db_path or (self.user_data / "parser.db"))
        stored_idle = self.db.get_setting("idle_seconds")
        self.idle = float(stored_idle) if stored_idle else idle_seconds
        self.hub = EventHub()
        self._segs: dict[tuple[int, int], Segmenter] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tail: LogTail | None = None
        self._live_path: str | None = None
        self._replay_lock = threading.Lock()
        self._replaying = False
        self._last_fight_emit = 0.0

    def close(self) -> None:
        """Stop a live tail and release the SQLite file so Windows can delete the temp dir."""
        self.stop_live()
        self.db.close()

    def eq_folder(self) -> str:
        saved = read_eq_install(self.user_data)
        if saved:
            return saved
        stored = self.db.get_setting("eq_install_folder") or ""
        return stored or DEFAULT_EQ_INSTALL

    def set_eq_folder(self, folder: str) -> str:
        folder = folder.strip()
        write_settings(self.user_data, {"eqInstallFolder": folder})
        self.db.set_setting("eq_install_folder", folder)
        return folder

    def set_idle(self, seconds: float) -> float:
        self.idle = float(seconds)
        self.db.set_setting("idle_seconds", str(self.idle))
        return self.idle

    def list_logs(self, root: str | None = None) -> dict:
        folder = root or self.eq_folder()
        return {"folder": folder, "logs": discover_logs(folder)}

    def config(self) -> dict:
        return {
            "eq_install_folder": self.eq_folder(),
            "default_eq_install_folder": DEFAULT_EQ_INSTALL,
            "idle_seconds": self.idle,
            "db_path": str(self.db.path),
            "user_data": str(self.user_data),
            "live": self._thread is not None and self._thread.is_alive(),
            "live_path": self._live_path,
        }

    def replay(self, path: str | Path, *, idle_seconds: float | None = None, finalize: bool = True) -> dict:
        self.stop_live()
        if idle_seconds is not None:
            self.set_idle(idle_seconds)
        with self._replay_lock:
            self._replaying = True
            try:
                return self._consume(Path(path), finalize=finalize)
            finally:
                self._replaying = False

    def start_live(self, path: str | Path, *, from_end: bool = True, backfill_seconds: float | None = None) -> dict:
        self.stop_live()
        path = Path(path).resolve()
        _check_log(path)
        tail = LogTail(path, poll_interval=0.25)
        if backfill_seconds:
            tail.offset = backfill_offset(path, backfill_seconds)
            tail.partial = b""
        elif from_end:
            tail.start_at_end()
        else:
            tail.offset = 0
        self._tail = tail
        self._live_path = str(path)
        self._stop.clear()
        # Remember the start offset so a later shrink is treated as truncation.
        character, server = parse_log_name(path.name) or ("You", "")
        st = path.stat()
        with self.db.lock:
            row = self.db.upsert_file(str(path), character, server, st.st_size, st.st_mtime)
            if tail.offset > int(row["last_offset"] or 0):
                self.db.mark_offset(row["id"], tail.offset, st.st_size)
                self.db.commit()
        self._thread = threading.Thread(target=self._live_loop, name="eq-log-tail", daemon=True)
        self._thread.start()
        self.hub.publish({"type": "live", "on": True, "path": str(path)})
        return {"ok": True, "live": True, "path": str(path), "offset": tail.offset}

    def stop_live(self) -> dict:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=5)
        self._thread = None
        self._tail = None
        path = self._live_path
        self._live_path = None
        self.hub.publish({"type": "live", "on": False, "path": path})
        return {"ok": True, "live": False}

    def _live_loop(self) -> None:
        tail = self._tail
        if tail is None:
            return
        while not self._stop.is_set():
            try:
                batch = tail.poll()
            except FileNotFoundError:
                if self._stop.wait(tail.poll_interval):
                    break
                continue
            if batch.truncated or batch.lines:
                self._ingest_batch(tail.path, batch)
            if self._stop.wait(tail.poll_interval):
                break

    def _ingest_batch(self, path: Path, batch: TailBatch) -> None:
        character, server = parse_log_name(path.name) or ("You", "")
        st = path.stat() if path.exists() else None
        with self.db.lock:
            row = self.db.upsert_file(str(path.resolve()), character, server, st.st_size if st else 0, st.st_mtime if st else 0)
            file_id = int(row["id"])
            if batch.truncated:
                seg = self._segs.get((file_id, int(row["generation"])))
                if seg is not None:
                    seg.finish()
                generation = self.db.bump_generation(file_id)
                self._segs.pop((file_id, generation - 1), None)
                self.hub.publish({"type": "reset", "path": str(path), "generation": generation})
                row = self.db.file_row(file_id)
            if not batch.lines:
                return
            generation = int(row["generation"])
            seg = self._ensure_segmenter(file_id, generation, character)
            self.db.begin()
            try:
                for line in batch.lines:
                    _ts, event = classify_log_line(line.text)
                    if event is None:
                        continue
                    if not self.db.insert_event(file_id, generation, line.offset, event):
                        continue
                    self.db.insert_specialized(file_id, generation, line.offset, character, event)
                    seg.observe(event, line.offset)
                if seg.fight is not None and seg.fight.open:
                    self.db.save_fight(file_id, generation, seg.fight)
                    self._emit_fight(seg.fight.summary())
                size_now = st.st_size if st else self._tail.offset if self._tail else 0
                self.db.mark_offset(file_id, size_now, size_now)
                self.db.commit()
            except Exception:
                self.db.conn.rollback()
                raise
            self._close_if_idle(seg, file_id, generation)

    def _close_if_idle(self, seg: Segmenter, file_id: int, generation: int) -> None:
        fight = seg.fight
        if fight is None or not fight.open or fight.last_combat_ts is None:
            return
        if (time.time() - fight.last_combat_ts.timestamp()) <= self.idle:
            return
        with self.db.lock:
            closed = seg.finish()
            if closed:
                self.db.commit()
                self._emit_fight(closed.summary())

    def _consume(self, path: Path, *, finalize: bool) -> dict:
        path = path.resolve()
        _check_log(path)
        character, server = parse_log_name(path.name) or ("You", "")
        st = path.stat()
        examples: dict[str, str] = {}
        shapes: Counter[str] = Counter()
        lines = classified = unclassified = inserted = duplicate = 0
        started = time.perf_counter()
        with self.db.lock:
            row = self.db.upsert_file(str(path), character, server, st.st_size, st.st_mtime)
            file_id = int(row["id"])
            if st.st_size < int(row["last_offset"] or 0):
                if (file_id, int(row["generation"])) in self._segs:
                    self._segs[(file_id, int(row["generation"]))].finish()
                generation = self.db.bump_generation(file_id)
                self._segs.pop((file_id, generation - 1), None)
            else:
                generation = int(row["generation"])
            seg = self._ensure_segmenter(file_id, generation, character)
            self.db.begin()
            try:
                for offset, text in iter_log_bytes(path):
                    lines += 1
                    _ts, event = classify_log_line(text)
                    if event is None:
                        unclassified += 1
                        msg = text.split("] ", 1)[-1].strip()
                        key = _skeleton(msg)
                        shapes[key] += 1
                        examples.setdefault(key, msg[:180])
                    else:
                        classified += 1
                        if self.db.insert_event(file_id, generation, offset, event):
                            inserted += 1
                            self.db.insert_specialized(file_id, generation, offset, character, event)
                            seg.observe(event, offset)
                        else:
                            duplicate += 1
                    if lines % CHUNK_LINES == 0:
                        if seg.fight is not None and seg.fight.open:
                            self.db.save_fight(file_id, generation, seg.fight)
                        self.db.mark_offset(file_id, offset, st.st_size)
                        self.db.commit()
                        self.hub.publish({
                            "type": "progress",
                            "lines": lines,
                            "classified": classified,
                            "unclassified": unclassified,
                            "offset": offset,
                            "path": str(path),
                        })
                        self.db.begin()
                if finalize:
                    seg.finish()
                elif seg.fight is not None and seg.fight.open:
                    self.db.save_fight(file_id, generation, seg.fight)
                self.db.mark_offset(file_id, st.st_size, st.st_size)
                self.db.commit()
            except Exception:
                self.db.conn.rollback()
                raise
            fight_count = self.db.count_where("fights", file_id)
        elapsed = time.perf_counter() - started
        self.hub.publish({
            "type": "progress",
            "lines": lines,
            "classified": classified,
            "unclassified": unclassified,
            "offset": st.st_size,
            "path": str(path),
            "done": True,
        })
        top = []
        for shape, count in shapes.most_common(12):
            top.append({"count": count, "shape": shape, "example": examples.get(shape, "")})
        return {
            "ok": True,
            "path": str(path),
            "character": character,
            "server": server,
            "lines": lines,
            "classified": classified,
            "unclassified": unclassified,
            "unclassified_pct": (100.0 * unclassified / lines) if lines else 0.0,
            "events_inserted": inserted,
            "events_duplicate": duplicate,
            "event_count": self.db.count_events(file_id),
            "fights": fight_count,
            "loot": self.db.count_where("loot_events", file_id),
            "xp": self.db.count_where("xp_events", file_id),
            "levels": self.db.count_where("level_events", file_id),
            "merges": self.db.count_where("merge_events", file_id),
            "gives": self.db.count_where("give_events", file_id),
            "elapsed_ms": round(elapsed * 1000, 1),
            "lines_per_second": round(lines / elapsed, 1) if elapsed else None,
            "unclassified_examples": top,
        }

    def _ensure_segmenter(self, file_id: int, generation: int, character: str) -> Segmenter:
        key = (file_id, generation)
        seg = self._segs.get(key)
        if seg is not None:
            return seg

        def on_roster(op: str, payload: dict) -> None:
            if op == "group_add":
                self.db.add_group(character, payload["name"])
            elif op == "group_clear":
                self.db.clear_group(character)
            elif op == "group_remove":
                self.db.remove_group(character, payload["name"])
            elif op == "player":
                self.db.note_player(character, payload["name"], payload.get("classes"), payload.get("level"))
            elif op == "pet":
                self.db.bind_pet(character, payload["pet"], payload.get("owner"), payload.get("evidence") or "auto", False)
            elif op == "pet_clear":
                self.db.clear_pet(character, payload["pet"])

        def on_close(fight) -> None:
            self.db.save_fight(file_id, generation, fight)
            self._emit_fight(fight.summary())

        seg = Segmenter(character, idle_seconds=self.idle, on_roster=on_roster, on_close=on_close)
        group, pets, manual, players = self.db.load_roster(character)
        seg.ctx.group = group
        seg.ctx.pets = dict(pets)
        seg.ctx.manual_pets = set(manual)
        seg.ctx.players = set(players)
        seg.load_open(self.db.load_open_fight(file_id, generation))
        self._segs[key] = seg
        return seg

    def _emit_fight(self, summary: dict) -> None:
        now = time.monotonic()
        if now - self._last_fight_emit < 0.25:
            return
        self._last_fight_emit = now
        self.hub.publish({"type": "fight", "fight": summary})

    def list_fights(self, character: str | None = None, limit: int = 200, offset: int = 0) -> dict:
        with self.db.lock:
            rows = self.db.list_fights(character=character, limit=limit, offset=offset)
        return {"fights": rows, "count": len(rows)}

    def list_levels(self, character: str | None = None) -> dict:
        with self.db.lock:
            rows = self.db.list_level_events(character)
        return {"levels": rows}

    def fight_detail(self, fight_id: int, merge_pets: bool = True) -> dict | None:
        with self.db.lock:
            fight = self.db.get_fight_row(fight_id)
            if fight is None:
                return None
            source_rows = self.db.fight_source_rows(fight_id)
        start = _parse_iso(fight["start_ts"])
        end = _parse_iso(fight["end_ts"])
        seconds = MIN_SECONDS
        if start and end:
            seconds = max(MIN_SECONDS, (end - start).total_seconds())
        rows = []
        for src in source_rows:
            agg = SourceAgg(
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
            row = agg.to_row(seconds)
            row["kind"] = agg.source_kind
            rows.append(row)
        if merge_pets:
            rows = merge_pet_rows(rows)
            recompute_sdps(rows, seconds)
        else:
            rows.sort(key=lambda row: (-int(row["damage"]), row["source"]))
            for row in rows:
                row["pets"] = []
        friendly = {"self", "group", "pet"}
        outgoing = sum(int(row["damage"]) for row in rows if row["kind"] in friendly)
        incoming = sum(int(row["damage_taken"]) for row in rows if row["kind"] in friendly)
        import json
        raw_targets = json.loads(fight["targets_json"] or "[]")
        targets = list(raw_targets)
        return {
            "id": fight["id"],
            "character": fight["character"],
            "zone": fight["zone"],
            "instance": json.loads(fight["instance_json"]) if fight["instance_json"] else None,
            "start_ts": fight["start_ts"],
            "end_ts": fight["end_ts"],
            "duration_seconds": seconds,
            "targets": targets,
            "open": bool(fight["open"]),
            "player_died": bool(fight["player_died"]),
            "merge_pets": merge_pets,
            "totals": {
                "damage": outgoing,
                "damage_taken": incoming,
                "dps": outgoing / seconds,
                "sdps": outgoing / seconds,
            },
            "sources": rows,
        }

    def set_pet_owner(self, character: str, pet: str, owner: str | None) -> dict:
        with self.db.lock:
            self.db.bind_pet(character, pet, owner, "manual", True)
            self.db.commit()
            for seg in self._segs.values():
                if seg.character == character:
                    seg.ctx.bind_pet(pet, owner, "manual", manual=True)
        return {"ok": True, "character": character, "pet": pet, "owner": owner, "manual": True}

    def list_pets(self, character: str) -> list[dict]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT pet, owner, evidence, manual FROM pet_bindings WHERE character=? ORDER BY pet",
                (character,),
            ).fetchall()
        return [
            {"pet": row["pet"], "owner": row["owner"], "evidence": row["evidence"], "manual": bool(row["manual"])}
            for row in rows
        ]


class EventHub:
    """Fan-out for Server-Sent Events. Publish is safe from a worker thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list = []
        self._loop = None

    def subscribe(self):
        import asyncio
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=400)
        with self._lock:
            self._loop = loop
            self._subs.append(queue)
        return queue

    def unsubscribe(self, queue) -> None:
        with self._lock:
            if queue in self._subs:
                self._subs.remove(queue)

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
            loop = self._loop
        if not subs:
            return
        for queue in subs:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_offer, queue, event)
            else:
                _offer(queue, event)


def _offer(queue, event: dict) -> None:
    try:
        queue.put_nowait(event)
    except Exception:
        return
