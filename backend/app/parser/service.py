"""Replay, live tail, and query facade used by the REST API."""

from __future__ import annotations

import faulthandler
import json
import os
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .alerts import (
    cooldown_blocks,
    default_rules,
    match_rule,
    share_decode,
    share_encode,
)
from .breakdown import Breakdown
from .classify import classify_log_line
from .identity import normalize_override, resolve_current
from .discover import (
    DEFAULT_EQ_INSTALL,
    default_user_data,
    discover_logs,
    parse_log_name,
    read_eq_install,
    write_settings,
)
from .fights import MIN_SECONDS, Segmenter, SourceAgg, merge_pet_rows, recompute_sdps
from .sources import is_npc_pet_name
from .store import SCHEMA_VERSION, ParserDB, _parse_iso
from .tail import LogTail, TailBatch, backfill_offset
from .timeline import build_timeline

CHUNK_LINES = 50_000
# How long a UI read may wait for the database lock before answering 503.
READ_LOCK_TIMEOUT = 1.5
# A rebuild that has not advanced for this long is reported as stalled and
# every thread's stack is written to <user data>/logs/parser-stall.log.
UPGRADE_STALL_SECONDS = 60.0
_TEXT_SUFFIXES = {".txt", ".log"}


class LogRejected(ValueError):
    """The path is not a text combat log we are willing to read."""


class ParserBusy(RuntimeError):
    """A replay or rebuild holds the parser database. Answer now, do not wait.

    A request that waits on the lock for the whole replay parks one of the
    browser's six connections to the sidecar. A few parked requests starve the
    rest: config polls and item icons queue in Chromium and the app looks dead
    (1.1.1 first launch, 2026-09-26).
    """

    def __init__(self, message: str = "Parser data is being rebuilt. Try again when it finishes.") -> None:
        super().__init__(message)


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


def read_log_range(path: Path, start_offset: int, end_offset: int) -> list[dict]:
    """Re-read one fight's lines. The database does not store raw log text.

    ``end_offset`` is the byte offset where the fight's last line starts, so
    that line is included.
    """
    start = max(0, int(start_offset))
    end = max(0, int(end_offset))
    if end < start:
        start, end = end, start
    lines: list[dict] = []
    with open(path, "rb") as handle:
        handle.seek(start)
        offset = start
        while True:
            raw = handle.readline()
            if not raw:
                break
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            lines.append({"offset": offset, "text": text})
            next_offset = offset + len(raw)
            if next_offset > end:
                break
            offset = next_offset
    return lines


def _log_message(line: str) -> str:
    text = line or ""
    if text.startswith("[") and "] " in text:
        return text.split("] ", 1)[1].strip()
    return text.strip()


def _skeleton(message: str) -> str:
    import re
    text = re.sub(r"\d+(?:\.\d+)?", "N", message)
    text = re.sub(r"[A-Za-z][A-Za-z'`.-]*", "W", text)
    return text[:160]


