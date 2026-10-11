"""Sync providers. Google Drive is not implemented; the factory is the plug-in point."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from .layout import (
    ICLOUD_WAITING,
    SYNC_DIR_NAME,
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

GRAPH_ROOT = "https://graph.microsoft.com/v1.0/me/drive/special/approot"
ONEDRIVE_CLIENT_ID = "868f921b-3445-4b09-90bf-13b343145256"
ONEDRIVE_AUTHORITY = "https://login.microsoftonline.com/common"
ONEDRIVE_SCOPES = "Files.ReadWrite.AppFolder offline_access"


class GraphResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body or b""


class GraphTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> GraphResponse: ...


class SyncProvider(Protocol):
    kind: str

    def pull(self) -> dict[str, Any]: ...

    def write_own(self, character: str, device_id: str, events: list[dict[str, Any]]) -> None: ...

    def write_device_manifest(self, device_id: str, name: str, updated: str) -> None: ...


def provider_for(kind: str, **kwargs: Any) -> SyncProvider:
    """Build a provider. ``google`` is reserved for 1.1.11."""
    if kind == "folder":
        return FolderProvider(kwargs["root"])
    if kind == "onedrive":
        return OneDriveProvider(kwargs["transport"], kwargs.get("token") or "")
    if kind == "google":
        raise SyncError("Google Drive sync is planned for 1.1.11 and is not in this version.")
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


class OneDriveProvider:
    """Microsoft Graph App Folder. Tests pass a fake transport; no network is required."""

    kind = "onedrive"

    def __init__(self, transport: GraphTransport, token: str) -> None:
        self.transport = transport
        self.token = token or ""

    def _headers(self, content: bool = False) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if content:
            headers["Content-Type"] = "application/octet-stream"
        return headers

    def _call(self, method: str, url: str, body: bytes | None = None, content: bool = False) -> GraphResponse:
        if not self.token:
            raise SyncError("Sign in to OneDrive.")
        try:
            response = self.transport.request(method, url, self._headers(content), body)
        except SyncOffline:
            raise
        except OSError as exc:
            raise SyncOffline("Offline. Changes stay on this PC until OneDrive is reachable.") from exc
        if response.status == 401:
            raise SyncError("OneDrive sign-in expired. Sign in again.")
        return response

    def pull(self) -> dict[str, Any]:
        events: dict[str, list[dict[str, Any]]] = {}
        listing = self._call("GET", _graph_path(f"{SYNC_DIR_NAME}/events", "/children"))
        if listing.status == 404:
            folders: list[str] = []
        elif listing.status >= 400:
            raise SyncError(f"OneDrive could not list events ({listing.status}).")
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
                raise SyncError(f"OneDrive could not list {character} ({children.status}).")
            gathered: list[list[dict[str, Any]]] = []
            for name in _child_names(children.body, folders_only=False):
                if not is_event_filename(name):
                    continue
                downloaded = self._call("GET", _graph_path(f"{relative}/{name}", "/content"))
                if downloaded.status == 404:
                    continue
                if downloaded.status >= 400:
                    raise SyncError(f"OneDrive could not read {name} ({downloaded.status}).")
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
            raise SyncError(f"OneDrive could not save this PC's events ({response.status}).")

    def write_device_manifest(self, device_id: str, name: str, updated: str) -> None:
        current = self._pull_manifest()
        devices = dict(current.get("devices") or {})
        devices[safe_device_file(device_id)] = {"name": name, "updated": updated}
        body = json.dumps({"version": 1, "devices": devices}, ensure_ascii=False).encode("utf-8")
        response = self._call("PUT", _graph_path(f"{SYNC_DIR_NAME}/manifest.json", "/content"), body, content=True)
        if response.status >= 400:
            raise SyncError(f"OneDrive could not save the manifest ({response.status}).")


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
