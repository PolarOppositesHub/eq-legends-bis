"""Sync providers. Google Drive is not implemented; the factory is the plug-in point."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from .layout import (
    ICLOUD_WAITING,
    SYNC_DIR_NAME,
    SyncAuthExpired,
    SyncError,
    SyncOffline,
    WaitingForCloud,
    character_folder_name,
    is_conflicted_name,
    is_event_filename,
    merge_manifests,
    own_event_path,
    read_events_file,
    read_manifest_file,
    safe_device_file,
    sync_root,
    write_events_file,
    write_manifest,
)
from .model import union_events

GRAPH_API = "https://graph.microsoft.com/v1.0"
GRAPH_ROOT = f"{GRAPH_API}/me/drive/special/approot"
ONEDRIVE_CLIENT_ID = "868f921b-3445-4b09-90bf-13b343145256"
# /common signs in both work and personal accounts. /consumers would reject work
# accounts. Personal-account App Folder tokens still need the fully qualified
# Graph scope below; a bare Files.ReadWrite.AppFolder scope is not enough.
ONEDRIVE_AUTHORITY = "https://login.microsoftonline.com/common"
ONEDRIVE_SCOPES = "https://graph.microsoft.com/Files.ReadWrite.AppFolder offline_access"
ONEDRIVE_SIGN_IN = "Sign in to OneDrive"
ONEDRIVE_SIGN_IN_EXPIRED = "OneDrive sign-in expired. Sign in again."
ONEDRIVE_UPDATE_SIGN_IN = "Sign in to OneDrive again to finish the update"
CONNECTED_APP_FOLDER = "Connected to OneDrive App Folder"
GRAPH_TIMEOUT_SECONDS = 30
GRAPH_LOGGER = logging.getLogger("eq.sync.graph")

_WWW_AUTH_PARAM = re.compile(r'([A-Za-z0-9_\-]+)\s*=\s*("(?:\\.|[^"])*"|[^,\s]+)')

# Tests point the default transport at a local fake Graph server. Production leaves this unset.
_graph_base_for_tests: str | None = None


class GraphResponse:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.body = body or b""
        self.headers = dict(headers or {})

    def header(self, name: str) -> str:
        wanted = name.lower()
        for key, value in self.headers.items():
            if str(key).lower() == wanted:
                return str(value)
        return ""


class GraphTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> GraphResponse: ...


def set_graph_base_url_for_tests(url: str | None) -> None:
    """Override the Graph host for tests. Production never calls this."""
    global _graph_base_for_tests
    _graph_base_for_tests = url.rstrip("/") if url else None


def default_graph_transport() -> "UrllibGraphTransport":
    """The transport production uses when the caller does not inject one."""
    return UrllibGraphTransport(base_url=_graph_base_for_tests)


class UrllibGraphTransport:
    """Microsoft Graph over urllib. JSON listings and raw file bytes. No extra packages."""

    def __init__(self, *, base_url: str | None = None, timeout: float = GRAPH_TIMEOUT_SECONDS) -> None:
        self.base_url = (base_url or GRAPH_API).rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> GraphResponse:
        target = self._resolve(url)
        request = urllib.request.Request(
            target,
            data=body,
            headers=dict(headers or {}),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                status = int(getattr(response, "status", response.getcode()))
                return GraphResponse(status, payload, _header_map(getattr(response, "headers", None)))
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read()
            except Exception:
                payload = b""
            return GraphResponse(int(exc.code), payload or b"", _header_map(getattr(exc, "headers", None)))
        except TimeoutError as exc:
            raise OSError("OneDrive timed out.") from exc
        except urllib.error.URLError as exc:
            raise OSError(f"OneDrive could not be reached: {exc.reason}") from exc

    def _resolve(self, url: str) -> str:
        production = GRAPH_API.rstrip("/")
        if self.base_url == production:
            return url
        if url.startswith(production):
            return self.base_url + url[len(production):]
        return url


class SyncProvider(Protocol):
    kind: str

    def pull(self) -> dict[str, Any]: ...

    def write_own(self, character: str, device_id: str, events: list[dict[str, Any]]) -> None: ...

    def write_device_manifest(self, device_id: str, name: str, updated: str) -> None: ...


def provider_for(kind: str, **kwargs: Any) -> SyncProvider:
    """Build a provider. ``google`` is reserved for 1.1.13."""
    if kind == "folder":
        return FolderProvider(kwargs["root"])
    if kind == "onedrive":
        return OneDriveProvider(kwargs["transport"], kwargs.get("token") or "")
    if kind == "google":
        raise SyncError("Google Drive sync is planned for 1.1.13 and is not in this version.")
    raise SyncError("Choose Sync folder or OneDrive.")


class FolderProvider:
    """A folder the user picked: iCloud Drive, Dropbox, OneDrive's desktop folder, or any path."""

    kind = "folder"

    def __init__(self, root: str | Path, *, online: bool = True) -> None:
        self.root = Path(root)
        self.online = online

    def _online(self) -> None:
        if not self.online:
            raise SyncOffline("Offline. Changes stay on this PC until the sync folder is reachable.")

    def pull(self) -> dict[str, Any]:
        self._online()
        root = sync_root(self.root)
        waiting = False
        if not root.exists():
            return {"events": {}, "waiting": False, "manifest": {"version": 1, "devices": {}}}
        try:
            waiting = waiting or self._dir_waiting(root)
        except WaitingForCloud:
            return {
                "events": {},
                "waiting": True,
                "manifest": {"version": 1, "devices": {}},
                "message": ICLOUD_WAITING,
            }
        events: dict[str, list[dict[str, Any]]] = {}
        events_root = root / "events"
        if events_root.is_dir():
            for character_dir in events_root.iterdir():
                if not character_dir.is_dir():
                    continue
                gathered: list[list[dict[str, Any]]] = []
                try:
                    names = list(character_dir.iterdir())
                except OSError as exc:
                    from .layout import is_cloud_placeholder
                    if is_cloud_placeholder(exc):
                        waiting = True
                        continue
                    raise
                for path in names:
                    if not path.is_file() or not is_event_filename(path.name):
                        continue
                    try:
                        gathered.append(read_events_file(path))
                    except WaitingForCloud:
                        waiting = True
                events[character_dir.name] = union_events(gathered)
        try:
            manifest = self._read_manifest()
        except WaitingForCloud:
            waiting = True
            manifest = {"version": 1, "devices": {}}
        return {"events": events, "waiting": waiting, "manifest": manifest, "message": ICLOUD_WAITING if waiting else ""}

    def _dir_waiting(self, root: Path) -> bool:
        try:
            root.iterdir()
        except OSError as exc:
            from .layout import is_cloud_placeholder
            if is_cloud_placeholder(exc):
                raise WaitingForCloud() from exc
            raise
        return False

    def _read_manifest(self) -> dict[str, Any]:
        root = sync_root(self.root)
        parts: list[dict[str, Any]] = []
        if not root.is_dir():
            return {"version": 1, "devices": {}}
        for path in root.iterdir():
            if not path.is_file():
                continue
            lower = path.name.lower()
            if lower == "manifest.json" or (lower.startswith("manifest") and is_conflicted_name(path.name)):
                try:
                    parts.append(read_manifest_file(path))
                except WaitingForCloud:
                    raise
        return merge_manifests(parts) if parts else {"version": 1, "devices": {}}

    def write_own(self, character: str, device_id: str, events: list[dict[str, Any]]) -> None:
        self._online()
        path = own_event_path(self.root, character, device_id)
        write_events_file(path, events)

    def write_device_manifest(self, device_id: str, name: str, updated: str) -> None:
        self._online()
        current = self._read_manifest()
        devices = dict(current.get("devices") or {})
        devices[safe_device_file(device_id)] = {"name": name, "updated": updated}
        try:
            write_manifest(self.root, {"version": 1, "devices": devices})
        except WaitingForCloud:
            raise