class ParserService:
    def __init__(
        self,
        user_data: Path | None = None,
        db_path: Path | None = None,
        idle_seconds: float = 30.0,
        clock=None,
    ) -> None:
        self.user_data = Path(user_data) if user_data else default_user_data()
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.db = ParserDB(db_path or (self.user_data / "parser.db"))
        self._ensure_alert_rules()
        stored_idle = self.db.get_setting("idle_seconds")
        self.idle = float(stored_idle) if stored_idle else idle_seconds
        saved_folder = read_eq_install(self.user_data)
        stored_folder = self.db.get_setting("eq_install_folder") or ""
        # Cached so /config stays responsive while a rebuild holds the DB lock.
        self._eq_folder = saved_folder or stored_folder or DEFAULT_EQ_INSTALL
        self.hub = EventHub()
        self._segs: dict[tuple[int, int], Segmenter] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tail: LogTail | None = None
        self._live_path: str | None = None
        self._replay_lock = threading.Lock()
        self._replaying = False
        self._last_fight_emit = 0.0
        self._upgrade_thread: threading.Thread | None = None
        self._upgrading = False
        self._upgrade_error: str | None = None
        self._upgrade_progress: dict | None = None
        self._upgrade_stalled = False
        self._upgrade_watch: threading.Thread | None = None
        self._schema_version = self.db.stored_schema_version()
        self.clock = clock or datetime.now
        # Cached with the folder so /config does not wait on a rebuild's DB lock.
        self._retention_days = self.db.retention_days()
        # Returns immediately. A full-log rebuild takes long enough that it
        # must not sit on the process or the first /config request.
        self._maybe_start_upgrade()
        if not self._upgrading:
            self._prune_history()

    def close(self) -> None:
        """Stop a live tail and release the SQLite file so Windows can delete the temp dir."""
        self.stop_live()
        thread = self._upgrade_thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=120)
        self.db.close()

    def wait_for_upgrade(self, timeout: float = 120) -> bool:
        """Block until a background rebuild finishes. Tests use this."""
        thread = self._upgrade_thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout)
        return not self._upgrading

    def eq_folder(self) -> str:
        if self._eq_folder:
            return self._eq_folder
        return DEFAULT_EQ_INSTALL

    def set_eq_folder(self, folder: str) -> str:
        folder = folder.strip()
        write_settings(self.user_data, {"eqInstallFolder": folder})
        self.db.set_setting("eq_install_folder", folder)
        self._eq_folder = folder or DEFAULT_EQ_INSTALL
        return folder

    def set_idle(self, seconds: float) -> float:
        self.idle = float(seconds)
        self.db.set_setting("idle_seconds", str(self.idle))
        return self.idle

    def set_retention_days(self, days: int) -> int:
        stored = self.db.set_retention_days(int(days))
        self._retention_days = stored
        self._prune_history()
        return stored

    def _prune_history(self) -> int:
        """Apply the retention window. Safe to call when the window is 0."""
        return self.db.prune_fights(self.clock())

    def list_logs(self, root: str | None = None) -> dict:
        folder = root or self.eq_folder()
        return {"folder": folder, "logs": discover_logs(folder)}

    def config(self) -> dict:
        progress = self._upgrade_progress
        return {
            "eq_install_folder": self.eq_folder(),
            "default_eq_install_folder": DEFAULT_EQ_INSTALL,
            "idle_seconds": self.idle,
            "db_path": str(self.db.path),
            "user_data": str(self.user_data),
            "live": self._thread is not None and self._thread.is_alive(),
            "live_path": self._live_path,
            "upgrading": self._upgrading,
            "schema_version": self._schema_version,
            "upgrade_error": self._upgrade_error,
            "upgrade_progress": dict(progress) if progress else None,
            "upgrade_stalled": self._upgrade_stalled,
            "rebuilding": self._replaying,
            "fight_retention_days": self._retention_days,
        }

    def _maybe_start_upgrade(self) -> None:
        """Replay known logs when this database predates the current aggregates."""
        stored = self._schema_version
        paths = self.db.list_log_paths()
        if stored is None and not paths:
            self.db.set_schema_version(SCHEMA_VERSION)
            self._schema_version = SCHEMA_VERSION
            return
        effective = 1 if stored is None else stored
        if effective >= SCHEMA_VERSION:
            return
        self._upgrading = True
        self._upgrade_thread = threading.Thread(
            target=self._upgrade_worker,
            name="parser-upgrade",
            daemon=True,
        )
        self._upgrade_thread.start()
        self._upgrade_watch = threading.Thread(
            target=self._watch_upgrade,
            name="parser-upgrade-watchdog",
            daemon=True,
        )
        self._upgrade_watch.start()

    @contextmanager
    def read_guard(self, timeout: float = READ_LOCK_TIMEOUT):
        """Hold the DB lock for one UI read, or raise ParserBusy right away.

        Replays hold ``db.lock`` for the whole log. UI reads must not queue
        behind that; they answer 503 and the Parser tab refreshes when the
        rebuild's ``upgrade`` done event arrives.
        """
        if self._replaying:
            raise ParserBusy()
        if not self.db.lock.acquire(timeout=timeout):
            raise ParserBusy()
        try:
            yield
        finally:
            self.db.lock.release()

    def _stall_log_path(self) -> Path:
        return Path(self.user_data) / "logs" / "parser-stall.log"

    def dump_threads(self, reason: str) -> Path | None:
        """Append every thread's Python stack to the stall log. Never raises."""
        try:
            path = self._stall_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"\n=== {datetime.now().isoformat(timespec='seconds')} {reason}\n")
                handle.write(f"progress={self._upgrade_progress!r}\n")
                handle.flush()
                faulthandler.dump_traceback(file=handle, all_threads=True)
            return path
        except Exception:
            return None

    def _progress_marker(self) -> tuple:
        progress = self._upgrade_progress or {}
        return (progress.get("file_index"), progress.get("lines"), progress.get("offset"), progress.get("done"))

    def _watch_upgrade(self, poll: float = 5.0, stall_seconds: float | None = None) -> None:
        """Flag a rebuild that stopped advancing and record where it is stuck."""
        limit = UPGRADE_STALL_SECONDS if stall_seconds is None else stall_seconds
        marker = self._progress_marker()
        changed = time.monotonic()
        reported = False
        while self._upgrading:
            time.sleep(poll)
            current = self._progress_marker()
            now = time.monotonic()
            if current != marker:
                marker = current
                changed = now
                if self._upgrade_stalled:
                    self._upgrade_stalled = False
                    self.hub.publish({"type": "upgrade", "active": True, "done": False, "stalled": False})
                continue
            if not reported and now - changed >= limit and self._upgrading:
                reported = True
                self._upgrade_stalled = True
                self.dump_threads(f"parser rebuild made no progress for {int(now - changed)}s")
                self.hub.publish({"type": "upgrade", "active": True, "done": False, "stalled": True})

    def _upgrade_worker(self) -> None:
        error = None
        try:
            with self._replay_lock:
                self._replaying = True
                try:
                    self.stop_live()
                    self._segs.clear()
                    paths = self.db.list_log_paths()
                    self._upgrade_progress = {
                        "lines": 0,
                        "offset": 0,
                        "size": 0,
                        "path": paths[0] if paths else "",
                        "file_index": 0,
                        "file_count": len(paths),
                        "done": False,
                    }
                    self.hub.publish({
                        "type": "upgrade",
                        "active": True,
                        "done": False,
                        "file_count": len(paths),
                    })
                    self.db.clear_derived()
                    for index, path in enumerate(paths):
                        self._upgrade_one(index, len(paths), path)
                    self.db.set_schema_version(SCHEMA_VERSION)
                    self._schema_version = SCHEMA_VERSION
                    # Replay restores every fight on the log. Retention is a
                    # user setting and has to be applied again afterwards.
                    self._prune_history()
                finally:
                    self._replaying = False
        except Exception as exc:
            error = str(exc)
            self._upgrade_error = error
        finally:
            self._upgrading = False
            finished = dict(self._upgrade_progress or {})
            finished["done"] = True
            self._upgrade_progress = finished
            self.hub.publish({
                "type": "upgrade",
                "active": False,
                "done": True,
                "error": error,
                "schema_version": self._schema_version,
            })

    def _upgrade_one(self, index: int, total: int, path: str) -> None:
        file_path = Path(path)
        size = file_path.stat().st_size if file_path.is_file() else 0
        self._upgrade_progress = {
            "lines": 0,
            "offset": 0,
            "size": size,
            "path": path,
            "file_index": index,
            "file_count": total,
            "done": False,
        }
        self.hub.publish({
            "type": "upgrade",
            "active": True,
            "done": False,
            "path": path,
            "file_index": index,
            "file_count": total,
        })
        if not file_path.is_file():
            return
        try:
            self._consume(file_path, finalize=True)
        except (LogRejected, OSError):
            return

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
        # A rebuild holds this lock for the whole replay. Wait it out so a live
        # tail cannot insert rows the rebuild is about to replace.
        with self._replay_lock:
            pass
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

    def _accept_parsed(
        self,
        *,
        file_id: int,
        generation: int,
        offset: int,
        character: str,
        seg,
        event,
        message: str,
    ) -> bool:
        """Store one classified line. Consider does not move fight boundaries.

        A duplicate zone line still updates the in-memory zone so a consider
        that was not in the database yet can keep the zone from the log.
        Returns True when the row is new.
        """
        if event is None:
            self.consider_alerts(file_id, offset, None, message)
            return False
        if event.kind == "consider":
            event.zone = seg.zone
        inserted = self.db.insert_event(file_id, generation, offset, event)
        if not inserted:
            if event.kind == "zone":
                seg.zone = event.zone
                seg.instance = dict(event.instance) if event.instance else None
            return False
        self.db.insert_specialized(file_id, generation, offset, character, event)
        if event.kind != "consider":
            seg.observe(event, offset)
        self.consider_alerts(file_id, offset, event, event.text or message)
        if event.kind in {"who", "level"} and not self._replaying:
            self.hub.publish({"type": "roster", "character": character})
        self._maybe_toast(event, character)
        return True

    def _wish_keys(self, character: str) -> set[str]:
        import json

        from .dashboards import item_key

        raw = self.db.get_setting(f"wishes:{character.casefold()}") or "[]"
        try:
            names = json.loads(raw)
        except json.JSONDecodeError:
            names = []
        if not isinstance(names, list):
            return set()
        return {item_key(name) for name in names if isinstance(name, str) and item_key(name)}

    def _mote_min_grade(self) -> int | None:
        from .dashboards import parse_mote_grade_setting

        return parse_mote_grade_setting(self.db.get_setting("mote_notable_grade"))

    def _maybe_toast(self, event, character: str) -> None:
        if self._replaying or event is None:
            return
        from .dashboards import bis_name_keys, pos_item_keys, toast_for_event

        payload = toast_for_event(
            event,
            live=True,
            bis_keys=bis_name_keys(),
            wish_keys=self._wish_keys(character),
            pos_keys=pos_item_keys(),
            mote_min_grade=self._mote_min_grade(),
        )
        if payload:
            self.hub.publish({"type": "toast", "live": True, "toast": payload})

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
                    self._accept_parsed(
                        file_id=file_id,
                        generation=generation,
                        offset=line.offset,
                        character=character,
                        seg=seg,
                        event=event,
                        message=_log_message(line.text),
                    )
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
            # Test hook. Unset in production, so a normal replay never waits here.
            self._wait_for_test_gate()
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
                    msg = _log_message(text)
                    if event is None:
                        unclassified += 1
                        key = _skeleton(msg)
                        shapes[key] += 1
                        examples.setdefault(key, msg[:180])
                    else:
                        classified += 1
                    accepted = self._accept_parsed(
                        file_id=file_id,
                        generation=generation,
                        offset=offset,
                        character=character,
                        seg=seg,
                        event=event,
                        message=msg,
                    )
                    if event is not None:
                        if accepted:
                            inserted += 1
                        else:
                            duplicate += 1
                    if lines % CHUNK_LINES == 0:
                        if seg.fight is not None and seg.fight.open:
                            self.db.save_fight(file_id, generation, seg.fight)
                        self.db.mark_offset(file_id, offset, st.st_size)
                        self.db.commit()
                        self._publish_progress(
                            lines=lines,
                            classified=classified,
                            unclassified=unclassified,
                            offset=offset,
                            path=path,
                            size=st.st_size,
                        )
                        self.db.begin()
                if finalize:
                    seg.finish()
                elif seg.fight is not None and seg.fight.open:
                    self.db.save_fight(file_id, generation, seg.fight)
                self.db.mark_offset(file_id, st.st_size, st.st_size)
                self.db.prune_fights(self.clock())
                self.db.commit()
            except Exception:
                self.db.conn.rollback()
                raise
            fight_count = self.db.count_where("fights", file_id)
        elapsed = time.perf_counter() - started
        self._publish_progress(
            lines=lines,
            classified=classified,
            unclassified=unclassified,
            offset=st.st_size,
            path=path,
            size=st.st_size,
            done=True,
        )
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
                name = payload["name"]
                if isinstance(name, str) and name.lower() == character.lower():
                    name = character
                self.db.note_player(character, name, payload.get("classes"), payload.get("level"))
                classes = payload.get("classes")
                if classes:
                    self.db.upsert_loadout(character, name, classes, payload.get("level"), payload.get("ts"))
            elif op == "pet":
                self.db.bind_pet(character, payload["pet"], payload.get("owner"), payload.get("evidence") or "auto", False)
            elif op == "pet_clear":
                self.db.clear_pet(character, payload["pet"])
            elif op == "candidate":
                opened = self.db.note_candidate(
                    character,
                    payload["pet"],
                    payload.get("evidence") or "nominate",
                    payload.get("ts"),
                )
                if opened and not self._replaying:
                    self.hub.publish({"type": "roster", "character": character})
            elif op == "candidate_close":
                self.db.close_open_candidate(character, payload["pet"])

        def on_close(fight) -> None:
            self.db.save_fight(file_id, generation, fight)
            self._emit_fight(fight.summary())

        seg = Segmenter(character, idle_seconds=self.idle, on_roster=on_roster, on_close=on_close)
        roster = self.db.load_roster(character)
        seg.ctx.group = roster["group"]
        seg.ctx.pets = dict(roster["pets"])
        seg.ctx.pet_evidence = dict(roster["evidence"])
        seg.ctx.manual_pets = set(roster["manual"])
        seg.ctx.players = set(roster["players"])
        seg.ctx.allowlist = dict(roster["allowlist"])
        seg.ctx.candidates = dict(roster["candidates"])
        seg.ctx.dismissed = set(roster["dismissed"])
        seg.load_open(self.db.load_open_fight(file_id, generation))
        self._segs[key] = seg
        return seg

    def _publish_progress(
        self,
        *,
        lines: int,
        classified: int,
        unclassified: int,
        offset: int,
        path: Path,
        size: int,
        done: bool = False,
    ) -> None:
        payload = {
            "type": "progress",
            "lines": lines,
            "classified": classified,
            "unclassified": unclassified,
            "offset": offset,
            "size": size,
            "path": str(path),
        }
        if done:
            payload["done"] = True
        if self._upgrading:
            payload["upgrade"] = True
            previous = self._upgrade_progress or {}
            self._upgrade_progress = {
                "lines": lines,
                "offset": offset,
                "size": size,
                "path": str(path),
                "file_index": previous.get("file_index", 0),
                "file_count": previous.get("file_count", 1),
                "done": False,
            }
        self.hub.publish(payload)

    def _wait_for_test_gate(self) -> None:
        """Pause a replay while ``EQ_PARSER_REBUILD_GATE`` names a file.

        The file is polled until it contains ``release``. The caller already
        holds ``db.lock``, which is what made the 1.1.1 UI look frozen.
        Production never sets the variable. While paused, fight events are
        offered the same way a long replay offers them; ``_emit_fight`` drops
        those during a replay so 1.1.2 does not refetch into the lock.
        """
        gate = os.environ.get("EQ_PARSER_REBUILD_GATE", "").strip()
        if not gate:
            return
        path = Path(gate)
        deadline = time.monotonic() + 180.0
        while time.monotonic() < deadline:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                text = ""
            if "release" in text.lower():
                return
            self._emit_fight({"id": 0, "character": ""})
            time.sleep(0.35)

    def _emit_fight(self, summary: dict) -> None:
        # A replay closes hundreds of fights. Each event made the Parser tab
        # fetch fights, roster and detail, and every one of those requests
        # waited on db.lock until the replay ended. The replay's own progress
        # and done events are enough; the tab refreshes once when it finishes.
        if self._replaying:
            return
        now = time.monotonic()
        if now - self._last_fight_emit < 0.25:
            return
        self._last_fight_emit = now
        self.hub.publish({"type": "fight", "fight": summary})

    def list_fights(self, character: str | None = None, limit: int = 200, offset: int = 0) -> dict:
        with self.db.lock:
            self.db.prune_fights(self.clock())
            rows = self.db.list_fights(character=character, limit=limit, offset=offset)
        return {"fights": rows, "count": len(rows)}

    def clear_character_history(self, character: str) -> dict:
        """Remove one character's saved fights. Other characters stay.

        Pet bindings, dismissed prompts, the group allowlist, and /who loadouts
        stay with the character. Retention is a setting and is not cleared.
        """
        character = character.strip()
        with self._replay_lock:
            drop = [key for key, seg in self._segs.items() if seg.character == character]
            for key in drop:
                self._segs.pop(key, None)
            removed = self.db.clear_character_fights(character)
        return {"ok": True, **removed}

    def fight_lines(self, fight_id: int) -> dict | None:
        """Drill-down lines for one fight, re-read from the log byte range."""
        with self.db.lock:
            fight = self.db.get_fight_row(fight_id)
            if fight is None:
                return None
            file_row = self.db.file_row(int(fight["file_id"]))
            start = fight["start_offset"]
            end = fight["end_offset"]
            path = str(file_row["path"]) if file_row is not None else None
        result = {
            "id": int(fight["id"]),
            "path": path,
            "start_offset": start,
            "end_offset": end,
            "available": False,
            "lines": [],
        }
        if path is None or start is None or end is None:
            result["reason"] = "fight has no log byte range"
            return result
        file_path = Path(path)
        if not file_path.is_file():
            result["reason"] = "log file is missing"
            return result
        size = file_path.stat().st_size
        if int(start) >= size:
            result["reason"] = "log byte range is past the end of the file"
            return result
        result["lines"] = read_log_range(file_path, int(start), int(end))
        result["available"] = True
        return result

    def fight_timeline(self, fight_id: int, ability: str | None = None) -> dict | None:
        """DPS-over-time buckets re-read from the fight's log byte range."""
        with self.db.lock:
            fight = self.db.get_fight_row(fight_id)
            if fight is None:
                return None
            source_rows = self.db.fight_source_rows(fight_id)
            file_row = self.db.file_row(int(fight["file_id"]))
            start = fight["start_offset"]
            end = fight["end_offset"]
            path = str(file_row["path"]) if file_row is not None else None
            character = fight["character"]
            start_ts = fight["start_ts"]
            end_ts = fight["end_ts"]
        payload = {
            "id": int(fight["id"]),
            "available": False,
            "bin_seconds": 1,
            "buckets": [],
            "ability": ability.strip() if isinstance(ability, str) and ability.strip() else None,
            "start_ts": start_ts,
        }
        if path is None or start is None or end is None:
            payload["reason"] = "fight has no log byte range"
            return payload
        file_path = Path(path)
        if not file_path.is_file():
            payload["reason"] = "log file is missing"
            return payload
        size = file_path.stat().st_size
        if int(start) >= size:
            payload["reason"] = "log byte range is past the end of the file"
            return payload
        lines = read_log_range(file_path, int(start), int(end))
        begin = _parse_iso(start_ts)
        finish = _parse_iso(end_ts)
        duration = None
        if begin and finish:
            duration = max(MIN_SECONDS, (finish - begin).total_seconds())
        sources = [
            {
                "source": row["source"],
                "kind": row["source_kind"] or "unknown",
                "owner": row["owner"],
            }
            for row in source_rows
        ]
        curve = build_timeline(
            lines,
            character=character,
            sources=sources,
            start_ts=start_ts,
            duration_seconds=duration,
            ability=ability,
        )
        payload.update(curve)
        payload["available"] = True
        return payload

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
            breakdown = Breakdown.from_state(self.db.breakdown_state(fight_id))
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
        parts = breakdown.to_api(seconds)
        by_source: dict[str, list] = {}
        for ability in parts["abilities"]:
            by_source.setdefault(ability["source"], []).append(ability)
        for row in rows:
            row["abilities"] = by_source.get(row["source"], [])
        if merge_pets:
            rows = merge_pet_rows(rows)
            recompute_sdps(rows, seconds)
        else:
            rows.sort(key=lambda row: (-int(row["damage"]), row["source"]))
            for row in rows:
                row["pets"] = []
        for row in rows:
            row.setdefault("abilities", [])
            for pet in row.get("pets") or []:
                pet.setdefault("abilities", [])
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
            "abilities": parts["abilities"],
            "healing": parts["healing"],
            "tanking": parts["tanking"],
            "deaths": parts["deaths"],
            "resists": parts["resists"],
            "procs": parts["procs"],
            "multi_attack": parts["multi_attack"],
        }

    def list_economy(self, character: str | None = None, limit: int = 500, offset: int = 0) -> dict:
        """Loot, turn-in, and merge streams captured for the currencies ledger."""
        with self.db.lock:
            return {
                "loot": self.db.list_loot(character, limit, offset),
                "gives": self.db.list_gives(character, limit, offset),
                "merges": self.db.list_merges(character, limit, offset),
            }

    def currency_feed(self, character: str) -> list[dict]:
        """Idempotent loot, offer, and merge rows for one character."""
        with self.read_guard():
            return self.db.currency_feed(character)

    def set_pet_owner(self, character: str, pet: str, owner: str | None) -> dict:
        kind = "pet" if owner else ("npc" if is_npc_pet_name(pet) else "other")
        with self.db.lock:
            self.db.bind_pet(character, pet, owner, "manual", True)
            if owner:
                self.db.confirm_candidate(character, pet)
            else:
                self.db.dismiss_candidate(character, pet)
            self.db.relabel_source(character, pet, kind, owner)
            self.db.commit()
            for seg in self._segs.values():
                if seg.character == character:
                    seg.ctx.bind_pet(pet, owner, "manual", manual=True)
                    self._relabel_open_source(seg, pet, kind, owner)
        return {"ok": True, "character": character, "pet": pet, "owner": owner, "manual": True, "evidence": "manual"}

    def dismiss_candidate(self, character: str, pet: str) -> dict:
        """Hide the prompt. Does not write a pet binding."""
        with self.db.lock:
            self.db.dismiss_candidate(character, pet)
            self.db.commit()
            for seg in self._segs.values():
                if seg.character == character:
                    seg.ctx.dismiss_candidate(pet)
        return {"ok": True, "character": character, "pet": pet, "status": "dismissed"}

    def add_allow(self, character: str, member: str) -> dict:
        member = member.strip()
        if not member or member.lower() == character.lower():
            raise ValueError("Name a group member other than yourself")
        with self.db.lock:
            self.db.add_allowlist(character, member)
            self.db.relabel_kind(character, member, "group")
            self.db.commit()
            for seg in self._segs.values():
                if seg.character == character:
                    seg.ctx.add_allow(member)
                    self._relabel_open_kind(seg, member, "group")
        return {"ok": True, "character": character, "member": member}

    def remove_allow(self, character: str, member: str) -> dict:
        member = member.strip()
        with self.db.lock:
            self.db.remove_allowlist(character, member)
            still_grouped = False
            known = False
            for seg in self._segs.values():
                if seg.character != character:
                    continue
                seg.ctx.remove_allow(member)
                still_grouped = member.lower() in seg.ctx.group or still_grouped
                known = member in seg.ctx.players or known
            if not still_grouped:
                row = self.db.conn.execute(
                    "SELECT 1 FROM group_members WHERE character=? AND lower(member)=lower(?)",
                    (character, member),
                ).fetchone()
                still_grouped = row is not None
            if not still_grouped:
                player = self.db.conn.execute(
                    "SELECT 1 FROM known_players WHERE character=? AND lower(name)=lower(?)",
                    (character, member),
                ).fetchone()
                kind = "other" if (known or player is not None) else "npc"
                self.db.relabel_kind(character, member, kind)
                for seg in self._segs.values():
                    if seg.character == character:
                        self._relabel_open_kind(seg, member, kind)
            self.db.commit()
        return {"ok": True, "character": character, "member": member, "removed": True}

    def _ensure_alert_rules(self) -> None:
        existing = {rule.get("id") for rule in self.db.list_alert_rules()}
        for rule in default_rules():
            if rule["id"] not in existing:
                self.db.save_alert_rule(rule)
        self.db.commit()

    def _stamp(self) -> str:
        now = self.clock()
        if isinstance(now, datetime):
            return now.strftime("%Y-%m-%dT%H:%M:%S")
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    def set_identity(self, character: str, classes, level) -> dict:
        from ..item_catalog import _CLASS_TOKEN_TO_NAME
        trio, number = normalize_override(classes, level, _CLASS_TOKEN_TO_NAME)
        stamp = self._stamp()
        with self.db.lock:
            self.db.set_override(character, trio, number, stamp)
            self.db.commit()
            current = self._current_locked(character)
        if not self._replaying:
            self.hub.publish({"type": "roster", "character": character})
        self._notify_identity(character, trio, number, stamp, cleared=False)
        return {"ok": True, "character": character, "current": current}

    def clear_identity(self, character: str) -> dict:
        with self.db.lock:
            self.db.clear_override(character)
            self.db.commit()
            current = self._current_locked(character)
        if not self._replaying:
            self.hub.publish({"type": "roster", "character": character})
        self._notify_identity(character, None, None, self._stamp(), cleared=True)
        return {"ok": True, "character": character, "current": current}

    def _notify_identity(self, character: str, classes, level, ts: str, *, cleared: bool) -> None:
        if getattr(self, "_sync_silent", False):
            return
        listener = getattr(self, "sync_listener", None)
        if listener is None:
            return
        try:
            listener(character, {
                "ts": ts,
                "source": "manual",
                "type": "parser_identity",
                "payload": {"classes": classes, "level": level, "cleared": cleared},
            })
        except Exception:
            return

    def apply_synced_identity(self, character: str, identity: dict) -> None:
        """Apply a replayed override when it is newer than the one stored here."""
        if not isinstance(identity, dict):
            return
        with self.db.lock:
            current = self.db.get_override(character)
        current_ts = str((current or {}).get("ts") or "")
        incoming_ts = str(identity.get("ts") or "")
        if current is not None and incoming_ts < current_ts:
            return
        self._sync_silent = True
        try:
            if identity.get("cleared"):
                with self.db.lock:
                    self.db.clear_override(character)
                    self.db.commit()
                return
            classes = identity.get("classes")
            level = identity.get("level")
            stamp = incoming_ts or self._stamp()
            with self.db.lock:
                self.db.set_override(character, classes, level if isinstance(level, int) else level, stamp)
                self.db.commit()
        finally:
            self._sync_silent = False

    def _current_locked(self, character: str) -> dict | None:
        resolved = resolve_current(self.db.list_level_events(character), self.db.get_override(character))
        return resolved["current"]

    def roster(self, character: str) -> dict:
        with self.db.lock:
            group = self.db.list_group(character)
            allowlist = self.db.list_allowlist(character)
            candidates = self.db.list_candidates(character, "open")
            loadouts = self.db.list_loadouts(character)
            pets = self.list_pets_locked(character)
            observations = self.db.list_level_events(character)
            manual = self.db.get_override(character)
            resolved = resolve_current(observations, manual)
        return {
            "character": character,
            "group": [{"name": name, "via": "log"} for name in group],
            "allowlist": allowlist,
            "candidates": candidates,
            "loadouts": loadouts,
            "pets": pets,
            "current": resolved["current"],
            "history": resolved["history"],
        }

    def consider_alerts(self, file_id: int, offset: int, event, message: str) -> list[dict]:
        """Fire each matching rule once per log offset. A second replay adds nothing."""
        fired: list[dict] = []
        ts = None
        if event is not None and getattr(event, "ts", None) is not None:
            ts = event.ts.strftime("%Y-%m-%dT%H:%M:%S")
        text = message or (getattr(event, "text", "") if event is not None else "")
        for rule in self.db.list_alert_rules():
            rule_id = str(rule.get("id") or "")
            if not rule_id or self.db.alert_already_fired(rule_id, file_id, offset):
                continue
            alert = match_rule(rule, event, text)
            if not alert:
                continue
            if cooldown_blocks(self.db.last_alert_ts(rule_id), ts, int(rule.get("cooldown") or 0)):
                continue
            self.db.record_alert_fire(rule_id, file_id, offset, ts, alert)
            fired.append({
                "rule_id": rule_id,
                "name": rule.get("name") or "Alert",
                "message": alert,
                "ts": ts,
                "sound": rule.get("sound") or "speech",
                "sound_file": rule.get("sound_file") or "",
            })
        if fired and not self._replaying:
            self.hub.publish({"type": "alert", "alerts": fired})
        return fired

    def list_alert_rules(self) -> dict:
        with self.db.lock:
            rules = self.db.list_alert_rules()
        return {"rules": rules, "share": share_encode(rules)}

    def save_alert_rule(self, rule: dict) -> dict:
        rule_id = str(rule.get("id") or "").strip()
        if not rule_id:
            raise ValueError("id is required")
        with self.db.lock:
            current = {row.get("id"): row for row in self.db.list_alert_rules()}
            existing = current.get(rule_id) or {}
            if existing.get("gated") or existing.get("kind") == "charm_break":
                rule = dict(existing)
                rule["enabled"] = False
                rule["gated"] = True
            else:
                rule = dict(rule)
                rule["id"] = rule_id
                if existing.get("builtin"):
                    rule["builtin"] = True
                    rule["kind"] = existing.get("kind")
            self.db.save_alert_rule(rule)
            self.db.commit()
            rules = self.db.list_alert_rules()
        return {"ok": True, "rules": rules}

    def import_alert_share(self, text: str) -> dict:
        incoming = share_decode(text)
        with self.db.lock:
            have = {row.get("id") for row in self.db.list_alert_rules()}
            added = 0
            for rule in incoming:
                if rule["id"] in have or rule.get("builtin"):
                    continue
                rule["builtin"] = False
                self.db.save_alert_rule(rule)
                have.add(rule["id"])
                added += 1
            self.db.commit()
            rules = self.db.list_alert_rules()
        return {"ok": True, "added": added, "rules": rules}

    def recent_alerts(self) -> dict:
        with self.db.lock:
            rows = self.db.recent_alerts()
        return {"alerts": rows}

    def meters(self, character: str, scope: str = "fight") -> dict:
        """DPS and heals from stored fight rows. Zone scope sums those integers.

        Fight DPS uses the same active-time and fight-time rates as the Parser
        tab. Zone scope does not invent a rate; it sums damage and heals.
        """
        scope = "zone" if scope == "zone" else "fight"
        with self.db.lock:
            fights = self.db.list_fights(character=character, limit=200)
            if not fights:
                return {"scope": scope, "zone": None, "fight_id": None, "rows": [], "empty": True}
            latest = fights[0]
            zone = latest.get("zone")
            if scope == "fight":
                detail = self.fight_detail(int(latest["id"]), merge_pets=True)
                rows = []
                if detail:
                    for row in detail.get("sources") or []:
                        rows.append({
                            "source": row.get("source"),
                            "kind": row.get("kind"),
                            "damage": row.get("damage") or 0,
                            "dps": row.get("dps"),
                            "sdps": row.get("sdps"),
                            "hps": row.get("hps"),
                            "heals": row.get("heals") or 0,
                        })
                return {
                    "scope": "fight",
                    "zone": zone,
                    "fight_id": latest.get("id"),
                    "open": bool(latest.get("open")),
                    "rows": rows,
                    "empty": not rows,
                    "note": "DPS is this fight. Heals are the actual amount, not the parenthetical full amount.",
                }
            ids = [int(fight["id"]) for fight in fights if fight.get("zone") == zone]
            totals: dict[str, dict] = {}
            for fight_id in ids:
                for src in self.db.fight_source_rows(fight_id):
                    name = src["source"]
                    bucket = totals.setdefault(name, {
                        "source": name,
                        "kind": src["source_kind"],
                        "damage": 0,
                        "heals": 0,
                    })
                    bucket["damage"] += int(src["damage"] or 0)
                    bucket["heals"] += int(src["heals"] or 0)
            rows = sorted(totals.values(), key=lambda row: (-row["damage"], row["source"] or ""))
            return {
                "scope": "zone",
                "zone": zone,
                "fight_id": None,
                "rows": rows,
                "empty": not rows,
                "note": "Totals are the sum of saved fights in this zone. DPS stays on the fight meter.",
            }

    def list_pets_locked(self, character: str) -> list[dict]:
        rows = self.db.conn.execute(
            "SELECT pet, owner, evidence, manual FROM pet_bindings WHERE character=? ORDER BY pet",
            (character,),
        ).fetchall()
        return [
            {"pet": row["pet"], "owner": row["owner"], "evidence": row["evidence"], "manual": bool(row["manual"])}
            for row in rows
        ]

    def _relabel_open_source(self, seg: Segmenter, source: str, kind: str, owner: str | None) -> None:
        fight = seg.fight
        if fight is None:
            return
        for name, row in list(fight.sources.items()):
            if name.lower() != source.lower():
                continue
            row.source_kind = kind
            row.owner = owner

    def _relabel_open_kind(self, seg: Segmenter, source: str, kind: str) -> None:
        fight = seg.fight
        if fight is None:
            return
        for name, row in list(fight.sources.items()):
            if name.lower() != source.lower():
                continue
            if row.source_kind in {"self", "pet"}:
                continue
            row.source_kind = kind

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


    def remember_wishes(self, character: str, wishes: list[str]) -> dict:
        import json

        character = character.strip()
        clean = []
        seen = set()
        for name in wishes:
            text = str(name or "").strip()
            if not text or text.casefold() in seen:
                continue
            seen.add(text.casefold())
            clean.append(text)
        self.db.set_setting(f"wishes:{character.casefold()}", json.dumps(clean))
        return {"ok": True, "character": character, "wishes": clean}

    def set_mote_notable_grade(self, grade: int | None) -> dict:
        if grade is None:
            self.db.set_setting("mote_notable_grade", "")
        else:
            self.db.set_setting("mote_notable_grade", str(int(grade)))
        return {"ok": True, "mote_notable_grade": self._mote_min_grade()}

    def set_favourite(self, character: str, kind: str, name: str, starred: bool) -> dict:
        character = character.strip()
        kind = kind.strip()
        name = name.strip()
        if kind not in {"item", "mob"}:
            raise ValueError("kind must be item or mob")
        if not character or not name:
            raise ValueError("character and name are required")
        with self.db.lock:
            self.db.set_favourite(character, kind, name, starred, datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
            self.db.commit()
        return {"ok": True, "character": character, "kind": kind, "name": name, "starred": starred}

    def set_user_lockout(self, character: str, mob: str, note: str | None, clear: bool = False) -> dict:
        character = character.strip()
        mob = mob.strip()
        if not character or not mob:
            raise ValueError("character and mob are required")
        with self.db.lock:
            self.db.set_user_lockout(character, mob, note, datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), clear=clear)
            self.db.commit()
            rows = self.db.list_user_lockouts(character)
        return {"ok": True, "lockouts": rows}

    def _notable_sets(self, character: str, wishes: list[str] | None) -> tuple[set[str], set[str], set[str], set[str]]:
        from .dashboards import bis_name_keys, item_key, pos_item_keys

        if wishes is not None:
            self.remember_wishes(character, wishes)
        wish_keys = self._wish_keys(character)
        favourite_keys = {item_key(row["name"]) for row in self.db.list_favourites(character, "item")}
        return set(bis_name_keys()), wish_keys, set(pos_item_keys()), favourite_keys

    def dashboard_loot(self, character: str, wishes: list[str] | None = None, limit: int = 300) -> dict:
        from .dashboards import annotate_loot_row, drop_rates

        character = character.strip()
        with self.read_guard():
            rows = self.db.list_loot(character, limit=limit, offset=0)
            rates = drop_rates(self.db.loot_counts_by_mob(character), self.db.slain_counts_by_mob(character))
            bis_keys, wish_keys, pos_keys, favourite_keys = self._notable_sets(character, wishes)
            grade = self._mote_min_grade()
            favourites = self.db.list_favourites(character)
        annotated = [
            annotate_loot_row(
                row,
                bis_keys=bis_keys,
                wish_keys=wish_keys,
                pos_keys=pos_keys,
                favourite_keys=favourite_keys,
                mote_min_grade=grade,
            )
            for row in rows
        ]
        return {
            "character": character,
            "loot": annotated,
            "drop_rates": rates,
            "mote_notable_grade": grade,
            "favourites": favourites,
        }

    def dashboard_leveling(self, character: str) -> dict:
        from ..spell_buffs import load_spell_buffs
        from .dashboards import leveling_summary, zone_level_requirement

        character = character.strip()
        with self.read_guard():
            xp_rows = self.db.list_xp_events(character)
            level_rows = self.db.list_level_events(character)
            current = self._current_locked(character) or {}
            fights = self.db.list_fights(character=character, limit=1)
        zone = fights[0]["zone"] if fights else None
        classes = current.get("classes")
        level = current.get("level")
        summary = leveling_summary(
            xp_rows,
            level_rows,
            classes=classes,
            level=level,
            spells=load_spell_buffs().get("buffs") or [],
            zone=zone,
            zone_level=zone_level_requirement(zone),
        )
        summary["character"] = character
        return summary

    def dashboard_raids(self, character: str, now: datetime | None = None) -> dict:
        from datetime import timezone

        from .dashboards import mob_index_by_key, name_key, raid_kills

        character = character.strip()
        moment = now or datetime.now(timezone.utc)
        with self.read_guard():
            slain = self.db.list_your_slain(character, limit=2000)
            fights = self.db.list_fights(character=character, limit=500)
            lockouts = self.db.list_user_lockouts(character)
        payload = raid_kills(slain, fights, mob_index_by_key(), moment)
        known = {name_key(row.get("name")) for row in mob_index_by_key().values()}
        payload["user_lockouts"] = lockouts
        payload["unverified_note"] = (
            "A lockout you type is UNVERIFIED. It is not the Tuesday reset unless you say so in the note."
        )
        payload["character"] = character
        payload["indexed_mobs"] = len(known)
        return payload

    def dashboard_considered(self, character: str, limit: int = 40) -> dict:
        character = character.strip()
        with self.read_guard():
            rows = self.db.list_consider(character, limit=limit)
            favourites = {row["name"].casefold() for row in self.db.list_favourites(character, "mob")}
        for row in rows:
            row["favourite"] = str(row.get("mob") or "").casefold() in favourites
        return {"character": character, "considered": rows}

    def dashboard_mob(self, character: str, name: str) -> dict:
        from ..mob_hub import mob_detail
        from .dashboards import drop_rate, name_key

        character = character.strip()
        name = name.strip()
        with self.read_guard():
            considers = [row for row in self.db.list_consider(character, limit=500) if name_key(row.get("mob")) == name_key(name)]
            loots = [row for row in self.db.list_loot(character, limit=2000) if name_key(row.get("from")) == name_key(name)]
            slain = [row for row in self.db.list_your_slain(character, limit=2000) if name_key(row.get("mob")) == name_key(name)]
            starred = any(
                name_key(row["name"]) == name_key(name)
                for row in self.db.list_favourites(character, "mob")
            )
        hub = mob_detail(name, fetch=False)
        wiki_level = (hub.get("level") or "").strip() if isinstance(hub, dict) else ""
        return {
            "character": character,
            "name": hub.get("name") if isinstance(hub, dict) and hub.get("name") else name,
            "favourite": starred,
            "your_considers": considers,
            "your_loots": loots,
            "your_kills": len(slain),
            "drop_rate": drop_rate(len(loots), len(slain)),
            "drop_rate_text": "unknown" if not slain else f"{len(loots)} / {len(slain)}",
            "consider_levels": [
                {"level": row.get("level"), "source": "consider line", "ts": row.get("ts")}
                for row in considers if row.get("level") is not None
            ],
            "hub": hub,
            "wiki_level": wiki_level or None,
            "wiki_level_note": None if wiki_level else "No sourced wiki level is cached for this mob.",
        }

    def dashboard_overview(self, character: str, wishes: list[str] | None = None) -> dict:
        from .dashboards import curve_from_timeline, overview_cards

        character = character.strip()
        with self.read_guard():
            fights = self.db.list_fights(character=character, limit=30)
            loots = self.db.list_loot(character, limit=8)
            slain = self.db.list_your_slain(character, limit=8)
            if wishes is not None:
                self.remember_wishes(character, wishes)
            alive = []
            dead = []
            fight = fights[0] if fights else None
            if fight is not None:
                import json
                raw = self.db.get_fight_row(int(fight["id"]))
                parsed = {}
                if raw is not None and raw["targets_json"]:
                    parsed = json.loads(raw["targets_json"])
                if isinstance(parsed, dict):
                    alive = [name for name, up in parsed.items() if up]
                    dead = [name for name, up in parsed.items() if not up]
                elif isinstance(parsed, list):
                    alive = [str(name) for name in parsed]
        zones = []
        seen = set()
        for row in fights:
            zone = row.get("zone") or ""
            if not zone or zone in seen:
                continue
            seen.add(zone)
            zones.append({"zone": zone, "instance": row.get("instance"), "ts": row.get("start_ts")})
            if len(zones) >= 8:
                break
        leveling = self.dashboard_leveling(character)
        cards = overview_cards(
            fight=fight,
            targets_alive=alive,
            targets_dead=dead,
            recent_loots=loots,
            recent_kills=slain,
            zones=zones,
            leveling=leveling,
        )
        curve = {"available": False, "buckets": [], "bin_seconds": None, "reason": "No fight yet."}
        fight_id = cards["dps"].get("fight_id")
        if fight_id:
            try:
                curve = curve_from_timeline(self.fight_timeline(int(fight_id)))
            except ParserBusy:
                curve = {"available": False, "buckets": [], "bin_seconds": None, "reason": "Parser is rebuilding."}
        cards["dps"]["curve"] = curve
        cards["character"] = character
        cards["caveat"] = leveling.get("caveat")
        return cards

    def dashboard_overlay(self, character: str, kind: str) -> dict:
        character = character.strip()
        kind = "con" if kind == "con" else "xp"
        with self.read_guard():
            if kind == "con":
                rows = self.db.list_consider(character, limit=1)
                latest = rows[0] if rows else None
                return {
                    "kind": "con",
                    "character": character,
                    "consider": latest,
                    "note": None if latest else "No consider line yet. Consider a mob in game.",
                }
            xp_rows = self.db.list_xp_events(character)
        from .dashboards import leveling_summary

        summary = leveling_summary(xp_rows, [])
        latest = None
        for row in reversed(xp_rows):
            latest = row
            break
        return {
            "kind": "xp",
            "character": character,
            "latest": latest,
            "levels_per_hour": summary.get("levels_per_hour"),
            "progress_pct": summary.get("progress_pct"),
            "bar_known": summary.get("bar_known"),
            "hours_to_level": summary.get("hours_to_level"),
            "honesty": summary.get("honesty"),
            "xp_lines_without_percent": summary.get("xp_lines_without_percent"),
        }

    def _companion_key(self, character: str) -> str:
        return "companion:" + character.strip().casefold()

    def _companion_blob(self, character: str) -> dict:
        from .companion import normalize_blob

        raw = self.db.get_setting(self._companion_key(character))
        if not raw:
            return normalize_blob({})
        try:
            return normalize_blob(json.loads(raw))
        except json.JSONDecodeError:
            return normalize_blob({})

    def _save_companion_blob(self, character: str, blob: dict) -> None:
        self.db.set_setting(self._companion_key(character), json.dumps(blob))

    def companion_buffs(self, character: str, loadout: str, now: datetime | None = None) -> dict:
        from .companion import buff_timers, durations_for_loadout

        character = character.strip()
        blob = self._companion_blob(character)
        with self.read_guard():
            events = self.db.list_companion_events(character)
        payload = buff_timers(
            events,
            loadout=loadout,
            durations=durations_for_loadout(blob, loadout),
            manual=blob.get("manual_buffs") or [],
            now=now or self.clock(),
        )
        payload["character"] = character
        return payload

    def companion_set_duration(self, character: str, loadout: str, spell: str, seconds: int | None) -> dict:
        from .companion import set_duration

        character = character.strip()
        blob = self._companion_blob(character)
        set_duration(blob, loadout, spell, seconds)
        self._save_companion_blob(character, blob)
        return self.companion_buffs(character, loadout)

    def companion_manual_buff(
        self,
        character: str,
        loadout: str,
        spell: str,
        target: str,
        seconds: int | None,
        action: str,
    ) -> dict:
        from .companion import parse_user_seconds

        character = character.strip()
        spell = spell.strip()
        if not spell:
            raise ValueError("spell name is required")
        if seconds is not None:
            seconds = parse_user_seconds(seconds)
        blob = self._companion_blob(character)
        manuals = [row for row in (blob.get("manual_buffs") or []) if isinstance(row, dict)]
        if action == "clear":
            manuals = [
                row for row in manuals
                if not (
                    str(row.get("loadout") or "") == loadout
                    and str(row.get("spell") or "").casefold() == spell.casefold()
                    and str(row.get("target") or "You").casefold() == (target or "You").strip().casefold()
                )
            ]
        else:
            manuals.append({
                "id": f"{loadout}|{spell}|{target or 'You'}|{self.clock().isoformat(timespec='seconds')}",
                "loadout": loadout,
                "spell": spell,
                "target": (target or "You").strip() or "You",
                "started": self.clock().isoformat(timespec="seconds"),
                "duration_seconds": seconds,
            })
        blob["manual_buffs"] = manuals[-80:]
        self._save_companion_blob(character, blob)
        return self.companion_buffs(character, loadout)

    def companion_respawns(self, character: str, now: datetime | None = None) -> dict:
        from .companion import respawn_timers

        character = character.strip()
        blob = self._companion_blob(character)
        with self.read_guard():
            kills = self.db.list_slain_with_zone(character)
        payload = respawn_timers(kills, blob.get("respawns") or {}, now=now or self.clock())
        payload["character"] = character
        return payload

    def companion_set_respawn(self, character: str, zone: str, mob: str, seconds: int | None) -> dict:
        from .companion import set_respawn

        character = character.strip()
        blob = self._companion_blob(character)
        set_respawn(blob, zone or "", mob, seconds)
        self._save_companion_blob(character, blob)
        return self.companion_respawns(character)

    def companion_maps(self, character: str) -> dict:
        from ..zones import get_zone
        from .companion import map_rows

        character = character.strip()
        with self.read_guard():
            seen = self.db.list_zones_seen(character)
        payload = map_rows(seen, get_zone)
        payload["character"] = character
        return payload

    def companion_exaltations(self, character: str, loadout: str, items: list[dict] | None) -> dict:
        from ..item_catalog import get_item_by_name
        from .companion import exaltation_plan

        character = character.strip()
        blob = self._companion_blob(character)
        notes = (blob.get("exaltation_notes") or {}).get(loadout) or {}

        def lookup(name: str):
            found = get_item_by_name(name, enrich=False) if name else None
            if not isinstance(found, dict):
                return None
            stats = found.get("stats_plus0") or {}
            return stats if isinstance(stats, dict) and stats else None

        payload = exaltation_plan(items or [], loadout=loadout, notes=notes if isinstance(notes, dict) else {}, stat_lookup=lookup)
        payload["character"] = character
        return payload

    def companion_set_exaltation_note(self, character: str, loadout: str, socket_key: str, target: str) -> dict:
        character = character.strip()
        socket_key = socket_key.strip()
        if not socket_key:
            raise ValueError("socket is required")
        blob = self._companion_blob(character)
        notes = blob.setdefault("exaltation_notes", {}).setdefault(loadout, {})
        if not isinstance(notes, dict):
            notes = {}
            blob["exaltation_notes"][loadout] = notes
        cleaned = target.strip()
        if cleaned:
            notes[socket_key] = cleaned[:200]
        else:
            notes.pop(socket_key, None)
        self._save_companion_blob(character, blob)
        return {"ok": True, "loadout": loadout, "key": socket_key, "target": notes.get(socket_key, "")}

    def companion_resists(
        self,
        character: str,
        loadout: str,
        classes: list[str],
        level: int | None,
        race: str | None,
        worn: list[dict],
        assume_max_aas: bool,
        save_as: str | None,
    ) -> dict:
        from ..item_catalog import get_item_by_name
        from .companion import resist_profile

        def lookup(name: str):
            found = get_item_by_name(name, enrich=False) if name else None
            if not isinstance(found, dict):
                return None
            stats = found.get("stats_plus0") or {}
            return stats if isinstance(stats, dict) and stats else None

        payload = resist_profile(
            loadout=loadout,
            classes=classes,
            level=level,
            race=race,
            worn=worn,
            stat_lookup=lookup,
            assume_max_aas=assume_max_aas,
        )
        payload["character"] = character.strip()
        if save_as and save_as.strip():
            blob = self._companion_blob(character)
            bucket = blob.setdefault("resist_profiles", {}).setdefault(loadout, [])
            if not isinstance(bucket, list):
                bucket = []
                blob["resist_profiles"][loadout] = bucket
            bucket.append({
                "name": save_as.strip()[:80],
                "saved_at": self.clock().isoformat(timespec="seconds"),
                "snapshot": json.loads(json.dumps(payload, default=str)),
            })
            blob["resist_profiles"][loadout] = bucket[-12:]
            self._save_companion_blob(character, blob)
            payload["saved"] = True
        else:
            blob = self._companion_blob(character)
        payload["saved_profiles"] = (blob.get("resist_profiles") or {}).get(loadout) or []
        return payload

    def companion_export(self, character: str, ui: dict | None) -> dict:
        from .companion import export_profile

        character = character.strip()
        return export_profile(self._companion_blob(character), ui, character)

    def companion_import(self, character: str, profile: dict) -> dict:
        from .companion import import_profile, merge_profile

        character = character.strip()
        incoming = import_profile(profile)
        blob = merge_profile(self._companion_blob(character), incoming)
        self._save_companion_blob(character, blob)
        return {"ok": True, "character": character, "ui": incoming.get("ui") or {}}

    def companion_feedback(self) -> bytes:
        from .companion import feedback_zip, perf_readout, safe_log_name

        log_dir = Path(self.user_data) / "logs"
        files = []
        if log_dir.is_dir():
            for path in sorted(log_dir.iterdir()):
                if not path.is_file() or safe_log_name(path.name) is None:
                    continue
                data = path.read_bytes()
                if len(data) > 200_000:
                    data = data[-200_000:]
                files.append((path.name, data))
        settings = {"companion_note": "Per-character companion entries stay in the profile export. This zip is logs and the perf readout."}
        return feedback_zip(settings, files, perf_readout())


class EventHub:
    """Fan-out for Server-Sent Events. Publish is safe from a worker thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list = []
        self._loop = None

    def subscribe(self, types: list[str] | None = None):
        import asyncio
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=400)
        wanted = None
        if types:
            wanted = frozenset(str(item).strip() for item in types if str(item).strip())
            if not wanted:
                wanted = None
        with self._lock:
            self._loop = loop
            self._subs.append((queue, wanted))
        return queue

    def unsubscribe(self, queue) -> None:
        with self._lock:
            self._subs = [row for row in self._subs if (row[0] if isinstance(row, tuple) else row) is not queue]

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
            loop = self._loop
        if not subs:
            return
        etype = str(event.get("type") or "")
        for row in subs:
            queue, wanted = row if isinstance(row, tuple) else (row, None)
            if wanted is not None and etype not in wanted:
                continue
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_offer, queue, event)
            else:
                _offer(queue, event)


def _offer(queue, event: dict) -> None:
    try:
        queue.put_nowait(event)
    except Exception:
        return
