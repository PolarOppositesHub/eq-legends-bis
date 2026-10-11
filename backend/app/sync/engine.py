"""Local queue, migration, and a sync pass.

Offline edits stay in ``sync/queue.jsonl`` under the sidecar user-data folder
until a provider accepts them. Each device still writes only its own jsonl.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable

from .layout import (
    ICLOUD_TIP,
    ICLOUD_WAITING,
    SyncAuthExpired,
    SyncError,
    SyncOffline,
    WaitingForCloud,
    atomic_write,
    character_folder_name,
)
from .model import (
    decode_jsonl,
    encode_jsonl,
    log_event_id,
    make_event,
    new_id,
    project_all,
    sort_key,
    union_events,
)
from .providers import (
    ONEDRIVE_AUTHORITY,
    ONEDRIVE_CLIENT_ID,
    ONEDRIVE_SCOPES,
    FolderProvider,
    OneDriveProvider,
    default_graph_transport,
    provider_for,
)


def _stamp_now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class SyncEngine:
    def __init__(self, user_data: str | Path, *, device_id: str | None = None, clock: Callable[[], str] | None = None) -> None:
        self.user_data = Path(user_data)
        self.clock = clock or _stamp_now
        self._access_token = ""
        self._transport = None
        self._bound: Any = None
        self.state = self._load_state(device_id)
        self._remote: dict[str, list[dict[str, Any]]] = {}

    def _dir(self) -> Path:
        path = self.user_data / "sync"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_state(self, device_id: str | None) -> dict[str, Any]:
        path = self.user_data / "sync" / "local.json"
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        if device_id:
            data["device_id"] = device_id
        if not data.get("device_id"):
            data["device_id"] = uuid.uuid4().hex
        data.setdefault("device_name", "This PC")
        data.setdefault("provider", "")
        data.setdefault("folder", "")
        data.setdefault("account", "")
        data.setdefault("migrated", False)
        data.setdefault("last_synced", None)
        data.setdefault("status", "idle")
        data.setdefault("error", "")
        data.setdefault("message", "")
        data.setdefault("auth_expired", False)
        return data

    def _save_state(self) -> None:
        path = self._dir() / "local.json"
        atomic_write(path, json.dumps(self.state, indent=2, ensure_ascii=False) + "\n")

    @property
    def device_id(self) -> str:
        return str(self.state.get("device_id") or "")

    def status(self) -> dict[str, Any]:
        provider = str(self.state.get("provider") or "")
        queued = self._read_queue()
        pending = sum(len(events) for events in queued.values())
        return {
            "ok": True,
            "provider": provider,
            "account": self.state.get("account") or "",
            "folder": self.state.get("folder") or "",
            "device_id": self.device_id,
            "device_name": self.state.get("device_name") or "",
            "last_synced": self.state.get("last_synced"),
            "status": self.state.get("status") or "idle",
            "error": self.state.get("error") or "",
            "message": self.state.get("message") or "",
            "auth_expired": bool(self.state.get("auth_expired")),
            "pending": pending,
            "migrated": bool(self.state.get("migrated")),
            "icloud_tip": ICLOUD_TIP if provider == "folder" else "",
            "onedrive": {
                "client_id": ONEDRIVE_CLIENT_ID,
                "authority": ONEDRIVE_AUTHORITY,
                "scopes": ONEDRIVE_SCOPES,
                "redirect": "http://localhost:<port>",
            },
        }

    def configure(
        self,
        *,
        provider: str | None = None,
        folder: str | None = None,
        device_name: str | None = None,
    ) -> dict[str, Any]:
        if provider is not None:
            if provider not in {"", "folder", "onedrive"}:
                if provider == "google":
                    raise SyncError("Google Drive sync is planned for 1.1.12 and is not in this version.")
                raise SyncError("Choose Sync folder or OneDrive.")
            self.state["provider"] = provider
        if folder is not None:
            self.state["folder"] = str(folder)
        if device_name is not None:
            name = " ".join(str(device_name).split())
            if not name:
                raise SyncError("Device name is required.")
            if len(name) > 60:
                raise SyncError("Device name is too long.")
            self.state["device_name"] = name
        self._save_state()
        return self.status()

    def bind_provider(self, provider: Any) -> None:
        self._bound = provider
        self.state["provider"] = getattr(provider, "kind", self.state.get("provider") or "")
        self._save_state()

    def set_onedrive_session(self, access_token: str, account: str = "", transport: Any = None) -> dict[str, Any]:
        self._access_token = access_token or ""
        if transport is not None:
            self._transport = transport
        else:
            self._transport = default_graph_transport()
        self.state["provider"] = "onedrive"
        self.state["account"] = account or self.state.get("account") or ""
        self.state["error"] = ""
        self.state["auth_expired"] = False
        self._save_state()
        return self.status()

    def clear_onedrive_session(self) -> dict[str, Any]:
        self._access_token = ""
        self.state["account"] = ""
        if self.state.get("provider") == "onedrive":
            self.state["status"] = "idle"
            self.state["message"] = ""
        self._save_state()
        return self.status()

    def _provider(self) -> Any:
        if self._bound is not None:
            return self._bound
        kind = str(self.state.get("provider") or "")
        if kind == "folder":
            folder = str(self.state.get("folder") or "")
            if not folder:
                raise SyncError("Choose a sync folder.")
            return FolderProvider(folder)
        if kind == "onedrive":
            if not self._access_token:
                raise SyncError("Sign in to OneDrive.")
            if self._transport is None:
                self._transport = default_graph_transport()
            return OneDriveProvider(self._transport, self._access_token)
        if kind == "google":
            return provider_for("google")
        raise SyncError("Choose Sync folder or OneDrive.")

    def _read_queue(self) -> dict[str, list[dict[str, Any]]]:
        path = self.user_data / "sync" / "queue.jsonl"
        if not path.is_file():
            return {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        for line in text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            character = str(item.get("character") or "")
            event = item.get("event")
            if not character or not isinstance(event, dict) or not event.get("id"):
                continue
            grouped.setdefault(character, []).append(event)
        for character, events in list(grouped.items()):
            grouped[character] = union_events([events])
        return grouped

    def _write_queue(self, grouped: dict[str, list[dict[str, Any]]]) -> None:
        lines: list[str] = []
        for character, events in grouped.items():
            for event in events:
                lines.append(json.dumps({"character": character, "event": event}, ensure_ascii=False, separators=(",", ":")))
        text = ("\n".join(lines) + "\n") if lines else ""
        atomic_write(self._dir() / "queue.jsonl", text)

    def _queue_event(self, character: str, event: dict[str, Any]) -> bool:
        try:
            folder_name = character_folder_name(character)
        except ValueError as exc:
            raise SyncError(str(exc)) from exc
        grouped = self._read_queue()
        current = grouped.get(folder_name) or []
        if any(row.get("id") == event.get("id") for row in current):
            return False
        current.append(event)
        grouped[folder_name] = current
        self._write_queue(grouped)
        return True

    def events_by_character(self) -> dict[str, list[dict[str, Any]]]:
        merged: dict[str, list[dict[str, Any]]] = {}
        for source in (self._remote, self._read_queue()):
            for character, events in source.items():
                merged[character] = union_events([merged.get(character) or [], events])
        return merged

    def projection(self) -> dict[str, Any]:
        return project_all(self.events_by_character())

    def append_log_line(self, character: str, raw_line: str, line_ts: str) -> dict[str, Any]:
        """Record one log line. The same line on this PC is stored once."""
        event = make_event(
            event_id=log_event_id(character, raw_line, line_ts, self.device_id),
            ts=line_ts,
            device_id=self.device_id,
            source="log",
            event_type="log_line",
            payload={"raw": raw_line},
        )
        added = self._queue_event(character, event)
        return {"ok": True, "id": event["id"], "added": added}

    def on_currency(self, character: str, hint: dict[str, Any]) -> None:
        """CurrencyBook calls this after a new ledger row or a revert. Failures stay local."""
        try:
            event_type = str(hint.get("type") or "currency")
            source = str(hint.get("source") or "manual")
            if source not in {"log", "manual", "import"}:
                source = "manual"
            ts = str(hint.get("ts") or self.clock())
            payload = dict(hint.get("payload") or {})
            event_id = str(hint.get("id") or "")
            raw = payload.get("raw")
            if source == "log" and raw:
                event_id = log_event_id(character, str(raw), ts, self.device_id)
            if not event_id:
                event_id = new_id()
            event = make_event(
                event_id=event_id,
                ts=ts,
                device_id=self.device_id,
                source=source,
                event_type=event_type,
                payload=payload,
            )
            self._queue_event(character, event)
        except Exception:
            return

    def migrate(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Copy existing local data into events once, keeping the timestamps it already has."""
        if self.state.get("migrated"):
            return {"ok": True, "already": True, "added": 0}
        added = self._import_snapshot(snapshot, migration=True)
        self.state["migrated"] = True
        self._save_state()
        return {"ok": True, "already": False, "added": added}

    def capture(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Migrate on the first call, then append only what changed since the last replay."""
        if not self.state.get("migrated"):
            result = self.migrate(snapshot)
            return {**result, "projection": self.projection()}
        added = self._import_snapshot(snapshot, migration=False)
        return {"ok": True, "added": added, "projection": self.projection()}

    def _import_snapshot(self, snapshot: dict[str, Any], *, migration: bool) -> int:
        added = 0
        characters = snapshot.get("characters") or {}
        if not isinstance(characters, dict):
            return 0
        current = self.events_by_character()
        for name, body in characters.items():
            if not isinstance(body, dict):
                continue
            try:
                character = character_folder_name(str(name))
            except ValueError:
                continue
            have = current.get(character) or []
            known_ids = {str(event.get("id")) for event in have}
            projected = project_all({character: have})["characters"].get(character) or {}
            fresh: list[dict[str, Any]] = []
            fresh.extend(self._currency_events(character, body, known_ids, migration))
            fresh.extend(self._wish_events(character, body, projected, migration))
            fresh.extend(self._identity_events(character, body, projected, migration))
            fresh.extend(self._setting_events(character, body, projected, migration))
            fresh.extend(self._inventory_events(character, body, known_ids))
            for event in fresh:
                if event["id"] in known_ids:
                    continue
                if self._queue_event(character, event):
                    known_ids.add(event["id"])
                    added += 1
            current[character] = union_events([have, fresh])
        return added

    def _currency_events(self, character: str, body: dict[str, Any], known_ids: set[str], migration: bool) -> list[dict[str, Any]]:
        if not migration or "currency_entries" not in body:
            return []
        events: list[dict[str, Any]] = []
        for entry in body.get("currency_entries") or []:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            event_id = str(entry["id"])
            if event_id in known_ids:
                continue
            source = str(entry.get("source") or "manual")
            if source.startswith("log"):
                mapped = "log"
            elif source == "inventory_reconcile":
                mapped = "import"
            else:
                mapped = "manual"
            events.append(make_event(
                event_id=event_id,
                ts=str(entry.get("ts") or self.clock()),
                device_id=self.device_id,
                source=mapped,
                event_type="currency",
                payload={"entry": entry},
            ))
        return events

    def _wish_events(self, character: str, body: dict[str, Any], projected: dict[str, Any], migration: bool) -> list[dict[str, Any]]:
        if "wishes" not in body:
            return []
        wanted: list[tuple[str, str | None]] = []
        for item in body.get("wishes") or []:
            if isinstance(item, str):
                wanted.append((item.strip(), None))
            elif isinstance(item, dict) and item.get("name"):
                wanted.append((str(item["name"]).strip(), item.get("ts")))
        wanted = [(name, ts) for name, ts in wanted if name]
        have = {name.casefold() for name in (projected.get("wishes") or [])}
        events: list[dict[str, Any]] = []
        for name, ts in wanted:
            if name.casefold() in have:
                continue
            event_id = f"migrate:wish:{character.casefold()}:{name.casefold()}" if migration else new_id()
            events.append(make_event(
                event_id=event_id,
                ts=str(ts or self.clock()),
                device_id=self.device_id,
                source="manual",
                event_type="wish",
                payload={"name": name, "pinned": True},
            ))
        if migration:
            return events
        wanted_folds = {name.casefold() for name, _ts in wanted}
        for name in projected.get("wishes") or []:
            if str(name).casefold() in wanted_folds:
                continue
            events.append(make_event(
                event_id=new_id(),
                ts=self.clock(),
                device_id=self.device_id,
                source="manual",
                event_type="wish",
                payload={"name": name, "pinned": False},
            ))
        return events

    def _identity_events(self, character: str, body: dict[str, Any], projected: dict[str, Any], migration: bool) -> list[dict[str, Any]]:
        if "identity" not in body:
            return []
        incoming = body.get("identity")
        current = projected.get("identity")
        if not incoming and not current:
            return []
        if not incoming:
            if current and not current.get("cleared"):
                return [make_event(
                    event_id=new_id(),
                    ts=self.clock(),
                    device_id=self.device_id,
                    source="manual",
                    event_type="parser_identity",
                    payload={"classes": None, "level": None, "cleared": True},
                )]
            return []
        if not isinstance(incoming, dict):
            return []
        classes = incoming.get("classes")
        level = incoming.get("level")
        cleared = bool(incoming.get("cleared"))
        if current and current.get("classes") == classes and current.get("level") == level and bool(current.get("cleared")) == cleared:
            return []
        event_id = f"migrate:identity:{character.casefold()}" if migration else new_id()
        return [make_event(
            event_id=event_id,
            ts=str(incoming.get("ts") or self.clock()),
            device_id=self.device_id,
            source="manual",
            event_type="parser_identity",
            payload={"classes": classes, "level": level, "cleared": cleared},
        )]

    def _setting_events(self, character: str, body: dict[str, Any], projected: dict[str, Any], migration: bool) -> list[dict[str, Any]]:
        if "settings" not in body or not isinstance(body.get("settings"), dict):
            return []
        incoming = body["settings"]
        current = projected.get("settings") or {}
        events: list[dict[str, Any]] = []
        group_ts = str(incoming.get("ts") or "") if migration else ""
        for group in ("upgrade_progress", "upgrade_tier", "pos_manual"):
            if group not in incoming and not migration:
                continue
            values = incoming.get(group) or {}
            if isinstance(values, dict) and "values" in values and "ts" in values:
                group_ts = str(values.get("ts") or group_ts)
                values = values.get("values") or {}
            if not isinstance(values, dict):
                continue
            have = current.get(group) or {}
            for item, value in values.items():
                if have.get(item) == value:
                    continue
                item_ts = group_ts or self.clock()
                event_id = (
                    f"migrate:setting:{character.casefold()}:{group}:{str(item).casefold()}"
                    if migration else new_id()
                )
                events.append(make_event(
                    event_id=event_id,
                    ts=item_ts,
                    device_id=self.device_id,
                    source="manual",
                    event_type="character_setting",
                    payload={"group": group, "item": str(item), "value": value},
                ))
        if "pos_ignored" in incoming or migration and "pos_ignored" in incoming:
            raw_ignored = incoming.get("pos_ignored") or []
            if isinstance(raw_ignored, dict) and "values" in raw_ignored:
                group_ts = str(raw_ignored.get("ts") or group_ts)
                raw_ignored = raw_ignored.get("values") or []
            wanted = [str(name) for name in raw_ignored] if isinstance(raw_ignored, list) else []
            have = set(current.get("pos_ignored") or [])
            for name in wanted:
                if name in have:
                    continue
                event_id = (
                    f"migrate:setting:{character.casefold()}:pos_ignored:{name.casefold()}"
                    if migration else new_id()
                )
                events.append(make_event(
                    event_id=event_id,
                    ts=group_ts or self.clock(),
                    device_id=self.device_id,
                    source="manual",
                    event_type="character_setting",
                    payload={"group": "pos_ignored", "item": name, "value": True},
                ))
            if not migration:
                for name in have:
                    if name in wanted:
                        continue
                    events.append(make_event(
                        event_id=new_id(),
                        ts=self.clock(),
                        device_id=self.device_id,
                        source="manual",
                        event_type="character_setting",
                        payload={"group": "pos_ignored", "item": name, "value": False},
                    ))
        if "achievements" in incoming:
            text = incoming.get("achievements")
            if isinstance(text, dict):
                group_ts = str(text.get("ts") or group_ts)
                text = text.get("value") if "value" in text else text.get("values")
            text = "" if text is None else str(text)
            if text != str(current.get("achievements") or ""):
                event_id = f"migrate:setting:{character.casefold()}:achievements:" if migration else new_id()
                events.append(make_event(
                    event_id=event_id,
                    ts=group_ts or self.clock(),
                    device_id=self.device_id,
                    source="import",
                    event_type="character_setting",
                    payload={"group": "achievements", "item": "", "value": text},
                ))
        return events

    def _inventory_events(self, character: str, body: dict[str, Any], known_ids: set[str]) -> list[dict[str, Any]]:
        if "inventory_events" not in body:
            return []
        events: list[dict[str, Any]] = []
        for event in body.get("inventory_events") or []:
            if not isinstance(event, dict) or not event.get("id"):
                continue
            if str(event["id"]) in known_ids:
                continue
            source = str(event.get("source") or "import")
            if source not in {"log", "manual", "import"}:
                source = "import"
            payload = dict(event.get("payload") or {})
            events.append(make_event(
                event_id=str(event["id"]),
                ts=str(event.get("ts") or self.clock()),
                device_id=str(event.get("device_id") or self.device_id),
                source=source,
                event_type="inventory_section",
                payload=payload,
            ))
        return events

    def sync(self) -> dict[str, Any]:
        """Read everyone's files, union by id, and write only this device's jsonl."""
        if self._bound is None and not str(self.state.get("provider") or ""):
            self.state["status"] = "idle"
            self.state["error"] = ""
            self.state["message"] = ""
            self.state["auth_expired"] = False
            self._save_state()
            return self.status()
        try:
            provider = self._provider()
        except SyncError as exc:
            return self._fail(exc)
        try:
            pulled = provider.pull()
        except SyncOffline as exc:
            return self._offline(exc)
        except WaitingForCloud:
            return self._waiting()
        except SyncError as exc:
            return self._fail(exc)

        remote = pulled.get("events") or {}
        self._remote = {key: union_events([rows]) for key, rows in remote.items()}
        waiting = bool(pulled.get("waiting"))
        queue = self._read_queue()
        characters = set(self._remote) | set(queue)
        written_ids: dict[str, set[str]] = {}
        try:
            for character in sorted(characters):
                combined = union_events([self._remote.get(character) or [], queue.get(character) or []])
                mine = [event for event in combined if str(event.get("device_id") or "") == self.device_id]
                mine = sorted(mine, key=sort_key)
                if not mine:
                    continue
                provider.write_own(character, self.device_id, mine)
                written_ids[character] = {str(event.get("id")) for event in mine}
                remote_left = [event for event in combined if str(event.get("device_id") or "") != self.device_id]
                self._remote[character] = union_events([remote_left, mine])
            provider.write_device_manifest(
                self.device_id,
                str(self.state.get("device_name") or "This PC"),
                self.clock(),
            )
        except SyncOffline as exc:
            return self._offline(exc)
        except WaitingForCloud:
            return self._waiting()
        except SyncError as exc:
            return self._fail(exc)

        if written_ids:
            remaining: dict[str, list[dict[str, Any]]] = {}
            for character, events in queue.items():
                done = written_ids.get(character) or set()
                left = [event for event in events if str(event.get("id")) not in done]
                if left:
                    remaining[character] = left
            self._write_queue(remaining)

        now = self.clock()
        self.state["last_synced"] = now
        self.state["error"] = ""
        self.state["auth_expired"] = False
        if waiting:
            self.state["status"] = "waiting"
            self.state["message"] = ICLOUD_WAITING
        else:
            self.state["status"] = "ok"
            self.state["message"] = ""
        self._save_state()
        return self.status()

    def _fail(self, exc: SyncError) -> dict[str, Any]:
        self.state["status"] = "error"
        self.state["error"] = str(exc)
        self.state["message"] = ""
        self.state["auth_expired"] = isinstance(exc, SyncAuthExpired)
        self._save_state()
        return self.status()

    def _offline(self, exc: SyncOffline) -> dict[str, Any]:
        self.state["status"] = "offline"
        self.state["error"] = str(exc)
        self.state["message"] = ""
        self.state["auth_expired"] = False
        self._save_state()
        return self.status()

    def _waiting(self) -> dict[str, Any]:
        self.state["status"] = "waiting"
        self.state["error"] = ""
        self.state["message"] = ICLOUD_WAITING
        self.state["auth_expired"] = False
        self._save_state()
        return self.status()

    def apply_currency(self, book: Any) -> None:
        """Copy replayed ledger rows into the local book. Existing ids are left as they are."""
        projected = self.projection()
        for character, body in (projected.get("characters") or {}).items():
            for entry in body.get("currency_history") or []:
                if not isinstance(entry, dict) or not entry.get("id"):
                    continue
                book.import_external_entry(character, entry)

    def apply_identity(self, setter: Callable[[str, dict[str, Any]], None]) -> None:
        projected = self.projection()
        for character, body in (projected.get("characters") or {}).items():
            identity = body.get("identity")
            if identity:
                setter(character, identity)


def queue_text_for_tests(events: list[dict[str, Any]]) -> str:
    """Helper used by tests that want to inspect jsonl text."""
    return encode_jsonl(events)


def parse_jsonl_text(text: str) -> list[dict[str, Any]]:
    return decode_jsonl(text)