def _graph_path(relative: str, suffix: str) -> str:
    return f"{GRAPH_ROOT}:/{quote(relative, safe='/')}:{suffix}"


def _header_map(headers: Any) -> dict[str, str]:
    if not headers:
        return {}
    try:
        pairs = list(headers.items())
    except Exception:
        return {}
    return {str(key): str(value) for key, value in pairs}


def _unquote_auth_value(raw: str) -> str:
    text = str(raw or "").strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].replace(r"\"", '"')
    return text


def parse_www_authenticate(header: str) -> tuple[str, str]:
    """error and error_description from a WWW-Authenticate challenge."""
    params: dict[str, str] = {}
    for match in _WWW_AUTH_PARAM.finditer(str(header or "")):
        params[match.group(1).lower()] = _unquote_auth_value(match.group(2))
    return params.get("error", ""), params.get("error_description", "")


def parse_graph_error(body: bytes, www_authenticate: str = "") -> dict[str, str]:
    """Graph error.code / error.message, plus the WWW-Authenticate challenge."""
    code = ""
    message = ""
    try:
        data = json.loads((body or b"").decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "")
            message = str(err.get("message") or "")
        elif isinstance(err, str):
            code = err
            message = str(data.get("error_description") or data.get("message") or "")
    header_error, header_description = parse_www_authenticate(www_authenticate)
    return {
        "code": " ".join(code.split()),
        "message": " ".join(message.split()),
        "www_error": " ".join(header_error.split()),
        "www_description": " ".join(header_description.split()),
    }


