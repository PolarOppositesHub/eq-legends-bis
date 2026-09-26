"""Polling tail that never holds the log open between polls.

EverQuest writes the log on a flush interval. Opening, reading, and closing
on each poll avoids a Windows share lock that could block the game. A trailing
partial line stays in memory until a newline arrives. If the file shrinks,
the tail resets to offset 0.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TailLine:
    offset: int
    text: str


@dataclass
class TailBatch:
    lines: list[TailLine] = field(default_factory=list)
    truncated: bool = False


class LogTail:
    def __init__(self, path: str | Path, poll_interval: float = 0.25) -> None:
        self.path = Path(path)
        self.poll_interval = poll_interval
        self.offset = 0
        self.partial = b""

    def start_at_end(self) -> None:
        self.offset = self.path.stat().st_size if self.path.exists() else 0
        self.partial = b""

    def poll(self) -> TailBatch:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        size = self.path.stat().st_size
        truncated = False
        if size < self.offset:
            self.offset = 0
            self.partial = b""
            truncated = True
            size = self.path.stat().st_size
        if size == self.offset and not self.partial:
            return TailBatch(truncated=truncated)

        file_pos = self.offset
        # Open, read, close. Nothing is left open when this block ends.
        with open(self.path, "rb") as handle:
            handle.seek(file_pos)
            data = handle.read()
        buf_start = file_pos - len(self.partial)
        buf = self.partial + data
        self.offset = file_pos + len(data)
        if not buf:
            return TailBatch(truncated=truncated)

        parts = buf.split(b"\n")
        if buf.endswith(b"\n"):
            complete = parts[:-1]
            self.partial = b""
        else:
            complete = parts[:-1]
            self.partial = parts[-1]

        lines: list[TailLine] = []
        cursor = buf_start
        for part in complete:
            lines.append(TailLine(cursor, part.decode("utf-8", errors="replace").rstrip("\r")))
            cursor += len(part) + 1
        return TailBatch(lines=lines, truncated=truncated)


def backfill_offset(path: str | Path, seconds: float) -> int:
    """Byte offset of the first line within ``seconds`` of the file's last timestamp."""
    from .classify import split_log_line

    path = Path(path)
    last_ts = None
    stamped: list[tuple[int, object]] = []
    offset = 0
    with open(path, "rb") as handle:
        for raw in handle:
            _ts, _msg = split_log_line(raw.decode("utf-8", errors="replace"))
            if _ts is not None:
                last_ts = _ts
                stamped.append((offset, _ts))
            offset += len(raw)
    if last_ts is None or not stamped:
        return 0
    cutoff = last_ts.timestamp() - seconds
    for pos, ts in stamped:
        if ts.timestamp() >= cutoff:
            return pos
    return stamped[-1][0]
