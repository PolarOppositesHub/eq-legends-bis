"""Production OneDrive transport.

The 1.1.10 API saved a token and left the Graph transport unset, so every sync
said OneDrive was not connected. These tests call that API with no injected
transport and drive the real urllib client at a local fake Graph server.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.sync.engine import SyncEngine  # noqa: E402
from app.sync.layout import SYNC_DIR_NAME  # noqa: E402
from app.sync.model import encode_jsonl, log_event_id, make_event  # noqa: E402
from app.sync.providers import (  # noqa: E402
    CONNECTED_APP_FOLDER,
    GRAPH_API,
    ONEDRIVE_SCOPES,
    ONEDRIVE_SIGN_IN,
    ONEDRIVE_UPDATE_SIGN_IN,
    GraphResponse,
    UrllibGraphTransport,
    describe_graph_error,
    log_graph_error,
    set_graph_base_url_for_tests,
)
import app.sync_api as sync_api  # noqa: E402


LINE = "You looted a Wind Rune Geza from a greater sphinx's corpse and stored it in your currency"
LINE_TS = "2026-08-04T22:00:01"
TOKEN = "test-token"
MARKER = "/me/drive/special/approot:"


class _Store:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.calls: list[tuple[str, str, str | None, bytes]] = []
        self.token = TOKEN
        self.force_unauthorized = False
        self.unauthorized_body = b'{"error":"invalid_token"}'
        self.unauthorized_header = ""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET", b"")

    def do_PUT(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._dispatch("PUT", body)

    def log_message(self, fmt: str, *args) -> None:
        return

    def _dispatch(self, method: str, body: bytes) -> None:
        store: _Store = self.server.store  # type: ignore[attr-defined]
        auth = self.headers.get("Authorization")
        path = unquote(self.path.split("?", 1)[0])
        store.calls.append((method, path, auth, body))
        if store.force_unauthorized or auth != f"Bearer {store.token}":
            extra = {"WWW-Authenticate": store.unauthorized_header} if store.unauthorized_header else None
            self._send(401, store.unauthorized_body or b'{"error":"invalid_token"}', extra)
            return
        bare = path.rstrip("/")
        if method == "GET" and bare.endswith("/me/drive/special/approot"):
            self._send(200, b'{"name":"EQ Legends BiS","folder":{}}')
            return
        kind, relative = _split(path)
        if kind == "children" and method == "GET":
            items = _children(store.files, relative)
            if not items:
                self._send(404, b"")
                return
            self._send(200, json.dumps({"value": items}).encode("utf-8"))
            return
        if kind == "content" and method == "GET":
            if relative not in store.files:
                self._send(404, b"")
                return
            self._send(200, store.files[relative])
            return
        if kind == "content" and method == "PUT":
            store.files[relative] = body
            self._send(201, b"{}")
            return
        self._send(404, b"")

    def _send(self, status: int, payload: bytes, extra: dict[str, str] | None = None) -> None:
        payload = payload or b""
        self.send_response(status)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Server(ThreadingHTTPServer):
    def __init__(self, store: _Store) -> None:
        self.store = store
        super().__init__(("127.0.0.1", 0), _Handler)


def _split(path: str) -> tuple[str, str]:
    rest = path.split(MARKER, 1)[1]
    if rest.endswith(":/children"):
        return "children", unquote(rest[1:-len(":/children")])
    if rest.endswith(":/content"):
        return "content", unquote(rest[1:-len(":/content")])
    raise AssertionError(path)


def _children(files: dict[str, bytes], folder: str) -> list[dict[str, object]]:
    prefix = folder.rstrip("/") + "/"
    names: dict[str, bool] = {}
    for key in files:
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        if not rest:
            continue
        name = rest.split("/", 1)[0]
        names[name] = "/" in rest or any(other.startswith(prefix + name + "/") for other in files)
    items = []
    for name, is_folder in sorted(names.items()):
        item: dict[str, object] = {"name": name}
        if is_folder:
            item["folder"] = {}
        else:
            item["file"] = {}
        items.append(item)
    return items


class OneDriveTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous = sync_api._engine
        self._tmpdir = tempfile.TemporaryDirectory()
        self.engine = SyncEngine(Path(self._tmpdir.name), device_id="a" * 32, clock=lambda: "2026-10-11T12:00:00")
        sync_api._engine = self.engine
        self.client = TestClient(app)

    def tearDown(self) -> None:
        sync_api._engine = self._previous
        set_graph_base_url_for_tests(None)
        self._tmpdir.cleanup()

    def test_api_session_without_a_transport_builds_the_real_one(self) -> None:
        response = self.client.post("/api/sync/onedrive", json={"access_token": TOKEN, "account": "Josh"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsInstance(self.engine._transport, UrllibGraphTransport)
        self.assertEqual(self.engine._transport.base_url, GRAPH_API)
        self.engine._transport = None
        provider = self.engine._provider()
        self.assertIsInstance(provider.transport, UrllibGraphTransport)
        self.assertIs(self.engine._transport, provider.transport)

    def test_real_transport_uploads_and_downloads_against_a_local_graph(self) -> None:
        store = _Store()
        remote = make_event(
            event_id="from-other-pc",
            ts="2026-08-01T00:00:00",
            device_id="b" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Mask of Song", "pinned": True},
        )
        remote_path = f"{SYNC_DIR_NAME}/events/Zasariz/{'b' * 32}.jsonl"
        store.files[remote_path] = encode_jsonl([remote]).encode("utf-8")
        server = _Server(store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            set_graph_base_url_for_tests(f"http://127.0.0.1:{port}")
            self.engine.append_log_line("Zasariz", LINE, LINE_TS)
            signed = self.client.post("/api/sync/onedrive", json={"access_token": TOKEN, "account": "Josh"})
            self.assertEqual(signed.status_code, 200, signed.text)
            self.assertIsInstance(self.engine._transport, UrllibGraphTransport)
            self.assertNotEqual(self.engine._transport.base_url, GRAPH_API)
            synced = self.client.post("/api/sync/now")
            self.assertEqual(synced.status_code, 200, synced.text)
            body = synced.json()
            self.assertEqual(body["status"], "ok", body)
            self.assertFalse(body["auth_expired"])
            wishes = body["projection"]["characters"]["Zasariz"]["wishes"]
            self.assertEqual(wishes, ["Mask of Song"])
            own = f"{SYNC_DIR_NAME}/events/Zasariz/{'a' * 32}.jsonl"
            self.assertIn(log_event_id("Zasariz", LINE, LINE_TS, "a" * 32), store.files[own].decode("utf-8"))
            downloads = [path for method, path, _auth, _body in store.calls if method == "GET" and path.endswith(":/content")]
            uploads = [path for method, path, _auth, _body in store.calls if method == "PUT" and path.endswith(":/content")]
            self.assertTrue(any(("b" * 32) + ".jsonl" in path for path in downloads))
            self.assertTrue(any(("a" * 32) + ".jsonl" in path for path in uploads))
            self.assertTrue(all(auth == f"Bearer {TOKEN}" for _m, _p, auth, _b in store.calls))

            def approot_calls() -> list[str]:
                return [
                    path for method, path, _auth, _body in store.calls
                    if method == "GET" and path.rstrip("/").endswith("/me/drive/special/approot")
                ]

            self.assertEqual(len(approot_calls()), 1)
            checked = self.client.post("/api/sync/onedrive/test")
            self.assertEqual(checked.status_code, 200, checked.text)
            self.assertEqual(checked.json()["message"], CONNECTED_APP_FOLDER)
            self.assertEqual(len(approot_calls()), 2)
            again = self.client.post("/api/sync/now")
            self.assertEqual(again.json()["status"], "ok", again.text)
            self.assertEqual(len(approot_calls()), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_graph_401_reports_auth_expired(self) -> None:
        store = _Store()
        store.force_unauthorized = True
        server = _Server(store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            set_graph_base_url_for_tests(f"http://127.0.0.1:{port}")
            self.engine.append_log_line("Zasariz", LINE, LINE_TS)
            signed = self.client.post("/api/sync/onedrive", json={"access_token": TOKEN, "account": "Josh"})
            self.assertEqual(signed.status_code, 200, signed.text)
            synced = self.client.post("/api/sync/now")
            self.assertEqual(synced.status_code, 200, synced.text)
            body = synced.json()
            self.assertEqual(body["status"], "error")
            self.assertTrue(body["auth_expired"])
            self.assertIn("invalid_token", body["error"])
            self.assertIn("401", body["error"])
            own = f"{SYNC_DIR_NAME}/events/Zasariz/{'a' * 32}.jsonl"
            self.assertNotIn(own, store.files)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_graph_401_json_error_reaches_status_and_the_sidecar_log(self) -> None:
        store = _Store()
        store.force_unauthorized = True
        store.unauthorized_body = json.dumps({
            "error": {
                "code": "InvalidAuthenticationToken",
                "message": "IDX14100: JWT is not well formed, there are no dots (.).",
            }
        }).encode("utf-8")
        store.unauthorized_header = 'Bearer error="invalid_token", error_description="The access token is invalid"'
        server = _Server(store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            set_graph_base_url_for_tests(f"http://127.0.0.1:{port}")
            signed = self.client.post("/api/sync/onedrive", json={"access_token": TOKEN, "account": "OneDrive"})
            self.assertEqual(signed.status_code, 200, signed.text)
            with self.assertLogs("eq.sync.graph", level="WARNING") as logs:
                synced = self.client.post("/api/sync/now")
            self.assertEqual(synced.status_code, 200, synced.text)
            body = synced.json()
            self.assertEqual(body["status"], "error")
            self.assertTrue(body["auth_expired"])
            self.assertIn("InvalidAuthenticationToken", body["error"])
            self.assertIn("IDX14100", body["error"])
            self.assertIn("WWW-Authenticate", body["error"])
            self.assertIn("invalid_token", body["error"])
            self.assertIn("The access token is invalid", body["error"])
            logged = "\n".join(logs.output)
            self.assertIn("InvalidAuthenticationToken", logged)
            self.assertIn("IDX14100", logged)
            self.assertIn("WWW-Authenticate", logged)
            self.assertNotIn(TOKEN, logged)
            self.assertNotIn("Bearer " + TOKEN, logged)
            tested = self.client.post("/api/sync/onedrive/test")
            self.assertIn("InvalidAuthenticationToken", tested.json()["message"])
            self.assertFalse(tested.json()["ok"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_no_token_says_sign_in_and_not_expired(self) -> None:
        self.engine.configure(provider="onedrive")
        synced = self.client.post("/api/sync/now")
        body = synced.json()
        self.assertEqual(body["error"], ONEDRIVE_SIGN_IN)
        self.assertNotIn("expired", body["error"].lower())
        self.assertFalse(body["auth_expired"])
        notice = self.client.post("/api/sync/onedrive/notice", json={
            "error": ONEDRIVE_UPDATE_SIGN_IN,
            "auth_expired": False,
            "reauth": True,
        })
        noted = notice.json()
        self.assertEqual(noted["error"], ONEDRIVE_UPDATE_SIGN_IN)
        self.assertFalse(noted["auth_expired"])
        self.assertTrue(noted["reauth"])
        checked = self.client.post("/api/sync/onedrive/test")
        self.assertEqual(checked.json()["message"], ONEDRIVE_SIGN_IN)


class GraphErrorParseTests(unittest.TestCase):
    def test_json_body_and_www_authenticate_are_parsed_and_logged_without_the_token(self) -> None:
        self.assertEqual(
            ONEDRIVE_SCOPES,
            "https://graph.microsoft.com/Files.ReadWrite.AppFolder offline_access",
        )
        body = json.dumps({
            "error": {
                "code": "InvalidAuthenticationToken",
                "message": "CompactToken parsing failed secret-token-value",
            }
        }).encode("utf-8")
        header = 'Bearer realm="", error="invalid_token", error_description="The access token is invalid"'
        response = GraphResponse(401, body, {"WWW-Authenticate": header})
        detail = describe_graph_error(response)
        self.assertIn("401", detail)
        self.assertIn("InvalidAuthenticationToken", detail)
        self.assertIn("CompactToken parsing failed", detail)
        self.assertIn("WWW-Authenticate invalid_token: The access token is invalid", detail)
        with self.assertLogs("eq.sync.graph", level="WARNING") as logs:
            log_graph_error(
                "GET",
                "https://graph.microsoft.com/v1.0/me/drive/special/approot",
                401,
                detail,
                "secret-token-value",
            )
        logged = logs.output[0]
        self.assertIn("InvalidAuthenticationToken", logged)
        self.assertIn("approot", logged)
        self.assertNotIn("secret-token-value", logged)
        self.assertNotIn("Bearer secret-token-value", logged)


if __name__ == "__main__":
    unittest.main()