def describe_graph_error(response: GraphResponse) -> str:
    """Status plus Graph's code and message, and the WWW-Authenticate challenge."""
    parsed = parse_graph_error(response.body, response.header("WWW-Authenticate"))
    if parsed["code"] and parsed["message"]:
        detail = f"{parsed['code']}: {parsed['message']}"
    else:
        detail = parsed["code"] or parsed["message"]
    if parsed["www_error"] and parsed["www_description"]:
        header = f"{parsed['www_error']}: {parsed['www_description']}"
    else:
        header = parsed["www_error"] or parsed["www_description"]
    if header and header not in detail and parsed["www_error"] != parsed["code"]:
        extra = f"WWW-Authenticate {header}"
        detail = f"{detail} ({extra})" if detail else extra
    detail = " ".join(detail.split())
    if detail:
        return f"{response.status} {detail}"
    return str(response.status)


def redact_secrets(text: str, token: str = "") -> str:
    """Drop bearer tokens and a known access token before anything is logged."""
    cleaned = str(text or "")
    if token:
        cleaned = cleaned.replace(token, "[redacted]")
    cleaned = re.sub(r"(?i)Bearer\s+\S+", "Bearer [redacted]", cleaned)
    cleaned = re.sub(r"(?i)(access_token|refresh_token)=([^&\s]+)", r"\1=[redacted]", cleaned)
    return cleaned


def log_graph_error(method: str, url: str, status: int, detail: str, token: str = "") -> None:
    """Sidecar log line for a Graph error. The access token is never written.

    ``status`` is accepted so callers can pass the HTTP code beside ``detail``,
    which already starts with that code.
    """
    _ = status
    safe_url = redact_secrets(str(url or "").split("?", 1)[0], token)
    safe_detail = redact_secrets(detail, token)
    GRAPH_LOGGER.warning("Graph %s %s -> %s", method, safe_url, safe_detail)


