"""PyInstaller entry: start uvicorn serving backend.app.main:app."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def main() -> None:
    root = _bundle_root()
    resources = root.parent if root.name.lower() == "api" else root
    app_root = resources if (resources / "backend").exists() else (
        resources.parent if (resources.parent / "backend").exists() else resources
    )

    candidates_data = [
        Path(os.environ["EQ_LEGENDS_DATA"]) if os.environ.get("EQ_LEGENDS_DATA") else None,
        resources / "data" / "decoded",
        root / "data" / "decoded",
        app_root / "data" / "decoded",
    ]
    data = next((p for p in candidates_data if p and p.exists()), candidates_data[1])

    vendor = Path(os.environ["EQ_LEGENDS_ROOT"]) if os.environ.get("EQ_LEGENDS_ROOT") else Path()
    if not vendor.exists():
        for c in (resources / "vendor", root / "vendor", app_root / "backend" / "vendor"):
            if (c / "build_planner.py").exists():
                vendor = c
                break

    ui = Path(os.environ["EQ_FRONTEND_DIST"]) if os.environ.get("EQ_FRONTEND_DIST") else Path()
    if not ui.exists():
        for c in (resources / "ui", root / "ui", app_root / "frontend" / "dist"):
            if (c / "index.html").exists():
                ui = c
                break

    os.environ.setdefault("EQ_PACKAGED", "1")
    os.environ.setdefault("EQ_APP_ROOT", str(app_root))
    os.environ["EQ_LEGENDS_DATA"] = str(data)
    if vendor.exists():
        os.environ["EQ_LEGENDS_ROOT"] = str(vendor)
        sys.path.insert(0, str(vendor))
    if ui.exists():
        os.environ["EQ_FRONTEND_DIST"] = str(ui)

    for c in (resources, app_root, root):
        if (c / "backend" / "app" / "main.py").exists():
            sys.path.insert(0, str(c))
            break

    host = os.environ.get("EQ_API_HOST", "127.0.0.1")
    port = int(os.environ.get("EQ_API_PORT", "8765"))

    import uvicorn
    uvicorn.run("backend.app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
