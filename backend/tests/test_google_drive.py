"""Google Drive app folder: layout, download hygiene, skipped files, and errors."""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.sync.engine import SyncEngine  # noqa: E402
from app.sync.google_drive import (  # noqa: E402
    CONNECTED_APP_DATA,
    DRIVE_API,
    FOLDER_MIME,
    GOOGLE_DRIVE_CLIENT_ID,
    GOOGLE_DRIVE_SCOPES,
    GOOGLE_SIGN_IN,
    DriveResponse,
    GoogleDriveProvider,
    UrllibDriveTransport,
    describe_drive_error,
    download_candidates,
    media_url,
)
from app.sync.layout import SYNC_DIR_NAME, SyncAuthExpired  # noqa: E402
from app.sync.model import encode_jsonl, make_event  # noqa: E402
from app.sync.providers import provider_for  # noqa: E402


TOKEN = "test-token"


class MockDrive:
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.seq = 1
        self.fail_ids: set[str] = set()
        self.unauthorized = False
        self.reject_web = False
        self.web_unauthorized = False

    def add(self, parent: str, name: str, content: bytes = b"", *, folder: bool = False, web: str = "", file_id: str = "") -> str:
        fid = file_id or f"id{self.seq}"
        self.seq += 1
        self.files[fid] = {
            "id": fid,
            "name": name,
            "mimeType": FOLDER_MIME if folder else "application/octet-stream",
            "parents": [parent],
            "content": content,
            "webContentLink": web,
        }
        return fid

    def request(self, method: str, url: str, headers: dict, body: bytes | None = None) -> DriveResponse:
        self.calls.append((method, url, dict(headers or {}), body))
        api = "googleapis.com" in (urlsplit(url).hostname or "")
        if self.unauthorized or headers.get("Authorization") != f"Bearer {TOKEN}":
            payload = b'{"error":{"code":401,"message":"Invalid Credentials","status":"UNAUTHENTICATED","errors":[{"reason":"authError","message":"Invalid Credentials"}]}}'
            return DriveResponse(401, payload, url=url, api_host=api)
        parsed = urlsplit(url)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        if method == "GET" and path.rstrip("/").endswith("/drive/v3/files") and "alt" not in query:
            return self._list(query.get("q", [""])[0], url)
        if method == "GET" and query.get("alt") == ["media"]:
            return self._media(path.rstrip("/").split("/")[-1], url, api=True)
        if method == "GET" and not api:
            if self.web_unauthorized:
                return DriveResponse(401, b'{"error":{"code":401,"message":"download host rejected the sign-in"}}', url=url, api_host=False)
            if self.reject_web:
                return DriveResponse(500, b'{"error":{"code":500,"message":"download failed"}}', url=url, api_host=False)
            fid = (query.get("id") or [""])[0]
            return self._media(fid, url, api=False)
        if method == "POST" and path.rstrip("/").endswith("/drive/v3/files"):
            meta = json.loads((body or b"{}").decode("utf-8"))
            fid = f"id{self.seq}"
            self.seq += 1
            self.files[fid] = {
                "id": fid,
                "name": meta.get("name") or "",
                "mimeType": meta.get("mimeType") or "application/octet-stream",
                "parents": list(meta.get("parents") or []),
                "content": b"",
                "webContentLink": "",
            }
            return DriveResponse(200, json.dumps({"id": fid, "name": meta.get("name") or ""}).encode(), url=url, api_host=True)
        if method == "PATCH" and "/upload/drive/v3/files/" in path:
            fid = path.split("/files/")[1].split("?")[0]
            if fid not in self.files:
                return DriveResponse(404, b"{}", url=url, api_host=True)
            self.files[fid]["content"] = body or b""
            return DriveResponse(200, b"{}", url=url, api_host=True)
        return DriveResponse(404, b"{}", url=url, api_host=api)

    def _list(self, query: str, url: str) -> DriveResponse:
        parent = ""
        matched_parent = __import__("re").search(r"'([^']+)' in parents", query or "")
        if matched_parent:
            parent = matched_parent.group(1)
        name = ""
        matched_name = __import__("re").search(r"name = '([^']*)'", query or "")
        if matched_name:
            name = matched_name.group(1)
        folders_only = FOLDER_MIME in (query or "")
        files = []
        for item in self.files.values():
            if parent and parent not in item["parents"]:
                continue
            if matched_name and item["name"] != name:
                continue
            if folders_only and item["mimeType"] != FOLDER_MIME:
                continue
            row = {
                "id": item["id"],
                "name": item["name"],
                "mimeType": item["mimeType"],
            }
            if item.get("webContentLink"):
                row["webContentLink"] = item["webContentLink"]
            files.append(row)
        return DriveResponse(200, json.dumps({"files": files}).encode(), url=url, api_host=True)

    def _media(self, fid: str, url: str, *, api: bool) -> DriveResponse:
        item = self.files.get(fid)
        if not item:
            return DriveResponse(404, b"", url=url, api_host=api)
        if fid in self.fail_ids:
            return DriveResponse(500, b'{"error":{"code":500,"message":"backendError","status":"INTERNAL"}}', url=url, api_host=api)
        return DriveResponse(200, item.get("content") or b"", url=url, api_host=api)


