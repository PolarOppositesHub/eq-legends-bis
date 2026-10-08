"""Per-character currency ledger for motes, Wind Runes, and Void-Touched.

Counts are a ledger sum. Item XP values are the SPEC §8.1 table
(eqlwiki Mote_Guide and Item_Upgrade_System). No mote id, log line, or
formula is invented. The condense log line is UNVERIFIED (SPEC §5.3) and
is not parsed. A merge line does not name the mote, so it never decrements
a count.

Void-Touched spending is not planned here. SPEC §9.3 puts Void-Touched on
the highest-tier gap first; this ledger does not reorder or replace that.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .inventory import MOTE_GRADES, VOID_TOUCHED_NAME, WIND_RUNE_NAMES

# Item XP, spell XP, and the tier the mote can still be used on.
# SPEC §8.1. Rank 4 is "Mote of Potential", not "Mote of Potential Potential".
_MOTE_META: dict[str, dict[str, Any]] = {
    "Mote of Infinitesimal Potential": {"item_xp": 1, "spell_xp": 1, "usable_on": "+0"},
    "Mote of Minor Potential": {"item_xp": 1, "spell_xp": 2, "usable_on": "≤ +1"},
    "Mote of Lesser Potential": {"item_xp": 2, "spell_xp": 4, "usable_on": "≤ +2"},
    "Mote of Potential": {"item_xp": 4, "spell_xp": 8, "usable_on": "≤ +3"},
    "Mote of Major Potential": {"item_xp": 5, "spell_xp": 16, "usable_on": "≤ +4"},
    "Mote of Greater Potential": {"item_xp": 6, "spell_xp": 32, "usable_on": "≤ +5"},
    "Mote of Superior Potential": {"item_xp": 7, "spell_xp": 64, "usable_on": "≤ +6"},
    "Mote of Grand Potential": {"item_xp": 8, "spell_xp": 128, "usable_on": "≤ +7"},
    "Mote of Ascendant Potential": {"item_xp": 9, "spell_xp": 256, "usable_on": "≤ +8"},
    "Mote of Infinite Potential": {"item_xp": 10, "spell_xp": 512, "usable_on": "≤ +9"},
}

# Grand → Ascendant is the last step the wiki marks "Needs Confirmed".
# eqltools says "up to Ascendant". Ascendant → Infinite is not offered.
_CONDENSE_MAX_GRADE = 8
_VOID_CAP = 3
_PT = ZoneInfo("America/Los_Angeles")
_CT = ZoneInfo("America/Chicago")

_GRADE_BY_NAME = {name: grade for grade, name in MOTE_GRADES}
_NAME_BY_GRADE = {grade: name for grade, name in MOTE_GRADES}
_ADD_MODES = {"bag", "stored_currency", "stored_depot", "stored_hoard", "given"}
_STORAGE_SOURCES = {"manual", "log_loot", "log_given", "log_offer"}

CURRENCY_SHEET_HEADERS = (
    "Currency",
    "Kind",
    "Rank",
    "Item XP",
    "Spell XP",
    "Usable on items currently at",
    "Bags",
    "Currency storage",
    "Total",
)


def all_currency_names() -> list[str]:
    names = [name for _grade, name in MOTE_GRADES]
    names.append(VOID_TOUCHED_NAME)
    names.extend(WIND_RUNE_NAMES)
    return names


def currency_kind(name: str) -> str | None:
    if name in _GRADE_BY_NAME:
        return "mote"
    if name == VOID_TOUCHED_NAME:
        return "void_touched"
    if name in WIND_RUNE_NAMES:
        return "wind_rune"
    return None


def currency_sheet_rows() -> list[dict[str, Any]]:
    """Reference rows for the XLSX Currencies sheet. Counts are blank."""
    rows: list[dict[str, Any]] = []
    for grade, name in MOTE_GRADES:
        meta = _MOTE_META[name]
        rows.append({
            "Currency": name,
            "Kind": "mote",
            "Rank": grade,
            "Item XP": meta["item_xp"],
            "Spell XP": meta["spell_xp"],
            "Usable on items currently at": meta["usable_on"],
            "Bags": None,
            "Currency storage": None,
            "Total": None,
        })
    rows.append({
        "Currency": VOID_TOUCHED_NAME,
        "Kind": "void_touched",
        "Rank": None,
        "Item XP": None,
        "Spell XP": None,
        "Usable on items currently at": None,
        "Bags": None,
        "Currency storage": None,
        "Total": None,
    })
    for name in WIND_RUNE_NAMES:
        rows.append({
            "Currency": name,
            "Kind": "wind_rune",
            "Rank": None,
            "Item XP": None,
            "Spell XP": None,
            "Usable on items currently at": None,
            "Bags": None,
            "Currency storage": None,
            "Total": None,
        })
    return rows


def condense_preview(grade: int) -> dict[str, Any] | None:
    """2 of this grade → 1 of the next. None when the step is not offered.

    Minor → Lesser and Lesser → Potential keep item XP (the next grade's
    item XP is double). Every other offered step loses item XP.
    """
    if grade < 1 or grade > _CONDENSE_MAX_GRADE:
        return None
    src = _NAME_BY_GRADE[grade]
    dst = _NAME_BY_GRADE[grade + 1]
    src_xp = int(_MOTE_META[src]["item_xp"])
    dst_xp = int(_MOTE_META[dst]["item_xp"])
    before = src_xp * 2
    loss = before - dst_xp
    doubles = loss == 0 and dst_xp == src_xp * 2
    warning = None
    note = f"2 × {src} ({src_xp} item XP) becomes 1 × {dst} ({dst_xp} item XP)."
    if loss > 0:
        warning = f"This loses {loss} item XP (2 × {src_xp} → {dst_xp})."
    if grade == _CONDENSE_MAX_GRADE:
        note = f"{note} eqlwiki marks Grand → Ascendant as Needs Confirmed."
    return {
        "offered": True,
        "from": src,
        "to": dst,
        "from_grade": grade,
        "item_xp_before": before,
        "item_xp_after": dst_xp,
        "item_xp_loss": loss,
        "doubles": doubles,
        "warning": warning,
        "note": note,
        "needs_confirmed": grade == _CONDENSE_MAX_GRADE,
    }


def weekly_reset(now: datetime) -> dict[str, Any]:
    """Next and previous Tuesday 08:00 America/Los_Angeles, labeled in Central time.

    ``now`` may be any aware datetime. The reset instant is 8:00 in Pacific
    local time, so PDT and PST both land on Tuesday 08:00, not a fixed UTC offset.
    """
    if now.tzinfo is None:
        raise ValueError("weekly_reset requires an aware datetime")
    pt = now.astimezone(_PT)
    days_since_tue = (pt.weekday() - 1) % 7
    candidate = (pt - timedelta(days=days_since_tue)).replace(
        hour=8, minute=0, second=0, microsecond=0,
    )
    if pt < candidate:
        last_reset = candidate - timedelta(days=7)
        nxt = candidate
    else:
        last_reset = candidate
        nxt = candidate + timedelta(days=7)
    return {
        "last_reset": last_reset,
        "next_reset": nxt,
        "countdown_label": _countdown_label(now, nxt),
        "ct_clock": _ct_clock(nxt),
    }


def _ct_clock(instant: datetime) -> str:
    ct = instant.astimezone(_CT)
    hour = ct.hour % 12 or 12
    ampm = "AM" if ct.hour < 12 else "PM"
    return f"{ct.strftime('%A')} {hour}:{ct.minute:02d} {ampm} CT"


def _countdown_label(now: datetime, nxt: datetime) -> str:
    seconds = int((nxt - now).total_seconds())
    if seconds < 0:
        seconds = 0
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        left = f"{days}d {hours}h {minutes}m"
    elif hours:
        left = f"{hours}h {minutes}m"
    else:
        left = f"{minutes}m"
    return f"{left} · resets {_ct_clock(nxt)}"


def _stamp(moment: datetime | None = None) -> str:
    moment = moment or datetime.now()
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_stamp(text: str | None) -> datetime | None:
    if not text or not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


class CurrencyBook:
    """JSON ledger under the sidecar user-data directory, one object per character."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"version": 1, "characters": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "characters": {}}
        if not isinstance(raw, dict) or not isinstance(raw.get("characters"), dict):
            return {"version": 1, "characters": {}}
        raw["version"] = 1
        return raw

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def _blank(self) -> dict[str, Any]:
        return {
            "entries": [],
            "bag_import": {},
            "bag_import_at": None,
            "ack_merges": [],
            "merges": [],
            "next_seq": 1,
        }

    def _resolve(self, character: str, *, create: bool) -> tuple[str, dict[str, Any]]:
        name = (character or "").strip()
        if not name or len(name) > 80:
            raise ValueError("character is required")
        chars: dict[str, Any] = self._data["characters"]
        for key, state in chars.items():
            if key.casefold() == name.casefold():
                return key, state
        if not create:
            raise ValueError("character is required")
        state = self._blank()
        chars[name] = state
        return name, state

    def _entry(
        self,
        state: dict[str, Any],
        *,
        currency: str,
        delta: int,
        source: str,
        ts: str,
        evidence: str,
        anchor: bool = False,
        count: int | None = None,
        autosold: bool = False,
        event_key: str | None = None,
        group: str | None = None,
        bags_before: int | None = None,
        bags_after: int | None = None,
    ) -> dict[str, Any]:
        seq = int(state.get("next_seq") or 1)
        state["next_seq"] = seq + 1
        entry = {
            "id": uuid.uuid4().hex,
            "seq": seq,
            "ts": ts,
            "currency": currency,
            "delta": int(delta),
            "source": source,
            "evidence": evidence,
            "anchor": bool(anchor),
            "count": int(count) if count is not None else None,
            "autosold": bool(autosold),
            "event_key": event_key,
            "group": group,
            "reverted": False,
            "bags_before": bags_before,
            "bags_after": bags_after,
        }
        state["entries"].append(entry)
        return entry

    def _keys(self, state: dict[str, Any]) -> set[str]:
        return {e["event_key"] for e in state["entries"] if e.get("event_key")}

    def _anchor(self, state: dict[str, Any], currency: str) -> dict[str, Any] | None:
        anchors = [
            e for e in state["entries"]
            if e["currency"] == currency and e.get("anchor") and not e.get("reverted")
        ]
        if not anchors:
            return None
        return max(anchors, key=lambda e: (e["ts"], e["seq"]))

    def storage_count(self, state: dict[str, Any], currency: str) -> int:
        anchor = self._anchor(state, currency)
        if anchor is None:
            return 0
        total = int(anchor.get("count") or 0)
        for entry in state["entries"]:
            if entry.get("reverted") or entry["currency"] != currency:
                continue
            if entry["id"] == anchor["id"] or entry.get("anchor"):
                continue
            if entry["source"] == "inventory_reconcile" or entry.get("autosold"):
                continue
            if entry["source"] not in _STORAGE_SOURCES:
                continue
            if entry["ts"] < anchor["ts"]:
                continue
            if entry["ts"] == anchor["ts"] and entry["seq"] <= anchor["seq"]:
                continue
            total += int(entry["delta"])
        return total

    def bag_count(self, state: dict[str, Any], currency: str) -> int:
        try:
            return int(state.get("bag_import", {}).get(currency) or 0)
        except (TypeError, ValueError):
            return 0

    def set_anchor(self, character: str, currency: str, count: int, ts: str | None = None) -> dict[str, Any]:
        if currency_kind(currency) is None:
            raise ValueError("unknown currency")
        try:
            amount = int(count)
        except (TypeError, ValueError) as exc:
            raise ValueError("count must be a whole number") from exc
        if amount < 0:
            raise ValueError("count must be zero or more")
        stamp = ts or _stamp()
        if _parse_stamp(stamp) is None:
            raise ValueError("timestamp must be YYYY-MM-DDTHH:MM:SS")
        with self._lock:
            _key, state = self._resolve(character, create=True)
            entry = self._entry(
                state,
                currency=currency,
                delta=amount,
                source="manual",
                ts=stamp,
                evidence=f"Set currency storage to {amount}",
                anchor=True,
                count=amount,
            )
            self._save()
            return self._public_entry(entry)

    def sync(self, character: str, events: list[dict[str, Any]]) -> None:
        """Apply loot, given, and offer lines. Merge lines only feed the pending chip."""
        with self._lock:
            _key, state = self._resolve(character, create=True)
            merges: list[dict[str, Any]] = []
            seen: set[str] = set()
            for event in events or []:
                if not isinstance(event, dict):
                    continue
                if event.get("kind") == "merge":
                    key = str(event.get("key") or "")
                    if key and key not in seen:
                        seen.add(key)
                        merges.append({
                            "key": key,
                            "ts": event.get("ts"),
                            "result_item": event.get("result_item") or event.get("item"),
                        })
                    continue
                self._apply_log(state, event)
            state["merges"] = merges
            self._save()

    def _apply_log(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        kind = event.get("kind")
        if kind in {None, "merge", "mote_reject"}:
            return
        key = str(event.get("key") or "")
        if not key or key in self._keys(state):
            return
        mode = event.get("mode")
        item = (event.get("item") or "").strip()
        if currency_kind(item) is None:
            return
        stamp = event.get("ts")
        if _parse_stamp(stamp if isinstance(stamp, str) else None) is None:
            return
        anchor = self._anchor(state, item)
        if anchor is None or stamp < anchor["ts"]:
            return
        qty = event.get("qty")
        try:
            amount = int(qty if qty is not None else 1)
        except (TypeError, ValueError):
            return
        if amount < 0:
            return
        npc = (event.get("npc") or "").strip()
        if kind == "give":
            self._entry(
                state,
                currency=item,
                delta=-amount,
                source="log_offer",
                ts=stamp,
                evidence=f"You offered {amount} {item} to {npc}".rstrip(),
                event_key=key,
            )
            return
        if kind != "loot":
            return
        if mode == "autosold":
            self._entry(
                state,
                currency=item,
                delta=0,
                source="log_loot",
                ts=stamp,
                evidence="auto-sold, not kept",
                autosold=True,
                event_key=key,
            )
            return
        if mode == "given":
            self._entry(
                state,
                currency=item,
                delta=amount,
                source="log_given",
                ts=stamp,
                evidence=f"You have been given: {item}",
                event_key=key,
            )
            return
        if mode in _ADD_MODES:
            where = {
                "bag": "looted",
                "stored_currency": "stored in currency",
                "stored_depot": "stored in tradeskill depot",
                "stored_hoard": "stored in Dragon Hoard",
            }[mode]
            self._entry(
                state,
                currency=item,
                delta=amount,
                source="log_loot",
                ts=stamp,
                evidence=f"{where}: {amount} {item}",
                event_key=key,
            )

    def use(self, character: str, currency: str, qty: int, ts: str | None = None) -> dict[str, Any]:
        """Record 'I used: [grade] x [n]' and clear the pending-merge chip."""
        if currency_kind(currency) is None:
            raise ValueError("unknown currency")
        try:
            amount = int(qty)
        except (TypeError, ValueError) as exc:
            raise ValueError("count must be a whole number") from exc
        if amount < 0:
            raise ValueError("count must be zero or more")
        stamp = ts or _stamp()
        if _parse_stamp(stamp) is None:
            raise ValueError("timestamp must be YYYY-MM-DDTHH:MM:SS")
        with self._lock:
            _key, state = self._resolve(character, create=True)
            entry = None
            if amount:
                if self._anchor(state, currency) is None:
                    raise ValueError("Set a currency storage count first.")
                held = self.storage_count(state, currency)
                if amount > held:
                    raise ValueError(f"Currency storage has {held}.")
                entry = self._entry(
                    state,
                    currency=currency,
                    delta=-amount,
                    source="manual",
                    ts=stamp,
                    evidence=f"I used {currency} x {amount}",
                )
            acked = set(state.get("ack_merges") or [])
            acked.update(m["key"] for m in state.get("merges") or [] if m.get("key"))
            state["ack_merges"] = sorted(acked)
            self._save()
            return self._public_entry(entry) if entry else {"acked": True}

    def condense(self, character: str, currency: str, ts: str | None = None) -> dict[str, Any]:
        grade = _GRADE_BY_NAME.get(currency)
        preview = condense_preview(grade or 0)
        if preview is None:
            raise ValueError("Condense is offered up to Grand → Ascendant only.")
        stamp = ts or _stamp()
        if _parse_stamp(stamp) is None:
            raise ValueError("timestamp must be YYYY-MM-DDTHH:MM:SS")
        with self._lock:
            _key, state = self._resolve(character, create=True)
            if self._anchor(state, currency) is None:
                raise ValueError("Set a currency storage count first.")
            held = self.storage_count(state, currency)
            if held < 2:
                raise ValueError(f"Currency storage has {held}. Condense needs 2.")
            group = uuid.uuid4().hex
            warning = preview["warning"] or preview["note"]
            self._entry(
                state,
                currency=currency,
                delta=-2,
                source="manual",
                ts=stamp,
                evidence=f"Condense 2 × {currency}. {warning}",
                group=group,
            )
            target = preview["to"]
            if self._anchor(state, target) is None:
                self._entry(
                    state,
                    currency=target,
                    delta=0,
                    source="manual",
                    ts=stamp,
                    evidence=f"Set currency storage to 0",
                    anchor=True,
                    count=0,
                    group=group,
                )
            self._entry(
                state,
                currency=target,
                delta=1,
                source="manual",
                ts=stamp,
                evidence=f"Condense into 1 × {target}. {warning}",
                group=group,
            )
            self._save()
            return preview

    def undo(self, character: str, entry_id: str) -> dict[str, Any]:
        with self._lock:
            _key, state = self._resolve(character, create=False)
            match = next((e for e in state["entries"] if e["id"] == entry_id), None)
            if match is None:
                raise ValueError("ledger entry not found")
            group = match.get("group")
            targets = [
                e for e in state["entries"]
                if e["id"] == entry_id or (group and e.get("group") == group)
            ]
            for entry in targets:
                if entry.get("reverted"):
                    continue
                entry["reverted"] = True
                if entry["source"] == "inventory_reconcile" and entry.get("bags_before") is not None:
                    state["bag_import"][entry["currency"]] = int(entry["bags_before"])
            self._save()
            return {"ok": True, "reverted": [e["id"] for e in targets]}

    def reconcile(
        self,
        character: str,
        bag_counts: dict[str, Any],
        imported_at: str | None = None,
    ) -> list[dict[str, Any]]:
        """Set bag counts from an inventory import. An unexplained drop is a ledger entry."""
        stamp = imported_at or _stamp()
        if _parse_stamp(stamp) is None:
            raise ValueError("timestamp must be YYYY-MM-DDTHH:MM:SS")
        observed = {name: 0 for name in all_currency_names()}
        for name, raw in (bag_counts or {}).items():
            if name not in observed:
                continue
            try:
                observed[name] = max(0, int(raw))
            except (TypeError, ValueError):
                continue
        created: list[dict[str, Any]] = []
        with self._lock:
            _key, state = self._resolve(character, create=True)
            previous_at = state.get("bag_import_at")
            for name, new in observed.items():
                old = self.bag_count(state, name)
                drop = old - new
                if drop > 0:
                    explained = self._explained_drop(state, name, previous_at, stamp)
                    unexplained = drop - explained
                    if unexplained > 0:
                        entry = self._entry(
                            state,
                            currency=name,
                            delta=-unexplained,
                            source="inventory_reconcile",
                            ts=stamp,
                            evidence=(
                                f"Bag count dropped from {old} to {new} with no matching ledger entry "
                                f"for {unexplained}. Bags (from import) + Currency storage = Total. "
                                "This reconcile can be undone."
                            ),
                            bags_before=old,
                            bags_after=new,
                        )
                        created.append(self._public_entry(entry))
                state["bag_import"][name] = new
            state["bag_import_at"] = stamp
            self._save()
        return created

    def _explained_drop(
        self,
        state: dict[str, Any],
        currency: str,
        since: str | None,
        until: str,
    ) -> int:
        anchor = self._anchor(state, currency)
        total = 0
        for entry in state["entries"]:
            if entry.get("reverted") or entry["currency"] != currency:
                continue
            if entry["source"] not in {"manual", "log_offer"}:
                continue
            if int(entry["delta"]) >= 0 or entry.get("anchor"):
                continue
            if since and entry["ts"] <= since:
                continue
            if entry["ts"] > until:
                continue
            if anchor is not None:
                if entry["ts"] < anchor["ts"]:
                    continue
                if entry["ts"] == anchor["ts"] and entry["seq"] <= anchor["seq"]:
                    continue
            total += -int(entry["delta"])
        return total

    def view(
        self,
        character: str,
        *,
        now: datetime | None = None,
        event_zone: ZoneInfo | None = None,
        warning: str | None = None,
    ) -> dict[str, Any]:
        moment = now or datetime.now().astimezone()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.now().astimezone().tzinfo)
        zone = event_zone or moment.tzinfo
        reset = weekly_reset(moment)
        with self._lock:
            try:
                key, state = self._resolve(character, create=False)
            except ValueError:
                key, state = (character or "").strip(), self._blank()
            currencies = [self._currency_view(state, name, reset, zone) for name in all_currency_names()]
            acked = set(state.get("ack_merges") or [])
            pending = [m for m in state.get("merges") or [] if m.get("key") not in acked]
            ledger = {}
            for entry in state["entries"]:
                ledger.setdefault(entry["currency"], []).append(self._public_entry(entry))
            for rows in ledger.values():
                rows.sort(key=lambda row: (row["ts"], row["seq"]), reverse=True)
        motes = [row for row in currencies if row["kind"] == "mote"]
        void_row = next(row for row in currencies if row["kind"] == "void_touched")
        runes = [row for row in currencies if row["kind"] == "wind_rune"]
        n = len(pending)
        return {
            "character": key,
            "warning": warning,
            "pending_merges": n,
            "pending_label": f"Pending: {n} merge{'s' if n != 1 else ''} since last check",
            "reset": {
                "countdown_label": reset["countdown_label"],
                "ct_clock": reset["ct_clock"],
                "next_reset_pt": reset["next_reset"].isoformat(),
                "next_reset_ct": reset["next_reset"].astimezone(_CT).isoformat(),
                "last_reset_pt": reset["last_reset"].isoformat(),
            },
            "motes": motes,
            "void_touched": void_row,
            "wind_runes": runes,
            "ledger": ledger,
            "rule": "Bags (from import) + Currency storage = Total.",
        }

    def _currency_view(
        self,
        state: dict[str, Any],
        name: str,
        reset: dict[str, Any],
        zone: Any,
    ) -> dict[str, Any]:
        bags = self.bag_count(state, name)
        storage = self.storage_count(state, name)
        total = bags + storage
        kind = currency_kind(name)
        grade = _GRADE_BY_NAME.get(name)
        meta = _MOTE_META.get(name) or {}
        item_xp = meta.get("item_xp")
        anchor = self._anchor(state, name)
        autosold = any(
            e["currency"] == name and e.get("autosold") and not e.get("reverted")
            and anchor is not None and e["ts"] >= anchor["ts"]
            for e in state["entries"]
        )
        row: dict[str, Any] = {
            "name": name,
            "kind": kind,
            "grade": grade,
            "item_xp": item_xp,
            "spell_xp": meta.get("spell_xp"),
            "usable_on": meta.get("usable_on"),
            "bags": bags,
            "storage": storage,
            "total": total,
            "total_item_xp": (total * int(item_xp)) if item_xp is not None else None,
            "anchored": anchor is not None,
            "autosold": autosold,
            "autosold_note": "auto-sold, not kept" if autosold else None,
            "need": None,
        }
        if kind == "mote" and grade is not None:
            row["condense"] = condense_preview(grade)
        if kind == "void_touched":
            earned = self._earned_since(state, name, reset["last_reset"], zone)
            row["held"] = total
            row["held_label"] = f"{total}/{_VOID_CAP}"
            row["earned_this_week"] = earned
            row["earned_label"] = f"{earned}/{_VOID_CAP}"
            row["cap"] = _VOID_CAP
            row["countdown_label"] = reset["countdown_label"]
        return row

    def _earned_since(self, state: dict[str, Any], currency: str, start: datetime, zone: Any) -> int:
        anchor = self._anchor(state, currency)
        total = 0
        for entry in state["entries"]:
            if entry.get("reverted") or entry["currency"] != currency:
                continue
            if entry["source"] not in {"log_loot", "log_given"} or entry.get("autosold"):
                continue
            if int(entry["delta"]) <= 0:
                continue
            if anchor is not None and entry["ts"] < anchor["ts"]:
                continue
            parsed = _parse_stamp(entry["ts"])
            if parsed is None:
                continue
            aware = parsed.replace(tzinfo=zone)
            if aware >= start:
                total += int(entry["delta"])
        return total

    def _public_entry(self, entry: dict[str, Any] | None) -> dict[str, Any]:
        if entry is None:
            return {}
        return {
            "id": entry["id"],
            "seq": entry["seq"],
            "ts": entry["ts"],
            "currency": entry["currency"],
            "delta": entry["delta"],
            "source": entry["source"],
            "evidence": entry["evidence"],
            "anchor": bool(entry.get("anchor")),
            "autosold": bool(entry.get("autosold")),
            "reverted": bool(entry.get("reverted")),
            "group": entry.get("group"),
        }


_book: CurrencyBook | None = None
_book_lock = threading.Lock()


def get_book() -> CurrencyBook:
    global _book
    if _book is None:
        with _book_lock:
            if _book is None:
                override = os.environ.get("EQ_CURRENCIES_PATH")
                if override:
                    path = Path(override)
                else:
                    from .parser.discover import default_user_data
                    path = default_user_data() / "currencies.json"
                _book = CurrencyBook(path)
    return _book


def reset_book(book: CurrencyBook | None = None) -> None:
    global _book
    _book = book
