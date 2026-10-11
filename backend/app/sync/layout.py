"""On-disk layout shared by every provider.

``EQLegendsBiS-sync/manifest.json`` plus ``events/<character>/<device_id>.jsonl``.
A device writes only its own jsonl, via a temp file and then rename.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .model import decode_jsonl, encode_jsonl

SYNC_DIR_NAME = "EQLegendsBiS-sync"
ICLOUD_WAITING = "waiting for iCloud to download"
ICLOUD_TIP = "If this folder is in iCloud Drive, mark it Always keep on this device."

_CLOUD_WORDS = ("cloud file", "placeholder", "icloud", "not downloaded")


class SyncOffline(Exception):
    """The provider cannot be reached. Queued events stay on this PC."""


class WaitingForCloud(Exception):
    """The file is an iCloud placeholder that has not been downloaded."""

    def __init__(self) -> None:
        super().__init__(ICLOUD_WAITING)


class SyncError(Exception):
    """A sync problem the Settings screen can show."""


def character_folder_name(name: str) -> str:
    text = (name or "").strip()
    if not text or len(text) > 80:
        raise ValueError("character is required")
    if "/" in text or "\\" in text or text in {".", ".."} or ".." in text:
        raise ValueError("character is required")
    if any(ord(ch) < 32 for ch in text):
        raise ValueError("character is required")
    return text


def safe_device_file(device_id: str) -> str:
    text = (device_id or "").strip()
    if not text or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", text):
        raise ValueError("device id is not a file name")
    return text


def is_cloud_placeholder(exc: BaseException) -> bool:
    winerror = getattr(exc, "winerror", None)
    if isinstance(winerror, int) and 358 <= winerror <= 410:
        return True
    text = str(exc).lower()
    return any(word in text for word in _CLOUD_WORDS)


def atomic_write(path: Path, text: str) -> None:
    """Write ``path.tmp`` in the same directory, then rename over ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        if is_cloud_placeholder(exc):
            raise WaitingForCloud() from exc
        raise


def is_event_filename(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(".tmp") or lower.endswith(".jsonl.tmp"):
        return False
    if lower.endswith(".jsonl"):
        return True
    return "conflict" in lower


def is_conflicted_name(name: str) -> bool:
    return "conflict" in name.lower()


def sync_root(folder: Path) -> Path:
    return Path(folder) / SYNC_DIR_NAME


def events_dir(folder: Path, character: str) -> Path:
    return sync_root(folder) / "events" / character_folder_name(character)


def own_event_path(folder: Path, character: str, device_id: str) -> Path:
    return events_dir(folder, character) / f"{safe_device_file(device_id)}.jsonl"


def write_events_file(path: Path, events: list[dict[str, Any]]) -> None:
    try:
        atomic_write(path, encode_jsonl(events))
    except OSError as exc:
        if is_cloud_placeholder(exc):
            raise WaitingForCloud() from exc
        raise


def read_events_file(path: Path) -> list[dict[str, Any]]:
    return decode_jsonl(read_text(path))


def write_manifest(folder: Path, manifest: dict[str, Any]) -> None:
    path = sync_root(folder) / "manifest.json"
    atomic_write(path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def read_manifest_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(read_text(path) or "{}")
    except json.JSONDecodeError:
        return {"version": 1, "devices": {}}
    if not isinstance(data, dict):
        return {"version": 1, "devices": {}}
    devices = data.get("devices")
    if not isinstance(devices, dict):
        devices = {}
    return {"version": 1, "devices": devices}


def merge_manifests(parts: list[dict[str, Any]]) -> dict[str, Any]:
    devices: dict[str, Any] = {}
    for part in parts:
        for device_id, row in (part.get("devices") or {}).items():
            current = devices.get(device_id) or {}
            updated = str((row or {}).get("updated") or "")
            if updated >= str(current.get("updated") or ""):
                devices[device_id] = dict(row or {})
    return {"version": 1, "devices": devices}
