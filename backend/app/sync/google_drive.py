"""Google Drive appDataFolder provider.

Files use the same layout as the sync folder and OneDrive:
``EQLegendsBiS-sync/manifest.json`` and ``events/<character>/<device_id>.jsonl``.
The scope is the hidden app folder only.

Downloads prefer a listing's ``webContentLink`` and otherwise use the Drive
``alt=media`` URL. Authorization is sent only to the Google API host. A
redirect is fetched again with no Authorization header. One bad file is
skipped. The API error code and message are kept for Settings.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlsplit

from .layout import (
    SYNC_DIR_NAME,
    SyncAuthExpired,
    SyncError,
    SyncOffline,
    character_folder_name,
    is_conflicted_name,
    is_event_filename,
    merge_manifests,
    safe_device_file,
)
from .model import decode_jsonl, union_events

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
DRIVE_ORIGIN = "https://www.googleapis.com"
GOOGLE_DRIVE_CLIENT_ID = "REPLACE_WITH_GOOGLE_DESKTOP_CLIENT_ID"
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_SCOPES = "https://www.googleapis.com/auth/drive.appdata"
GOOGLE_SIGN_IN = "Sign in to Google Drive"
GOOGLE_SIGN_IN_EXPIRED = "Google Drive sign-in expired. Sign in again."
GOOGLE_UPDATE_SIGN_IN = "Sign in to Google Drive again to finish the update"
CONNECTED_APP_DATA = "Connected to Google Drive app folder"
FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_TIMEOUT_SECONDS = 30
DRIVE_MAX_REDIRECTS = 5
DRIVE_LOGGER = logging.getLogger("eq.sync.drive")
_SAFE_REDIRECT_HEADERS = frozenset({"accept", "accept-language", "user-agent"})
_CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization"})
_APP_DATA = "appDataFolder"

_drive_base_for_tests: str | None = None


class DriveResponse:
    def __init__(
        self,
        status: int,
        body: bytes,
        headers: dict[str, str] | None = None,
        *,
        url: str = "",
        api_host: bool | None = None,
    ) -> None:
        self.status = status
        self.body = body or b""
        self.headers = dict(headers or {})
        self.url = url
        # None means the caller did not say. False means a download host, not the API.
        self.api_host = api_host

    def header(self, name: str) -> str:
        wanted = name.lower()
        for key, value in self.headers.items():
            if str(key).lower() == wanted:
                return str(value)
        return ""


def set_drive_base_url_for_tests(url: str | None) -> None:
    """Override the Drive API origin for tests. Production never calls this."""
    global _drive_base_for_tests
    _drive_base_for_tests = url.rstrip("/") if url else None


def default_drive_transport() -> "UrllibDriveTransport":
    return UrllibDriveTransport(base_url=_drive_base_for_tests)


def _endpoint_key(url: str) -> tuple[str, int]:
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").lower()
    if parts.port:
        port = int(parts.port)
    elif parts.scheme == "https":
        port = 443
    elif parts.scheme == "http":
        port = 80
    else:
        port = 0
    return host, port


def is_drive_api_url(url: str, base_url: str | None = None) -> bool:
    """True for www.googleapis.com, or the test origin standing in for it."""
    host = (urlsplit(str(url or "")).hostname or "").lower()
    if host == "googleapis.com" or host.endswith(".googleapis.com"):
        return True
    if base_url and host and _endpoint_key(url) == _endpoint_key(base_url):
        return True
    return False


def _safe_redirect_headers(headers: dict[str, str] | None) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in (headers or {}).items():
        if str(key).lower() in _SAFE_REDIRECT_HEADERS:
            safe[str(key)] = str(value)
    return safe


def _header_map(headers: Any) -> dict[str, str]:
    if not headers:
        return {}
    try:
        pairs = list(headers.items())
    except Exception:
        return {}
    return {str(key): str(value) for key, value in pairs}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class UrllibDriveTransport:
    """Drive API over urllib. Authorization stays on the API host.

    ``alt=media`` and ``webContentLink`` often 302 to a download host. urllib
    would keep ``Authorization`` on that hop. This transport fetches Location
    with a fresh request and no credential headers.
    """

    def __init__(self, *, base_url: str | None = None, timeout: float = DRIVE_TIMEOUT_SECONDS) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> DriveResponse:
        target = self._resolve(url)
        method_now = method
        body_now = body
        response = self._open(method_now, target, dict(headers or {}), body_now)
        seen = {target}
        hops = 0
        while 300 <= response.status < 400:
            location = response.header("Location").strip()
            if not location:
                break
            hops += 1
            if hops > DRIVE_MAX_REDIRECTS:
                raise OSError("Google Drive redirected too many times.")
            nxt = urljoin(response.url or target, location)
            parts = urlsplit(nxt)
            if parts.scheme not in {"http", "https"}:
                raise OSError("Google Drive redirected to an unsupported URL.")
            if nxt in seen:
                raise OSError("Google Drive redirected too many times.")
            seen.add(nxt)
            if response.status in {301, 302, 303} and method_now not in {"GET", "HEAD"}:
                method_now = "GET"
                body_now = None
            response = self._open(method_now, nxt, _safe_redirect_headers(headers), body_now)
            target = nxt
        return response

    def _is_api_host(self, url: str) -> bool:
        return is_drive_api_url(url, self.base_url or None)

    def _open(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> DriveResponse:
        send = dict(headers or {})
        if not self._is_api_host(url):
            send = {
                str(key): str(value)
                for key, value in send.items()
                if str(key).lower() not in _CREDENTIAL_HEADERS
            }
        request = urllib.request.Request(url, data=body, headers=send, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = response.read()
                status = int(getattr(response, "status", response.getcode()))
                final = str(getattr(response, "url", None) or url)
                return DriveResponse(
                    status,
                    payload,
                    _header_map(getattr(response, "headers", None)),
                    url=final,
                    api_host=self._is_api_host(final),
                )
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read()
            except Exception:
                payload = b""
            final = str(getattr(exc, "url", None) or url)
            return DriveResponse(
                int(exc.code),
                payload or b"",
                _header_map(getattr(exc, "headers", None)),
                url=final,
                api_host=self._is_api_host(final),
            )
        except TimeoutError as exc:
            raise OSError("Google Drive timed out.") from exc
        except urllib.error.URLError as exc:
            raise OSError(f"Google Drive could not be reached: {exc.reason}") from exc

    def _resolve(self, url: str) -> str:
        if not self.base_url or self.base_url == DRIVE_ORIGIN:
            return url
        if url.startswith(DRIVE_ORIGIN):
            return self.base_url + url[len(DRIVE_ORIGIN):]
        return url


def escape_query(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def child_query(parent_id: str, name: str | None = None, *, folders_only: bool = False) -> str:
    parts = [f"'{escape_query(parent_id)}' in parents", "trashed = false"]
    if name is not None:
        parts.append(f"name = '{escape_query(name)}'")
    if folders_only:
        parts.append(f"mimeType = '{FOLDER_MIME}'")
    return " and ".join(parts)


def files_list_url(query: str, *, page_size: int = 1000, page_token: str = "") -> str:
    params = {
        "spaces": _APP_DATA,
        "q": query,
        "pageSize": str(page_size),
        "fields": "files(id,name,mimeType,webContentLink),nextPageToken",
    }
    if page_token:
        params["pageToken"] = page_token
    return f"{DRIVE_API}/files?{urlencode(params)}"


def media_url(file_id: str) -> str:
    return f"{DRIVE_API}/files/{quote(str(file_id), safe='')}?alt=media"


def upload_url(file_id: str) -> str:
    return f"{DRIVE_UPLOAD}/files/{quote(str(file_id), safe='')}?uploadType=media"


def download_candidates(item: dict[str, Any]) -> list[str]:
    """Listing download URL first, then the official Drive media URL."""
    found: list[str] = []
    link = str(item.get("webContentLink") or "").strip()
    if link:
        found.append(link)
    file_id = str(item.get("id") or "").strip()
    if file_id:
        official = media_url(file_id)
        if official not in found:
            found.append(official)
    return found


def parse_drive_error(body: bytes) -> dict[str, str]:
    """Drive ``error.code``, ``error.status``, ``error.errors[].reason``, and message."""
    code = ""
    message = ""
    status = ""
    reason = ""
    try:
        data = json.loads((body or b"").decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "")
            message = str(err.get("message") or "")
            status = str(err.get("status") or "")
            errors = err.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                reason = str(errors[0].get("reason") or "")
                if not message:
                    message = str(errors[0].get("message") or "")
        elif isinstance(err, str):
            code = err
            message = str(data.get("error_description") or data.get("message") or "")
    return {
        "code": " ".join(code.split()),
        "message": " ".join(message.split()),
        "status": " ".join(status.split()),
        "reason": " ".join(reason.split()),
    }


def describe_drive_error(response: DriveResponse) -> str:
    """HTTP status plus Drive's code, status, reason, and message."""
    parsed = parse_drive_error(response.body)
    labels: list[str] = []
    if parsed["code"] and parsed["code"] != str(response.status):
        labels.append(parsed["code"])
    if parsed["status"]:
        labels.append(parsed["status"])
    if parsed["reason"] and parsed["reason"] not in labels:
        labels.append(parsed["reason"])
    label = " ".join(labels)
    if label and parsed["message"]:
        detail = f"{label}: {parsed['message']}"
    else:
        detail = label or parsed["message"]
    detail = " ".join(detail.split())
    if detail:
        return f"{response.status} {detail}"
    return str(response.status)