def _tree(drive: MockDrive) -> str:
    root = drive.add("appDataFolder", SYNC_DIR_NAME, folder=True)
    events = drive.add(root, "events", folder=True)
    return drive.add(events, "Zasariz", folder=True)


class GoogleDriveProviderTests(unittest.TestCase):
    def test_client_id_is_the_desktop_oauth_client(self):
        self.assertEqual(GOOGLE_DRIVE_CLIENT_ID, "122260219418-2rhjatugpadqi99ofecm8quruernbb0d.apps.googleusercontent.com")
        self.assertIn(".apps.googleusercontent.com", GOOGLE_DRIVE_CLIENT_ID)
        self.assertEqual(GOOGLE_DRIVE_SCOPES, "https://www.googleapis.com/auth/drive.appdata")
        built = provider_for("google", transport=object(), token=TOKEN)
        self.assertIsInstance(built, GoogleDriveProvider)

    def test_empty_app_folder_does_not_create_files(self):
        drive = MockDrive()
        provider = GoogleDriveProvider(drive, TOKEN)
        pulled = provider.pull()
        self.assertEqual(pulled["events"], {})
        self.assertEqual(pulled["skipped"], 0)
        self.assertFalse(any(method == "POST" for method, _url, _headers, _body in drive.calls))
        checked = provider.test_connection()
        self.assertEqual(checked, {"ok": True, "message": CONNECTED_APP_DATA})

    def test_pull_merges_conflicted_copies_and_prefers_the_download_url(self):
        drive = MockDrive()
        folder = _tree(drive)
        remote = make_event(
            event_id="from-other-pc",
            ts="2026-08-01T00:00:00",
            device_id="b" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Mask of Song", "pinned": True},
        )
        conflict = make_event(
            event_id="from-drive-conflict",
            ts="2026-08-02T00:00:00",
            device_id="b" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Cloak of Flames", "pinned": True},
        )
        peer_id = drive.add(folder, f"{'b' * 32}.jsonl", encode_jsonl([remote]).encode(), web="https://drive.google.com/uc?id=PEER&export=download")
        drive.files[peer_id]["webContentLink"] = f"https://drive.google.com/uc?id={peer_id}&export=download"
        drive.add(folder, f"{'b' * 32} (conflicted copy).jsonl", encode_jsonl([conflict]).encode())
        provider = GoogleDriveProvider(drive, TOKEN)
        pulled = provider.pull()
        wishes = [row["payload"]["name"] for row in pulled["events"]["Zasariz"] if row["type"] == "wish"]
        self.assertEqual(wishes, ["Mask of Song", "Cloak of Flames"])
        downloads = [url for method, url, _headers, _body in drive.calls if method == "GET" and "export=download" in url]
        self.assertTrue(downloads)
        self.assertTrue(downloads[0].startswith("https://drive.google.com/"))
        media = [url for method, url, _headers, _body in drive.calls if method == "GET" and "alt=media" in url and peer_id in url]
        self.assertEqual(media, [])

    def test_bad_download_url_falls_back_to_alt_media_and_one_bad_file_is_skipped(self):
        drive = MockDrive()
        drive.reject_web = True
        folder = _tree(drive)
        good = make_event(
            event_id="good",
            ts="2026-08-01T00:00:00",
            device_id="b" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Mask of Song", "pinned": True},
        )
        bad = make_event(
            event_id="bad",
            ts="2026-08-03T00:00:00",
            device_id="c" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Missing", "pinned": True},
        )
        good_id = drive.add(folder, "good.jsonl", encode_jsonl([good]).encode(), web="https://drive.google.com/uc?id=GOOD&export=download")
        drive.files[good_id]["webContentLink"] = f"https://drive.google.com/uc?id={good_id}&export=download"
        bad_id = drive.add(folder, "bad.jsonl", encode_jsonl([bad]).encode())
        drive.fail_ids.add(bad_id)
        provider = GoogleDriveProvider(drive, TOKEN)
        pulled = provider.pull()
        self.assertEqual(pulled["skipped"], 1)
        self.assertIn("1 file skipped", pulled["message"])
        names = [row["payload"]["name"] for row in pulled["events"]["Zasariz"]]
        self.assertEqual(names, ["Mask of Song"])
        self.assertTrue(any("alt=media" in url and good_id in url for _m, url, _h, _b in drive.calls))

    def test_download_host_401_is_not_an_expired_sign_in(self):
        drive = MockDrive()
        drive.web_unauthorized = True
        folder = _tree(drive)
        event = make_event(
            event_id="good",
            ts="2026-08-01T00:00:00",
            device_id="b" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Mask of Song", "pinned": True},
        )
        fid = drive.add(folder, "good.jsonl", encode_jsonl([event]).encode())
        drive.files[fid]["webContentLink"] = f"https://drive.google.com/uc?id={fid}&export=download"
        provider = GoogleDriveProvider(drive, TOKEN)
        pulled = provider.pull()
        self.assertEqual([row["payload"]["name"] for row in pulled["events"]["Zasariz"]], ["Mask of Song"])

    def test_api_401_keeps_the_drive_code_and_message(self):
        drive = MockDrive()
        drive.unauthorized = True
        provider = GoogleDriveProvider(drive, TOKEN)
        with self.assertRaises(SyncAuthExpired) as caught:
            provider.pull()
        text = str(caught.exception)
        self.assertIn("401", text)
        self.assertIn("UNAUTHENTICATED", text)
        self.assertIn("Invalid Credentials", text)
        self.assertIn("authError", text)

    def test_write_uses_the_sync_layout_and_leaves_other_devices_alone(self):
        drive = MockDrive()
        folder = _tree(drive)
        peer_id = drive.add(folder, f"{'b' * 32}.jsonl", b"peer\n")
        provider = GoogleDriveProvider(drive, TOKEN)
        event = make_event(
            event_id="mine",
            ts="2026-08-04T00:00:00",
            device_id="a" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Mask of Song", "pinned": True},
        )
        provider.write_own("Zasariz", "a" * 32, [event])
        provider.write_device_manifest("a" * 32, "Home PC", "2026-08-04T00:00:00")
        own = [item for item in drive.files.values() if item["name"] == f"{'a' * 32}.jsonl"]
        self.assertEqual(len(own), 1)
        self.assertIn(b"Mask of Song", own[0]["content"])
        self.assertEqual(drive.files[peer_id]["content"], b"peer\n")
        manifest = [item for item in drive.files.values() if item["name"] == "manifest.json"]
        self.assertEqual(len(manifest), 1)
        saved = json.loads(manifest[0]["content"].decode("utf-8"))
        self.assertEqual(saved["devices"]["a" * 32]["name"], "Home PC")
        patched = [url for method, url, _h, _b in drive.calls if method == "PATCH"]
        self.assertTrue(all(peer_id not in url for url in patched))
        self.assertTrue(all(headers.get("Authorization") == f"Bearer {TOKEN}" for _m, url, headers, _b in drive.calls if "googleapis.com" in url))

    def test_engine_syncs_through_the_google_session(self):
        import tempfile
        drive = MockDrive()
        folder = _tree(drive)
        remote = make_event(
            event_id="from-other-pc",
            ts="2026-08-01T00:00:00",
            device_id="b" * 32,
            source="manual",
            event_type="wish",
            payload={"name": "Mask of Song", "pinned": True},
        )
        drive.add(folder, f"{'b' * 32}.jsonl", encode_jsonl([remote]).encode())
        with tempfile.TemporaryDirectory() as tmp:
            engine = SyncEngine(Path(tmp), device_id="a" * 32, clock=lambda: "2026-08-04T22:00:01")
            engine.configure(provider="google")
            self.assertEqual(engine.test_google()["message"], GOOGLE_SIGN_IN)
            engine.set_google_session(TOKEN, "Google Drive", transport=drive)
            self.assertEqual(engine.status()["google"]["client_id"], GOOGLE_DRIVE_CLIENT_ID)
            self.assertEqual(engine.status()["google"]["scopes"], GOOGLE_DRIVE_SCOPES)
            engine.append_log_line("Zasariz", "You looted a test line.", "2026-08-04T22:00:01")
            status = engine.sync()
            self.assertEqual(status["status"], "ok")
            self.assertEqual(status["error"], "")
            wishes = engine.projection()["characters"]["Zasariz"]["wishes"]
            self.assertEqual(wishes, ["Mask of Song"])
            again = engine.sync()
            self.assertEqual(again["status"], "ok")

    def test_official_media_url_is_a_candidate(self):
        urls = download_candidates({"id": "abc", "webContentLink": "https://drive.google.com/uc?id=abc"})
        self.assertEqual(urls[0], "https://drive.google.com/uc?id=abc")
        self.assertEqual(urls[1], media_url("abc"))
        self.assertTrue(urls[1].startswith(f"{DRIVE_API}/files/"))
        described = describe_drive_error(DriveResponse(
            403,
            b'{"error":{"code":403,"message":"insufficient permissions","status":"PERMISSION_DENIED"}}',
        ))
        self.assertIn("403", described)
        self.assertIn("PERMISSION_DENIED", described)
        self.assertIn("insufficient permissions", described)


