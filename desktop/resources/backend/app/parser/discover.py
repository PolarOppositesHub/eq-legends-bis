"""Find EverQuest Legends combat logs under an install folder."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Default Daybreak install. The app's existing EQ-folder setting overrides this.
DEFAULT_EQ_INSTALL = (
    r"C:\Users\Public\Daybreak Game Company\Installed Games\EverQuest Legends"
)

_LOG_NAME = re.compile(r"^eqlog_(?P<char>.+)_(?P<server>[^_]+)\.txt$", re.IGNORECASE)


def parse_log_name(filename: str) -> tuple[str, str] | None:
    match = _LOG_NAME.match(Path(filename).name)
    if not match:
        return None
    return match.group("char"), match.group("server")


def discover_logs(root: str | Path | None) -> list[dict]:
    """List ``<root>/Logs/eqlog_<char>_<server>.txt``, newest first."""
    if not root:
        return []
    logs_dir = Path(root) / "Logs"
    if not logs_dir.is_dir():
        return []
    found: list[dict] = []
    try:
        entries = list(logs_dir.iterdir())
    except OSError:
        return []
    for path in entries:
        if not path.is_file():
            continue
        parsed = parse_log_name(path.name)
        if not parsed:
            continue
        character, server = parsed
        try:
            st = path.stat()
        except OSError:
            continue
        found.append({
            "path": str(path),
            "name": path.name,
            "character": character,
            "server": server,
            "size": st.st_size,
            "mtime": st.st_mtime,
        })
    found.sort(key=lambda row: row["mtime"], reverse=True)
    return found


def default_user_data() -> Path:
    for key in ("EQ_USER_DATA", "EQ_XLSX_DIR"):
        value = os.environ.get(key)
        if value:
            return Path(value)
    return Path.home() / ".eq-legends-bis"


def read_settings(user_data: Path) -> dict:
    path = Path(user_data) / "settings.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_settings(user_data: Path, patch: dict) -> dict:
    """Merge ``patch`` into settings.json without dropping unrelated keys."""
    path = Path(user_data) / "settings.json"
    current = read_settings(user_data)
    current.update(patch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def read_eq_install(user_data: Path) -> str:
    value = read_settings(user_data).get("eqInstallFolder") or ""
    return str(value).strip()