class OneDriveProvider:
    """Microsoft Graph App Folder. Tests may inject a fake transport."""

    kind = "onedrive"

    def __init__(self, transport: GraphTransport, token: str, session: dict[str, Any] | None = None) -> None:
        self.transport = transport
        self.token = token or ""
        self.session = session if session is not None else {}

    def _headers(self, content: bool = False) -> dict[str, str]:
        # Graph requires the Bearer scheme and a single space. The token is not logged.
        headers = {"Authorization": f"Bearer {self.token}"}
        if content:
            headers["Content-Type"] = "application/octet-stream"
        return headers

    def _call(self, method: str, url: str, body: bytes | None = None, content: bool = False) -> GraphResponse:
        if not self.token:
            raise SyncError(ONEDRIVE_SIGN_IN)
        try:
            response = self.transport.request(method, url, self._headers(content), body)
        except SyncOffline:
            raise
        except OSError as exc:
            raise SyncOffline("Offline. Changes stay on this PC until OneDrive is reachable.") from exc
        if response.status >= 400:
            detail = describe_graph_error(response)
            log_graph_error(method, url, response.status, detail, self.token)
            if response.status == 401:
                raise SyncAuthExpired(f"OneDrive Graph {detail}")
        return response

    def ensure_approot(self) -> None:
        """GET the App Folder once per access token so OneDrive creates it."""
        if self.token and self.session.get("approot_token") == self.token:
            return
        response = self._call("GET", GRAPH_ROOT)
        if response.status >= 400:
            raise SyncError(f"OneDrive could not open the App Folder ({describe_graph_error(response)}).")
        self.session["approot_token"] = self.token

    def test_connection(self) -> dict[str, Any]:
        """Live App Folder check. Always calls Graph, including after a successful provision."""
        response = self._call("GET", GRAPH_ROOT)
        if response.status >= 400:
            return {"ok": False, "message": f"OneDrive Graph {describe_graph_error(response)}"}
        self.session["approot_token"] = self.token
        return {"ok": True, "message": CONNECTED_APP_FOLDER}

    def pull(self) -> dict[str, Any]:
        self.ensure_approot()
        events: dict[str, list[dict[str, Any]]] = {}
        listing = self._call("GET", _graph_path(f"{SYNC_DIR_NAME}/events", "/children"))
        if listing.status == 404:
            folders: list[str] = []
        elif listing.status >= 400:
            raise SyncError(f"OneDrive could not list events ({describe_graph_error(listing)}).")
        else:
            folders = _child_names(listing.body, folders_only=True)
        for folder_name in folders:
            character = folder_name
            try:
                character_folder_name(character)
            except ValueError:
                continue
            relative = f"{SYNC_DIR_NAME}/events/{character}"
            children = self._call("GET", _graph_path(relative, "/children"))
            if children.status == 404:
                continue
            if children.status >= 400:
                raise SyncError(f"OneDrive could not list {character} ({describe_graph_error(children)}).")
            gathered: list[list[dict[str, Any]]] = []
            for name in _child_names(children.body, folders_only=False):
                if not is_event_filename(name):
                    continue
                downloaded = self._call("GET", _graph_path(f"{relative}/{name}", "/content"))
                if downloaded.status == 404:
                    continue
                if downloaded.status >= 400:
                    raise SyncError(f"OneDrive could not read {name} ({describe_graph_error(downloaded)}).")
                from .model import decode_jsonl
                text = downloaded.body.decode("utf-8", errors="replace")
                gathered.append(decode_jsonl(text))
            events[character] = union_events(gathered)
        manifest = self._pull_manifest()
        return {"events": events, "waiting": False, "manifest": manifest, "message": ""}

    def _pull_manifest(self) -> dict[str, Any]:
        parts: list[dict[str, Any]] = []
        listing = self._call("GET", _graph_path(SYNC_DIR_NAME, "/children"))
        if listing.status == 404:
            return {"version": 1, "devices": {}}
        if listing.status >= 400:
            return {"version": 1, "devices": {}}
        for name in _child_names(listing.body, folders_only=False):
            lower = name.lower()
            if lower != "manifest.json" and not (lower.startswith("manifest") and is_conflicted_name(name)):
                continue
            downloaded = self._call("GET", _graph_path(f"{SYNC_DIR_NAME}/{name}", "/content"))
            if downloaded.status >= 400:
                continue
            try:
                data = json.loads(downloaded.body.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                devices = data.get("devices") if isinstance(data.get("devices"), dict) else {}
                parts.append({"version": 1, "devices": devices})
        return merge_manifests(parts) if parts else {"version": 1, "devices": {}}

    def write_own(self, character: str, device_id: str, events: list[dict[str, Any]]) -> None:
        from .model import encode_jsonl
        relative = (
            f"{SYNC_DIR_NAME}/events/{character_folder_name(character)}/"
            f"{safe_device_file(device_id)}.jsonl"
        )
        body = encode_jsonl(events).encode("utf-8")
        response = self._call("PUT", _graph_path(relative, "/content"), body, content=True)
        if response.status >= 400:
            raise SyncError(f"OneDrive could not save this PC's events ({describe_graph_error(response)}).")

    def write_device_manifest(self, device_id: str, name: str, updated: str) -> None:
        current = self._pull_manifest()
        devices = dict(current.get("devices") or {})
        devices[safe_device_file(device_id)] = {"name": name, "updated": updated}
        body = json.dumps({"version": 1, "devices": devices}, ensure_ascii=False).encode("utf-8")
        response = self._call("PUT", _graph_path(f"{SYNC_DIR_NAME}/manifest.json", "/content"), body, content=True)
        if response.status >= 400:
            raise SyncError(f"OneDrive could not save the manifest ({describe_graph_error(response)}).")


def _child_names(body: bytes, *, folders_only: bool) -> list[str]:
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return []
    names: list[str] = []
    for item in data.get("value") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        if folders_only and "folder" not in item:
            continue
        if not folders_only and "folder" in item and "file" not in item:
            continue
        names.append(str(item["name"]))
    return names
