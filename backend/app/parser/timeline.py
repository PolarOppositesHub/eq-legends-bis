"""Per-second damage buckets for one fight, re-read from the log byte range.

The database stores aggregates, not a curve. This walks the fight's lines with
the same classifier the ingest path uses and buckets amounts by timestamp.
A missing log file yields an empty curve. It does not invent seconds.
"""

from __future__ import annotations

from datetime import datetime

from .breakdown import ability_name
from .classify import classify_log_line
from .sources import canonical_name

_DAMAGE = {"melee", "spell", "dot", "ds"}
_MAX_BINS = 720


def _parse_iso(text: str | None) -> datetime | None:
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(raw[:26], fmt)
        except ValueError:
            continue
    return None


def choose_bin(span_seconds: float) -> int:
    """Widen the bin so a long fight stays a few hundred points."""
    span = max(0.0, float(span_seconds or 0))
    bin_seconds = 1
    if span > 900:
        bin_seconds = 5
    if span > 3600:
        bin_seconds = 30
    while bin_seconds < 120 and span / bin_seconds > _MAX_BINS:
        bin_seconds *= 2
    return bin_seconds


def _empty(t: int) -> dict:
    return {
        "t": t,
        "you": 0,
        "pets": 0,
        "group": 0,
        "other": 0,
        "incoming": 0,
        "incoming_group": 0,
        "heals": 0,
    }


def _series_for(name: str | None, character: str, kinds: dict[str, str]) -> str | None:
    if not name:
        return None
    if name.lower() == character.lower():
        return "you"
    kind = kinds.get(name.lower())
    if kind == "self":
        return "you"
    if kind == "pet":
        return "pets"
    if kind == "group":
        return "group"
    if kind == "other":
        return "other"
    return None


def _label(event) -> str | None:
    if event.kind in _DAMAGE or event.kind == "miss":
        return ability_name(event.kind, event.verb, event.spell)
    if event.kind == "heal":
        spell = (event.spell or "").strip()
        return spell or "(unknown spell)"
    return None


def build_timeline(
    lines: list,
    *,
    character: str,
    sources: list[dict],
    start_ts: str | None,
    duration_seconds: float | None = None,
    ability: str | None = None,
) -> dict:
    """Bucket classified damage and heals.

    ``you`` / ``pets`` / ``group`` / ``other`` are outgoing damage.
    ``incoming`` is damage taken by you and your pets.
    ``incoming_group`` is damage taken by group members.
    ``heals`` is actual healing (not the parenthetical full amount).
    Self-damage stays out of every series. It is already on the tanking tab.
    """
    kinds: dict[str, str] = {}
    for row in sources or []:
        name = row.get("source")
        if not isinstance(name, str) or not name.strip():
            continue
        kind = row.get("kind") or row.get("source_kind") or "unknown"
        kinds[name.strip().lower()] = kind
    if character:
        kinds.setdefault(character.strip().lower(), "self")

    needle = ability.strip().lower() if isinstance(ability, str) and ability.strip() else None
    start = _parse_iso(start_ts)
    stamped: list[tuple[datetime, object]] = []
    for line in lines or []:
        text = line.get("text") if isinstance(line, dict) else str(line)
        ts, event = classify_log_line(text)
        if event is None:
            continue
        when = ts or getattr(event, "ts", None)
        if when is None:
            continue
        stamped.append((when, event))
    if start is None and stamped:
        start = min(when for when, _event in stamped)

    span = float(duration_seconds or 0)
    if start is not None and stamped:
        last = max(when for when, _event in stamped)
        span = max(span, (last - start).total_seconds())
    bin_seconds = choose_bin(span)

    raw: dict[int, dict] = {}

    def slot(when: datetime) -> dict | None:
        if start is None:
            return None
        delta = (when - start).total_seconds()
        if delta < 0:
            return None
        key = int(delta // bin_seconds) * bin_seconds
        row = raw.get(key)
        if row is None:
            row = _empty(key)
            raw[key] = row
        return row

    for when, event in stamped:
        label = _label(event)
        if needle is not None and (label or "").lower() != needle:
            continue
        amount = int(event.amount or 0)
        if event.kind == "heal":
            if not amount:
                continue
            row = slot(when)
            if row is not None:
                row["heals"] += amount
            continue
        if event.kind not in _DAMAGE or not amount:
            continue
        source = canonical_name(event.source, character) if event.source else None
        target = canonical_name(event.target, character) if event.target else None
        row = slot(when)
        if row is None:
            continue
        outgoing = _series_for(source, character, kinds)
        if outgoing:
            row[outgoing] += amount
        incoming = _series_for(target, character, kinds)
        if incoming in {"you", "pets"}:
            row["incoming"] += amount
        elif incoming == "group":
            row["incoming_group"] += amount

    buckets: list[dict] = []
    if raw:
        last_key = max(raw)
        t = 0
        while t <= last_key:
            buckets.append(raw.get(t) or _empty(t))
            t += bin_seconds
            if len(buckets) > _MAX_BINS + 5:
                break

    return {
        "bin_seconds": bin_seconds,
        "buckets": buckets,
        "ability": ability.strip() if needle else None,
    }
