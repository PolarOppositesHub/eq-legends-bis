"""Answer /api/health before the full API finishes importing.

Electron's splash only needs ok, the version string, and the instance nonce.
Importing the planner, parser, and catalog stays on a background thread.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

_ready = threading.Event()
_full_app: Any = None
_import_error: str | None = None
_started = False
_lock = threading.Lock()


def _version() -> str:
    from .version import __version__

    return __version__


def _load() -> None:
    global _full_app, _import_error
    try:
        from .main import app as full

        try:
            from .item_catalog import warm_search

            warm_search()
        except Exception:
            pass
        _full_app = full
    except Exception as exc:
        _import_error = f"{type(exc).__name__}: {exc}"
    finally:
        _ready.set()


def _start_load() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_load, name="eq-app-load", daemon=True).start()


async def _send_json(send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": body})


async def _drain(receive) -> None:
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return
        if message["type"] == "http.request" and not message.get("more_body", False):
            return


class BootApp:
    def __init__(self) -> None:
        _start_load()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return
        if scope["type"] != "http":
            return
        if _full_app is not None:
            await _full_app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path == "/api/health":
            await _drain(receive)
            await _send_json(send, 200, {
                "ok": True,
                "version": _version(),
                "instance": os.environ.get("EQ_INSTANCE_NONCE") or "",
                "booting": True,
            })
            return
        if not _ready.wait(60):
            await _drain(receive)
            await _send_json(send, 503, {"ok": False, "error": "starting"})
            return
        if _full_app is not None:
            await _full_app(scope, receive, send)
            return
        await _drain(receive)
        await _send_json(send, 503, {"ok": False, "error": _import_error or "import failed"})


app = BootApp()
