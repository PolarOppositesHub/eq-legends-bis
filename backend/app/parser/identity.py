"""Current class trio and level for the log character.

Newest timestamp wins. At the same timestamp, manual override beats an
own-character /who, which beats ``You have gained a level! Welcome to level N!``.
A level line does not name a class. There is no class-change log line.
"""

from __future__ import annotations

from typing import Any

SWAP_NOTE = "Type /who to refresh classes"
REPLACED_NOTE = "A newer /who replaced the class override."

_PRIORITY = {"level": 0, "who": 1, "manual": 2}


def resolve_current(
    observations: list[dict[str, Any]],
    manual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``current`` and older trios in ``history``.

    ``observations`` are own-character rows: evidence ``who`` (classes + level)
    or ``level_line`` (level only). Ability-point rows are ignored.
    """
    rows: list[dict[str, Any]] = []
    for obs in observations or []:
        evidence = obs.get("evidence")
        ts = obs.get("ts") or ""
        if evidence == "who" and obs.get("classes"):
            rows.append({
                "source": "who",
                "ts": ts,
                "classes": str(obs["classes"]),
                "level": _level(obs.get("level")),
            })
        elif evidence == "level_line" and _level(obs.get("level")) is not None:
            rows.append({
                "source": "level",
                "ts": ts,
                "classes": None,
                "level": _level(obs.get("level")),
            })
    if manual and manual.get("ts"):
        rows.append({
            "source": "manual",
            "ts": str(manual["ts"]),
            "classes": manual.get("classes") or None,
            "level": _level(manual.get("level")),
        })
    rows.sort(key=lambda row: (row["ts"], _PRIORITY[row["source"]]))

    current: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []

    def park() -> None:
        if current and current.get("classes"):
            history.append({
                "classes": current["classes"],
                "level": current["level"],
                "ts": current["ts"],
                "source": current["source"],
            })

    for row in rows:
        if row["source"] == "manual":
            if current and current.get("classes") and current["classes"] != row["classes"]:
                park()
            current = _snap(row, note=None, replaced=False)
            continue
        if row["source"] == "who":
            replaced = bool(
                current
                and current["source"] == "manual"
                and row["ts"] > (current["ts"] or "")
            )
            if current and current.get("classes") and current["classes"] != row["classes"]:
                park()
            current = _snap(
                row,
                note=REPLACED_NOTE if replaced else None,
                replaced=replaced,
            )
            continue
        # Level line. A manual override that is still current ignores it.
        if current and current["source"] == "manual" and row["ts"] >= (current["ts"] or ""):
            continue
        if current is None:
            current = _snap(row, note=None, replaced=False)
            continue
        previous = current["level"]
        if previous is not None and row["level"] is not None and row["level"] < previous:
            park()
            current = _snap(row, note=SWAP_NOTE, replaced=False)
            continue
        current = {
            "classes": current.get("classes"),
            "level": row["level"],
            "source": "level",
            "ts": row["ts"],
            "note": current.get("note") if current.get("note") == REPLACED_NOTE else None,
            "replaced_manual": bool(current.get("replaced_manual")),
        }

    if current and current.get("classes"):
        history = [row for row in history if row["classes"] != current["classes"]]
    history.reverse()
    return {"current": current, "history": history}


def _snap(row: dict[str, Any], *, note: str | None, replaced: bool) -> dict[str, Any]:
    return {
        "classes": row.get("classes"),
        "level": row.get("level"),
        "source": row["source"],
        "ts": row["ts"],
        "note": note,
        "replaced_manual": replaced,
    }


def normalize_override(classes: Any, level: Any, tokens: dict[str, str]) -> tuple[str, int]:
    """Three class codes, or two when the level is below 10. Tokens are the catalog map."""
    number = _level(level)
    if number is None or number < 1 or number > 50:
        raise ValueError("level must be from 1 to 50")
    if isinstance(classes, str):
        parts = [part.strip().upper() for part in classes.split("/") if part.strip()]
    elif isinstance(classes, (list, tuple)):
        parts = [str(part).strip().upper() for part in classes if str(part).strip()]
    else:
        parts = []
    need = 2 if number < 10 else 3
    if len(parts) != need:
        raise ValueError(f"pick {need} classes")
    if len(set(parts)) != len(parts):
        raise ValueError("classes must be different")
    unknown = [part for part in parts if part not in tokens]
    if unknown:
        raise ValueError("unknown class")
    return "/".join(parts), number


def _level(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