def redact_secrets(text: str, token: str = "") -> str:
    cleaned = str(text or "")
    if token:
        cleaned = cleaned.replace(token, "[redacted]")
    return cleaned


def log_drive_error(method: str, url: str, status: int, detail: str, token: str = "") -> None:
    _ = status
    safe_url = redact_secrets(str(url or "").split("?", 1)[0], token)
    safe_detail = redact_secrets(detail, token)
    DRIVE_LOGGER.warning("Drive %s %s -> %s", method, safe_url, safe_detail)


def _json_body(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads((body or b"").decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


class GoogleDriveProvider:
    """Hidden Drive app folder. Tests may inject a fake transport."""

    kind = "google"

    def __init__(self, transport: Any, token: str, session: dict[str, Any] | None = None) -> None:
        self.transport = transport
        self.token = token or ""
        self.session = session if session is not None else {}
        self.skipped = 0
        self._skipped_keys: set[str] = set()

    def _headers(self, content_type: str = "") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _response_is_api(self, response: DriveResponse, url: str) -> bool:
        if response.api_host is not None:
            return bool(response.api_host)
        base = getattr(self.transport, "base_url", None) or None
        return is_drive_api_url(response.url or url, base)

    def _call(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        content_type: str = "",
    ) -> DriveResponse:
        if not self.token:
            raise SyncError(GOOGLE_SIGN_IN)
        try:
            response = self.transport.request(method, url, self._headers(content_type), body)
        except SyncOffline:
            raise
        except OSError as exc:
            raise SyncOffline("Offline. Changes stay on this PC until Google Drive is reachable.") from exc
        if response.status >= 400:
            detail = describe_drive_error(response)
            log_drive_error(method, response.url or url, response.status, detail, self.token)
            if response.status == 401 and self._response_is_api(response, url):
                raise SyncAuthExpired(f"Google Drive {detail}")
        return response

    def ensure_app_data(self) -> None:
        """List the app folder once per access token so Drive opens it."""
        if self.token and self.session.get("appdata_token") == self.token:
            return
        response = self._call(
            "GET",
            files_list_url(child_query(_APP_DATA), page_size=1),
        )
        if response.status >= 400:
            raise SyncError(f"Google Drive could not open the app folder ({describe_drive_error(response)}).")
        self.session["appdata_token"] = self.token

    def test_connection(self) -> dict[str, Any]:
        """Live app-folder check. Always calls Drive, including after a successful open."""
        response = self._call(
            "GET",
            files_list_url(child_query(_APP_DATA), page_size=1),
        )
        if response.status >= 400:
            return {"ok": False, "message": f"Google Drive {describe_drive_error(response)}"}
        self.session["appdata_token"] = self.token
        return {"ok": True, "message": CONNECTED_APP_DATA}

    def pull(self) -> dict[str, Any]:
        from .providers import skipped_files_message

        self.skipped = 0
        self._skipped_keys = set()
        self.ensure_app_data()
        root = self._find(_APP_DATA, SYNC_DIR_NAME, folder=True)
        events: dict[str, list[dict[str, Any]]] = {}
        manifest = {"version": 1, "devices": {}}
        if root:
            events_folder = self._find(str(root["id"]), "events", folder=True)
            if events_folder:
                for folder in self._children(str(events_folder["id"]), folders=True):
                    character = str(folder.get("name") or "")
                    try:
                        character_folder_name(character)
                    except ValueError:
                        continue
                    gathered: list[list[dict[str, Any]]] = []
                    for item in self._children(str(folder["id"]), folders=False):
                        name = str(item.get("name") or "")
                        if not is_event_filename(name):
                            continue
                        payload = self._read_download(item)
                        if payload is None:
                            continue
                        gathered.append(decode_jsonl(payload.decode("utf-8", errors="replace")))
                    events[character] = union_events(gathered)
            manifest = self._pull_manifest(str(root["id"]))
        return {
            "events": events,
            "waiting": False,
            "manifest": manifest,
            "message": skipped_files_message(self.skipped),
            "skipped": self.skipped,
        }

    def _read_download(self, item: dict[str, Any]) -> bytes | None:
        """File bytes, or None when the file is missing or skipped.

        ``webContentLink`` is preferred when the listing has one. The official
        ``alt=media`` URL is the fallback. One failed file does not raise. A
        401 from the Drive API host still does.
        """
        relative = str(item.get("id") or item.get("name") or "")
        candidates = download_candidates(item)
        if not candidates:
            self._note_skip(relative)
            return None
        for index, url in enumerate(candidates):
            last = index == len(candidates) - 1
            try:
                response = self._call("GET", url)
            except SyncAuthExpired:
                raise
            except SyncOffline as exc:
                if last:
                    log_drive_error("GET", url, 0, str(exc), self.token)
                    self._note_skip(relative)
                    return None
                continue
            if 200 <= response.status < 300:
                return response.body
            if response.status == 404:
                if last:
                    return None
                continue
            if last:
                self._note_skip(relative)
                return None
        return None

    def _note_skip(self, relative: str) -> None:
        if not relative or relative in self._skipped_keys:
            return
        self._skipped_keys.add(relative)
        self.skipped += 1

    def _pull_manifest(self, root_id: str) -> dict[str, Any]:
        parts: list[dict[str, Any]] = []
        for item in self._children(root_id, folders=False):
            name = str(item.get("name") or "")
            lower = name.lower()
            if lower != "manifest.json" and not (lower.startswith("manifest") and is_conflicted_name(name)):
                continue
            payload = self._read_download(item)
            if payload is None:
                continue
            data = _json_body(payload)
            devices = data.get("devices") if isinstance(data.get("devices"), dict) else {}
            parts.append({"version": 1, "devices": devices})
        return merge_manifests(parts) if parts else {"version": 1, "devices": {}}

    def write_own(self, character: str, device_id: str, events: list[dict[str, Any]]) -> None:
        from .model import encode_jsonl

        root_id = self._ensure_folder(_APP_DATA, SYNC_DIR_NAME)
        events_id = self._ensure_folder(root_id, "events")
        character_id = self._ensure_folder(events_id, character_folder_name(character))
        name = f"{safe_device_file(device_id)}.jsonl"
        body = encode_jsonl(events).encode("utf-8")
        self._write_file(character_id, name, body)

    def write_device_manifest(self, device_id: str, name: str, updated: str) -> None:
        root_id = self._ensure_folder(_APP_DATA, SYNC_DIR_NAME)
        current = self._pull_manifest(root_id)
        devices = dict(current.get("devices") or {})
        devices[safe_device_file(device_id)] = {"name": name, "updated": updated}
        body = json.dumps({"version": 1, "devices": devices}, ensure_ascii=False).encode("utf-8")
        self._write_file(root_id, "manifest.json", body)

    def _write_file(self, parent_id: str, name: str, body: bytes) -> None:
        existing = self._find(parent_id, name, folder=False)
        if existing:
            file_id = str(existing["id"])
        else:
            created = self._call(
                "POST",
                f"{DRIVE_API}/files",
                json.dumps({"name": name, "parents": [parent_id]}).encode("utf-8"),
                "application/json",
            )
            if created.status >= 400:
                raise SyncError(f"Google Drive could not save {name} ({describe_drive_error(created)}).")
            file_id = str(_json_body(created.body).get("id") or "")
            if not file_id:
                raise SyncError(f"Google Drive could not save {name}.")
        uploaded = self._call("PATCH", upload_url(file_id), body, "application/octet-stream")
        if uploaded.status >= 400:
            raise SyncError(f"Google Drive could not save {name} ({describe_drive_error(uploaded)}).")

    def _ensure_folder(self, parent_id: str, name: str) -> str:
        found = self._find(parent_id, name, folder=True)
        if found:
            return str(found["id"])
        created = self._call(
            "POST",
            f"{DRIVE_API}/files",
            json.dumps({
                "name": name,
                "mimeType": FOLDER_MIME,
                "parents": [parent_id],
            }).encode("utf-8"),
            "application/json",
        )
        if created.status >= 400:
            raise SyncError(f"Google Drive could not create {name} ({describe_drive_error(created)}).")
        file_id = str(_json_body(created.body).get("id") or "")
        if not file_id:
            raise SyncError(f"Google Drive could not create {name}.")
        return file_id

    def _find(self, parent_id: str, name: str, *, folder: bool) -> dict[str, Any] | None:
        for item in self._list(child_query(parent_id, name, folders_only=folder)):
            if str(item.get("name") or "") != name:
                continue
            is_folder = item.get("mimeType") == FOLDER_MIME
            if folder != is_folder:
                continue
            return item
        return None

    def _children(self, parent_id: str, *, folders: bool) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for item in self._list(child_query(parent_id)):
            is_folder = item.get("mimeType") == FOLDER_MIME
            if folders != is_folder:
                continue
            found.append(item)
        return found

    def _list(self, query: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = ""
        for _ in range(20):
            response = self._call("GET", files_list_url(query, page_token=page))
            if response.status == 404:
                return items
            if response.status >= 400:
                raise SyncError(f"Google Drive could not list files ({describe_drive_error(response)}).")
            data = _json_body(response.body)
            for item in data.get("files") or []:
                if isinstance(item, dict) and item.get("id") and item.get("name"):
                    items.append(item)
            page = str(data.get("nextPageToken") or "")
            if not page:
                break
        return items
