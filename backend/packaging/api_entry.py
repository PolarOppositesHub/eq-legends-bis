#!/usr/bin/env python3
"""Sidecar entry for Electron / PyInstaller.

Usage:
  python api_entry.py --port 8765
  eq-api.exe --port 8765

Sets EQ_PACKAGED=1 and starts uvicorn serving backend.app.main:app
(with static UI when frontend/dist is present).
"""
from __future__ import annotations

import argparse
import copy
import faulthandler
import os
import sys
from pathlib import Path


def _bootstrap_path() -> None:
    """Ensure app root is importable when frozen or run from packaging/."""
    if getattr(sys, "frozen", False):
        # PyInstaller one-folder: modules live in _MEIPASS or next to exe
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        for p in (meipass, exe_dir, exe_dir.parent, exe_dir / "resources"):
            if (p / "backend").exists() or (p / "app").exists():
                sys.path.insert(0, str(p))
                os.environ.setdefault("EQ_APP_ROOT", str(p if (p / "backend").exists() else exe_dir.parent))
                break
        # Vendored legends
        for p in (exe_dir / "eq-legends", exe_dir / "resources" / "eq-legends", meipass / "eq-legends"):
            if (p / "build_planner.py").exists():
                sys.path.insert(0, str(p))
                os.environ.setdefault("EQ_LEGENDS_ROOT", str(p))
                break
    else:
        # .../backend/packaging/api_entry.py -> app root = parents[2]
        app_root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(app_root))
        os.environ.setdefault("EQ_APP_ROOT", str(app_root))
        legends = app_root.parent / "eq-legends"
        if (legends / "build_planner.py").exists():
            sys.path.insert(0, str(legends))
            os.environ.setdefault("EQ_LEGENDS_ROOT", str(legends))


def _log_dir() -> Path | None:
    """<user data>/logs, the same folder Electron uses. None when unknown."""
    root = os.environ.get("EQ_USER_DATA") or os.environ.get("EQ_XLSX_DIR")
    if not root:
        return None
    path = Path(root) / "logs"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path


def _log_config(log_dir: Path | None) -> dict:
    """uvicorn's console logging plus a rotating eq-api.log (access + errors).

    Before 1.1.2 the sidecar only logged to a pipe, so a stuck or failed
    request left no trace on the user's machine.
    """
    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    if log_dir is None:
        return config
    config["formatters"]["file"] = {
        "format": "%(asctime)s.%(msecs)03d %(levelname)s %(name)s %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }
    config["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "file",
        "filename": str(log_dir / "eq-api.log"),
        "maxBytes": 2_000_000,
        "backupCount": 3,
        "encoding": "utf-8",
    }
    for name in ("uvicorn", "uvicorn.access"):
        config["loggers"].setdefault(name, {"level": "INFO"})
        config["loggers"][name].setdefault("handlers", [])
        config["loggers"][name]["handlers"].append("file")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EQ Legends BiS API sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("EQ_API_PORT", "8765")))
    args = parser.parse_args(argv)

    os.environ["EQ_PACKAGED"] = "1"
    _bootstrap_path()

    # Frozen Windows builds often lack system CA certs for urllib HTTPS.
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass

    import uvicorn

    log_dir = _log_dir()
    if log_dir is not None:
        try:
            # Fatal errors and hard crashes still leave every thread's stack behind.
            faulthandler.enable(file=open(log_dir / "eq-api-fault.log", "a", encoding="utf-8"), all_threads=True)
        except OSError:
            pass

    # Import after path bootstrap
    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
        log_config=_log_config(log_dir),
        reload=False,
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