class _QuietHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.server.seen.append((self.path, self.headers.get("Authorization")))  # type: ignore[attr-defined]
        if getattr(self.server, "redirect_to", ""):
            self.send_response(302)
            self.send_header("Location", self.server.redirect_to)  # type: ignore[attr-defined]
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"file-bytes"
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


class DriveRedirectTests(unittest.TestCase):
    def test_redirect_and_download_host_do_not_get_authorization(self):
        download = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
        download.seen = []
        download.redirect_to = ""
        api = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
        api.seen = []
        api.redirect_to = f"http://127.0.0.1:{download.server_address[1]}/blob/file"
        threads = [
            threading.Thread(target=download.serve_forever, daemon=True),
            threading.Thread(target=api.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            transport = UrllibDriveTransport(base_url=f"http://127.0.0.1:{api.server_address[1]}")
            response = transport.request(
                "GET",
                "https://www.googleapis.com/drive/v3/files/abc?alt=media",
                {"Authorization": "Bearer secret-token", "Accept": "application/octet-stream"},
            )
            self.assertEqual(response.body, b"file-bytes")
            self.assertIs(response.api_host, False)
            self.assertIn("Bearer secret-token", api.seen[0][1] or "")
            self.assertIsNone(download.seen[0][1])
            direct = transport.request(
                "GET",
                f"http://127.0.0.1:{download.server_address[1]}/uc?id=abc",
                {"Authorization": "Bearer secret-token"},
            )
            self.assertEqual(direct.status, 200)
            self.assertIsNone(download.seen[-1][1])
        finally:
            api.shutdown()
            download.shutdown()
            api.server_close()
            download.server_close()


if __name__ == "__main__":
    unittest.main()
