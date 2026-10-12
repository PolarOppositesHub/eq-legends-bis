"""Sync phase 1: two devices, de-dupe, newest set, conflicted copy, offline queue, migration.

Graph HTTP is a fake transport. No Microsoft call is made.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.currencies import CurrencyBook  # noqa: E402
from app.sync.engine import SyncEngine  # noqa: E402
from app.sync.layout import (  # noqa: E402
    ICLOUD_WAITING,
    SYNC_DIR_NAME,
    WaitingForCloud,
    atomic_write,
    is_cloud_placeholder,
)
from app.sync.model import decode_jsonl, encode_jsonl, log_event_id, make_event  # noqa: E402
from app.sync.providers import (  # noqa: E402
    GRAPH_ROOT,
    FolderProvider,
    GraphResponse,
    OneDriveProvider,
    provider_for,
)
from app.sync.layout import SyncError  # noqa: E402


GEZA = "Wind Rune Geza"
LINE = "You looted a Wind Rune Geza from a greater sphinx's corpse and stored it in your currency"
LINE_TS = "2026-08-04T22:00:01"


def _engine(root: Path, device_id: str) -> SyncEngine:
    return SyncEngine(root, device_id=device_id, clock=lambda: "2026-10-11T12:00:00")


def _currency(entry_id: str, ts: str, count: int) -> dict:
    return {
        "id": entry_id,
        "ts": ts,
        "currency": GEZA,
        "delta": count,
        "source": "manual",
        "evidence": f"Set currency storage to {count}",
        "anchor": True,
        "count": count,
        "autosold": False,
        "reverted": False,
    }


class SyncTests(unittest.TestCase):
    def test_two_devices_offline_edits_merge_without_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "shared"
            user_a = root / "a"
            user_b = root / "b"
            left = _engine(user_a, "a" * 32)
            right = _engine(user_b, "b" * 32)
            provider_a = FolderProvider(folder, online=False)
            provider_b = FolderProvider(folder, online=False)
            left.bind_provider(provider_a)
            right.bind_provider(provider_b)
            left.migrate({
                "characters": {
                    "Zasariz": {
                        "currency_entries": [_currency("set-a", "2026-08-01T10:00:00", 3)],
                        "wishes": [{"name": "Mask of Song", "ts": "2026-08-02T11:00:00"}],
                    }
                }
            })
            right.migrate({
                "characters": {
                    "Zasariz": {
                        "wishes": [{"name": "Cloak of Flames", "ts": "2026-08-03T12:00:00"}],
                    },
                    "Other": {
                        "wishes": [{"name": "Slime Blood of Cazic-Thule", "ts": "2026-08-03T12:00:00"}],
                    },
                }
            })
            offline = left.sync()
            self.assertEqual(offline["status"], "offline")
            self.assertFalse((folder / SYNC_DIR_NAME).exists())
            provider_a.online = True
            provider_b.online = True
            left.sync()
            right.sync()
            left.sync()
            right.sync()
            seen = left.projection()["characters"]["Zasariz"]
            other = right.projection()["characters"]["Zasariz"]
            self.assertEqual(seen["currency_counts"][GEZA], 3)
            self.assertEqual(other["currency_counts"][GEZA], 3)
            self.assertEqual(seen["wishes"], ["Mask of Song", "Cloak of Flames"])
            self.assertEqual(other["wishes"], ["Mask of Song", "Cloak of Flames"])
            self.assertNotIn("Slime Blood of Cazic-Thule", seen["wishes"])
            self.assertEqual(
                left.projection()["characters"]["Other"]["wishes"],
                ["Slime Blood of Cazic-Thule"],
            )
            self.assertNotIn(GEZA, left.projection()["characters"]["Other"]["currency_counts"])
            own = decode_jsonl((folder / SYNC_DIR_NAME / "events" / "Zasariz" / f"{'a' * 32}.jsonl").read_text(encoding="utf-8"))
            self.assertTrue(all(event["device_id"] == "a" * 32 for event in own))
            self.assertFalse(any(event["id"].startswith("migrate:wish:other") for event in own))

    def test_duplicate_log_lines_from_the_same_device_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = _engine(Path(tmp) / "a", "a" * 32)
            first = device.append_log_line("Zasariz", LINE, LINE_TS)
            second = device.append_log_line("Zasariz", LINE, LINE_TS)
            self.assertEqual(first["id"], second["id"])
            self.assertTrue(first["added"])
            self.assertFalse(second["added"])
            self.assertEqual(first["id"], log_event_id("Zasariz", LINE, LINE_TS, "a" * 32))
            rows = device.events_by_character()["Zasariz"]
            self.assertEqual(len(rows), 1)
            other = _engine(Path(tmp) / "b", "b" * 32)
            copied = other.append_log_line("Zasariz", LINE, LINE_TS)
            self.assertNotEqual(copied["id"], first["id"])
            self.assertTrue(copied["added"])

    def test_newest_set_wins_and_the_other_stays_in_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "shared"
            left = _engine(root / "a", "a" * 32)
            right = _engine(root / "b", "b" * 32)
            left.bind_provider(FolderProvider(folder))
            right.bind_provider(FolderProvider(folder))
            left.migrate({
                "characters": {
                    "Zasariz": {"currency_entries": [_currency("set-old", "2026-08-01T10:00:00", 3)]}
                }
            })
            right.migrate({
                "characters": {
                    "Zasariz": {"currency_entries": [_currency("set-new", "2026-08-09T10:00:00", 9)]}
                }
            })
            left.sync()
            right.sync()
            left.sync()
            body = left.projection()["characters"]["Zasariz"]
            self.assertEqual(body["currency_counts"][GEZA], 9)
            history_ids = [entry["id"] for entry in body["currency_history"]]
            self.assertEqual(history_ids, ["set-old", "set-new"])
            book = CurrencyBook(root / "currencies.json")
            left.apply_currency(book)
            _key, state = book._resolve("Zasariz", create=False)
            self.assertEqual(book.storage_count(state, GEZA), 9)
            self.assertEqual({entry["id"] for entry in state["entries"]}, {"set-old", "set-new"})

    def test_conflicted_copy_merges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "shared"
            device = _engine(root / "a", "a" * 32)
            provider = FolderProvider(folder)
            device.bind_provider(provider)
            device.migrate({
                "characters": {
                    "Zasariz": {"wishes": [{"name": "Mask of Song", "ts": "2026-08-02T11:00:00"}]}
                }
            })
            device.sync()
            extra = make_event(
                event_id="from-conflict",
                ts="2026-08-04T12:00:00",
                device_id="a" * 32,
                source="manual",
                event_type="wish",
                payload={"name": "Cloak of Flames", "pinned": True},
            )
            path = folder / SYNC_DIR_NAME / "events" / "Zasariz" / f"{'a' * 32} (conflicted copy).jsonl"
            path.write_text(encode_jsonl([extra]), encoding="utf-8")
            device.sync()
            wishes = device.projection()["characters"]["Zasariz"]["wishes"]
            self.assertEqual(wishes, ["Mask of Song", "Cloak of Flames"])
            own = decode_jsonl((folder / SYNC_DIR_NAME / "events" / "Zasariz" / f"{'a' * 32}.jsonl").read_text(encoding="utf-8"))
            self.assertIn("from-conflict", {event["id"] for event in own})
            self.assertTrue(path.is_file())

    def test_offline_queue_catches_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "shared"
            device = _engine(root / "a", "a" * 32)
            provider = FolderProvider(folder, online=False)
            device.bind_provider(provider)
            added = device.append_log_line("Zasariz", LINE, LINE_TS)
            self.assertEqual(device.sync()["status"], "offline")
            queued = (root / "a" / "sync" / "queue.jsonl").read_text(encoding="utf-8")
            self.assertIn(added["id"], queued)
            self.assertFalse((folder / SYNC_DIR_NAME).exists())
            provider.online = True
            caught = device.sync()
            self.assertEqual(caught["status"], "ok")
            self.assertEqual(caught["pending"], 0)
            stored = decode_jsonl(
                (folder / SYNC_DIR_NAME / "events" / "Zasariz" / f"{'a' * 32}.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual([event["id"] for event in stored], [added["id"]])
            self.assertEqual((root / "a" / "sync" / "queue.jsonl").read_text(encoding="utf-8"), "")

    def test_migration_keeps_original_timestamps_and_runs_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = _engine(Path(tmp), "a" * 32)
            section = {
                "id": "inventory_section:worn:2026-08-05T14:00:00:0",
                "ts": "2026-08-05T14:00:00",
                "source": "import",
                "type": "inventory_section",
                "payload": {"section": "worn", "rows": [{"name": "Cloak of Flames"}]},
            }
            snapshot = {
                "characters": {
                    "Zasariz": {
                        "currency_entries": [_currency("set-a", "2026-08-01T10:00:00", 4)],
                        "wishes": [{"name": "Mask of Song", "ts": "2026-08-02T11:00:00"}],
                        "identity": {"classes": "WIZ/ENC/MAG", "level": 50, "ts": "2026-08-03T12:00:00"},
                        "settings": {
                            "upgrade_progress": {"ts": "2026-08-04T13:00:00", "values": {"Cloak of Flames": 8}},
                            "pos_ignored": ["Paladin Test of Spirit"],
                        },
                        "inventory_events": [section],
                    }
                }
            }
            first = device.migrate(snapshot)
            self.assertFalse(first["already"])
            self.assertGreater(first["added"], 0)
            events = {event["id"]: event for event in device.events_by_character()["Zasariz"]}
            self.assertEqual(events["set-a"]["ts"], "2026-08-01T10:00:00")
            self.assertEqual(events["migrate:wish:zasariz:mask of song"]["ts"], "2026-08-02T11:00:00")
            self.assertEqual(events["migrate:identity:zasariz"]["ts"], "2026-08-03T12:00:00")
            self.assertEqual(events["migrate:setting:zasariz:upgrade_progress:cloak of flames"]["ts"], "2026-08-04T13:00:00")
            self.assertEqual(events[section["id"]]["ts"], "2026-08-05T14:00:00")
            body = device.projection()["characters"]["Zasariz"]
            self.assertEqual(body["currency_counts"][GEZA], 4)
            self.assertEqual(body["wishes"], ["Mask of Song"])
            self.assertEqual(body["identity"]["classes"], "WIZ/ENC/MAG")
            self.assertEqual(body["identity"]["level"], 50)
            self.assertEqual(body["settings"]["upgrade_progress"]["Cloak of Flames"], 8)
            self.assertEqual(body["settings"]["pos_ignored"], ["Paladin Test of Spirit"])
            self.assertEqual(body["sections"]["worn"]["rows"][0]["name"], "Cloak of Flames")
            second = device.migrate(snapshot)
            self.assertTrue(second["already"])
            self.assertEqual(len(device.events_by_character()["Zasariz"]), len(events))

    def test_newer_inventory_section_wins_and_the_older_event_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = _engine(Path(tmp), "a" * 32)
            older = {
                "id": "section-old",
                "ts": "2026-08-01T00:00:00",
                "device_id": "a" * 32,
                "source": "import",
                "type": "inventory_section",
                "payload": {"section": "worn", "rows": [{"name": "Old Cloak"}]},
            }
            newer = {
                "id": "section-new",
                "ts": "2026-08-02T00:00:00",
                "device_id": "b" * 32,
                "source": "import",
                "type": "inventory_section",
                "payload": {"section": "worn", "rows": [{"name": "New Cloak"}]},
            }
            device.migrate({"characters": {"Zasariz": {"inventory_events": [older, newer]}}})
            body = device.projection()["characters"]["Zasariz"]
            self.assertEqual(body["sections"]["worn"]["rows"][0]["name"], "New Cloak")
            self.assertEqual([event["id"] for event in body["section_events"]], ["section-old", "section-new"])

    def test_placeholder_read_is_waiting_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "shared"
            device = _engine(root / "a", "a" * 32)
            provider = FolderProvider(folder)
            device.bind_provider(provider)
            device.append_log_line("Zasariz", LINE, LINE_TS)
            device.sync()
            ghost = folder / SYNC_DIR_NAME / "events" / "Zasariz" / "ghost.jsonl"
            ghost.write_text("{}\n", encoding="utf-8")
            real_read = __import__("app.sync.providers", fromlist=["read_events_file"]).read_events_file

            def read_events_file(path):
                if path.name == "ghost.jsonl":
                    raise WaitingForCloud()
                return real_read(path)

            import app.sync.providers as providers
            providers.read_events_file = read_events_file
            try:
                pulled = provider.pull()
            finally:
                providers.read_events_file = real_read
            self.assertTrue(pulled["waiting"])
            self.assertEqual(pulled["message"], ICLOUD_WAITING)
            provider.pull = lambda: pulled
            status = device.sync()
            self.assertEqual(status["status"], "waiting")
            self.assertEqual(status["message"], ICLOUD_WAITING)
            self.assertEqual(status["error"], "")
            error = OSError("The cloud file provider is not running")
            error.winerror = 362
            self.assertTrue(is_cloud_placeholder(error))
            self.assertTrue(is_cloud_placeholder(OSError("icloud placeholder not downloaded")))

    def test_writes_use_a_temp_file_then_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            atomic_write(path, "ok\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "ok\n")
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_onedrive_graph_is_mocked_and_conflicted_children_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = _engine(Path(tmp), "a" * 32)
            remote = make_event(
                event_id="from-other-pc",
                ts="2026-08-01T00:00:00",
                device_id="b" * 32,
                source="manual",
                event_type="wish",
                payload={"name": "Mask of Song", "pinned": True},
            )
            conflict = make_event(
                event_id="from-graph-conflict",
                ts="2026-08-02T00:00:00",
                device_id="b" * 32,
                source="manual",
                event_type="wish",
                payload={"name": "Cloak of Flames", "pinned": True},
            )
            graph = MockGraph()
            base = f"{SYNC_DIR_NAME}/events/Zasariz"
            graph.add(f"{base}/{'b' * 32}.jsonl", encode_jsonl([remote]).encode("utf-8"))
            graph.add(f"{base}/{'b' * 32} (conflicted copy).jsonl", encode_jsonl([conflict]).encode("utf-8"))
            device.set_onedrive_session("test-token", "Josh", transport=graph)
            device.append_log_line("Zasariz", LINE, LINE_TS)
            status = device.sync()
            self.assertEqual(status["status"], "ok")
            puts = [url for method, url, _headers, _body in graph.calls if method == "PUT"]
            self.assertTrue(any(GRAPH_ROOT in url and f"{'a' * 32}.jsonl" in unquote(url) for url in puts))
            self.assertTrue(all("conflict" not in unquote(url).lower() for url in puts))
            self.assertTrue(all(("b" * 32) + ".jsonl" not in unquote(url) for url in puts))
            wishes = device.projection()["characters"]["Zasariz"]["wishes"]
            self.assertEqual(wishes, ["Mask of Song", "Cloak of Flames"])
            authed = [headers for _method, _url, headers, _body in graph.calls]
            self.assertTrue(all(row.get("Authorization") == "Bearer test-token" for row in authed))
            device.sync()
            approot = [
                url for method, url, _headers, _body in graph.calls
                if method == "GET" and url.split("?", 1)[0].rstrip("/").endswith("/me/drive/special/approot")
            ]
            self.assertEqual(approot, [f"{GRAPH_ROOT}"])

    def test_google_provider_builds(self):
        provider = provider_for("google", transport=object(), token="test-token")
        self.assertEqual(provider.kind, "google")


class MockGraph:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.calls: list[tuple] = []

    def add(self, path: str, content: bytes) -> None:
        self.files[path] = content

    def request(self, method: str, url: str, headers: dict, body: bytes | None = None) -> GraphResponse:
        self.calls.append((method, url, headers, body))
        if headers.get("Authorization") != "Bearer test-token":
            return GraphResponse(
                401,
                b'{"error":{"code":"InvalidAuthenticationToken","message":"bad token"}}',
                {"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The access token is invalid"'},
            )
        bare = url.split("?", 1)[0].rstrip("/")
        if method == "GET" and bare.endswith("/me/drive/special/approot"):
            return GraphResponse(200, b'{"id":"approot","name":"app","folder":{}}')
        kind, path = _split_graph(url)
        if method == "GET" and kind == "children":
            names = _children(self.files, path)
            value = []
            for name in names:
                full = f"{path}/{name}"
                item = {"name": name}
                if any(key.startswith(full + "/") for key in self.files):
                    item["folder"] = {}
                else:
                    item["file"] = {}
                value.append(item)
            return GraphResponse(200, json.dumps({"value": value}).encode("utf-8"))
        if method == "GET" and kind == "content":
            if path not in self.files:
                return GraphResponse(404, b"")
            return GraphResponse(200, self.files[path])
        if method == "PUT" and kind == "content":
            self.files[path] = body or b""
            return GraphResponse(201, b"{}")
        return GraphResponse(404, b"")


def _split_graph(url: str) -> tuple[str, str]:
    marker = "/me/drive/special/approot:"
    rest = url.split(marker, 1)[1]
    if rest.endswith(":/children"):
        return "children", unquote(rest[1:-len(":/children")])
    if rest.endswith(":/content"):
        return "content", unquote(rest[1:-len(":/content")])
    raise AssertionError(url)


def _children(files: dict[str, bytes], path: str) -> list[str]:
    prefix = path.rstrip("/") + "/"
    names = set()
    for key in files:
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        if rest:
            names.add(rest.split("/")[0])
    return sorted(names)


class OneDriveDirectTests(unittest.TestCase):
    def test_provider_lists_approot_children(self):
        graph = MockGraph()
        graph.add(f"{SYNC_DIR_NAME}/events/Zasariz/peer.jsonl", b"")
        provider = OneDriveProvider(graph, "test-token")
        pulled = provider.pull()
        self.assertIn("Zasariz", pulled["events"])
        self.assertTrue(graph.calls[0][1].split("?", 1)[0].rstrip("/").endswith("/me/drive/special/approot"))
        self.assertTrue(any("/me/drive/special/approot:" in url for _m, url, _h, _b in graph.calls))
        provider.pull()
        approot = [
            url for method, url, _h, _b in graph.calls
            if method == "GET" and url.split("?", 1)[0].rstrip("/").endswith("/me/drive/special/approot")
        ]
        self.assertEqual(len(approot), 1)


if __name__ == "__main__":
    unittest.main()
