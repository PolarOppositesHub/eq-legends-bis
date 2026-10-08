"""Parse EQ Legends Inventory.txt (/outputfile inventory) TSV.

Table 1 is Location/Name/ID/Count/Slots. Table 2 is KeyRing/Name/ID.
Header rows are recognised by those column names anywhere in the file.
A location splits only on a trailing -SlotN suffix, so Personal-Depot1
stays one token. Children attach to the most recent parent row.
"""
from __future__ import annotations

import re
from typing import Any

from . import engine
from . import item_catalog as item_catalog_mod
from . import quest_guides
from . import scoring as sc
from . import zones as zones_mod

# Inventory Location → planner slot(s). Multi-slot locations consume in order.
LOCATION_TO_SLOTS: dict[str, list[str]] = {
    "HEAD": ["HEAD"],
    "FACE": ["FACE"],
    "EAR": ["EAR1", "EAR2"],
    "NECK": ["NECK"],
    "SHOULDERS": ["SHOULDERS"],
    "ARMS": ["ARMS"],
    "WRIST": ["WRIST1", "WRIST2"],
    "HANDS": ["HANDS"],
    "CHEST": ["CHEST"],
    "BACK": ["BACK"],
    "WAIST": ["WAIST"],
    "LEGS": ["LEGS"],
    "FEET": ["FEET"],
    "FINGERS": ["FINGER1", "FINGER2"],
    "FINGER": ["FINGER1", "FINGER2"],
    "PRIMARY": ["PRIMARY"],
    "SECONDARY": ["SECONDARY"],
    "RANGE": ["RANGE"],
    "RANGED": ["RANGE"],
    "AMMO": ["AMMO"],
    # EQ Legends has two worn "Any Slot" locations (Inventory.txt: Any Slot).
    "ANY SLOT": ["ANY1", "ANY2"],
    "ANY": ["ANY1", "ANY2"],
    "CHARM": ["ANY1", "ANY2"],
}

# Worn location tokens observed in Inventory.txt dumps (SPEC §4.1).
# Planner mapping still goes through LOCATION_TO_SLOTS, which also keeps
# the older aliases (FINGER, RANGED, ANY, CHARM).
_OBSERVED_WORN = {
    "ANY SLOT", "AMMO", "ARMS", "BACK", "CHEST", "EAR", "FACE", "FEET",
    "FINGERS", "HANDS", "HEAD", "HELD", "LEGS", "NECK", "PRIMARY", "RANGE",
    "SECONDARY", "SHOULDERS", "WAIST", "WRIST",
}

# Exact eqlwiki mote names (SPEC §8.1). Match the name only — item IDs seen
# in dumps are not a key. Void-Touched 148600 is unverified (SPEC §14).
MOTE_GRADES: tuple[tuple[int, str], ...] = (
    (1, "Mote of Infinitesimal Potential"),
    (2, "Mote of Minor Potential"),
    (3, "Mote of Lesser Potential"),
    (4, "Mote of Potential"),
    (5, "Mote of Major Potential"),
    (6, "Mote of Greater Potential"),
    (7, "Mote of Superior Potential"),
    (8, "Mote of Grand Potential"),
    (9, "Mote of Ascendant Potential"),
    (10, "Mote of Infinite Potential"),
)
_MOTE_GRADE_BY_NAME = {name: grade for grade, name in MOTE_GRADES}
VOID_TOUCHED_NAME = "Void-Touched Potential"
WIND_RUNE_NAMES: tuple[str, ...] = tuple(
    f"Wind Rune {suffix}"
    for suffix in (
        "Azia", "Beza", "Caza", "Dena", "Ena", "Fana", "Geza", "Heda",
        "Izah", "Jaka", "Kala", "Lena", "Meda", "Neza", "Ozah",
    )
)
_WIND_RUNE_NAMES = set(WIND_RUNE_NAMES)

# Table 2 ring values observed in dumps. Anything else stays unknown_rows.
_KNOWN_RINGS = {"equipment", "augmentation", "activated"}

# Slot7–10 labels are inferred and unconfirmed (SPEC §4.1). The "?" stays
# until those roles are checked in game. Slot1 and Slot2 have no role name.
EXALTATION_SOCKET_LABELS = {
    7: "Slot7 (Focus?)",
    8: "Slot8 (Click?)",
    9: "Slot9 (Worn?)",
    10: "Slot10 (Proc?)",
}

_TRAILING_SLOTS = re.compile(r"(?i)(?:-Slot\d+)+$")
_SLOT_NUMBER = re.compile(r"(?i)-Slot(\d+)")
_LAST_SLOT = re.compile(r"(?i)-Slot\d+$")
_GENERAL_TOKEN = re.compile(r"(?i)^general \d+$")
_INT_TOKEN = re.compile(r"^-?\d+$")
# Real /outputfile inventory rows are "Hoard N", not a Dragon Hoard header.
_HOARD_TOKEN = re.compile(r"(?i)^hoard \d+$")
_EXALTATION_NAME = re.compile(r"(?i)\(Exaltation\)\s*$")
# Bags and boxes are containers. Match the words the inventory uses for them.
_CONTAINER_NAME = re.compile(r"(?i)\b(?:bags?|boxes|box|satchels?|backpacks?|pouches|pouch)\b")


def _parse_item_name(name: str) -> tuple[str, int | None, bool]:
    """Split a trailing '*' flag and a trailing +N tier. Neither is invented."""
    n = (name or "").strip()
    flag_star = False
    if n.endswith("*"):
        flag_star = True
        n = n[:-1].strip()
    match = re.search(r"(?:\s*\+\s*(\d+))\s*$", n)
    if not match:
        return n, None, flag_star
    return n[: match.start()].strip(), int(match.group(1)), flag_star


def _parse_int(text: str) -> int | None:
    raw = (text or "").strip()
    if not raw or not _INT_TOKEN.fullmatch(raw):
        return None
    return int(raw)


def _split_location(location: str) -> tuple[str, list[int]]:
    """Split only a trailing (-SlotN)+ suffix. Hyphens inside the token stay."""
    match = _TRAILING_SLOTS.search(location)
    if not match:
        return location, []
    slots = [int(n) for n in _SLOT_NUMBER.findall(match.group(0))]
    return location[: match.start()], slots


def _parent_location(location: str) -> str | None:
    match = _LAST_SLOT.search(location)
    if not match:
        return None
    parent = location[: match.start()]
    return parent or None


def _numbered_token(token: str, prefix: str, low: int, high: int | None) -> bool:
    if len(token) <= len(prefix) or not token.lower().startswith(prefix.lower()):
        return False
    rest = token[len(prefix):]
    if not rest.isdigit():
        return False
    number = int(rest)
    if number < low:
        return False
    return high is None or number <= high


def _wearable_slot_tokens() -> set[str]:
    tokens = {key.upper() for key in LOCATION_TO_SLOTS}
    tokens.update(_OBSERVED_WORN)
    for slots in LOCATION_TO_SLOTS.values():
        tokens.update(slot.upper() for slot in slots)
    return tokens


_WEARABLE_SLOT_TOKENS = _wearable_slot_tokens()


def _container_kind(base: str) -> str:
    """Kinds follow the closed lists in SPEC §4.1. Unseen indexes stay unknown.

    Hoard N is the Dragon's Hoard container from a dump taken with that window
    open. N has no observed upper bound in the sample (1..74). -SlotK under a
    hoard row is that item's aug slot, attached by the usual parent link.
    """
    token = (base or "").strip()
    # "General N" has no observed upper bound. Bank is 1–24, SharedBank is 1–6.
    if _GENERAL_TOKEN.fullmatch(token) and _numbered_token(token, "general ", 1, None):
        return "general"
    if _HOARD_TOKEN.fullmatch(token) and _numbered_token(token, "hoard ", 1, None):
        return "dragonhorde"
    if _numbered_token(token, "sharedbank", 1, 6):
        return "sharedbank"
    if _numbered_token(token, "bank", 1, 24):
        return "bank"
    # Only Personal-Depot1 was in a dump. The hyphen stays part of the token.
    if token.casefold() == "personal-depot1":
        return "depot"
    upper = token.upper()
    if upper in _OBSERVED_WORN or upper in LOCATION_TO_SLOTS:
        return "worn"
    return "unknown"


def _is_exaltation_name(name: str) -> bool:
    return bool(_EXALTATION_NAME.search(name or ""))


def _is_container_name(name: str) -> bool:
    return bool(_CONTAINER_NAME.search(name or ""))


def _catalog_slots(base_name: str, item_id: str) -> set[str]:
    match = _catalog_match(base_name, item_id=item_id or None)
    slots = match.get("slots") or []
    return {str(slot).strip().upper() for slot in slots if str(slot).strip()}


def _row_flags(name: str, base_name: str, item_id: str, kind: str, slot_nums: list[int]) -> tuple[bool, bool]:
    """Wearable means the catalog slot list or a worn sheet row.

    A bag or box name is a container even when it sits in a bank or bag slot.
    A loose item in Bank N is not a container. Exaltations are not wearable gear.
    """
    catalog_slots = _catalog_slots(base_name, item_id)
    catalog_wearable = bool(catalog_slots & _WEARABLE_SLOT_TOKENS)
    on_sheet = kind == "worn" and not slot_nums
    exaltation = _is_exaltation_name(name) or _is_exaltation_name(base_name)
    container_item = _is_container_name(base_name or name)
    wearable = (catalog_wearable or on_sheet) and not exaltation and not container_item
    return wearable, container_item


def _classify_header(line: str) -> tuple[str, dict[str, int]] | None:
    """Known headers, matched by column name. Order does not matter."""
    index: dict[str, int] = {}
    for i, part in enumerate(line.split("\t")):
        key = part.strip().lower()
        if not key or key in index:
            continue
        index[key] = i
    names = set(index)
    if {"location", "name", "id", "count", "slots"} <= names:
        return "location", index
    if {"keyring", "name", "id"} <= names and "location" not in names:
        return "keyring", index
    return None


def _cell(cols: list[str], index: dict[str, int], key: str) -> str:
    pos = index.get(key)
    if pos is None or pos >= len(cols):
        return ""
    return cols[pos].strip()


def _scan_sections(lines: list[str]) -> list[dict[str, Any]]:
    """Walk the whole file. A section ends at a blank line or the next header."""
    sections: list[dict[str, Any]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        classified = _classify_header(line)
        if classified is None:
            if "\t" not in line:
                i += 1
                continue
            kind = "unknown"
            columns: dict[str, int] | None = None
        else:
            kind, columns = classified
        header_line = line
        header_line_no = i + 1
        i += 1
        records: list[tuple[str, int]] = []
        while i < n:
            row_line = lines[i]
            if not row_line.strip():
                break
            if _classify_header(row_line) is not None:
                break
            records.append((row_line, i + 1))
            i += 1
        sections.append({
            "kind": kind,
            "header": header_line,
            "header_line": header_line_no,
            "columns": columns,
            "records": records,
        })
    return sections


def _link_parents(rows: list[dict[str, Any]]) -> list[str]:
    """Most recent preceding row whose location token is the parent token."""
    warnings: list[str] = []
    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        parent = _parent_location(row["location_raw"])
        if parent is None:
            row["parent_idx"] = None
        else:
            row["parent_idx"] = seen.get(parent.casefold())
            if row["parent_idx"] is None:
                warnings.append(
                    f"No parent row for {row['location_raw']} (line {row['line']})"
                )
        seen[row["location_raw"].casefold()] = i
    return warnings


def _collapse_keyring(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Duplicate Table 2 rows become one entry. Count is how many were seen."""
    collapsed: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for entry in entries:
        key = (entry["ring"].casefold(), entry["name"], entry["id"])
        found = collapsed.get(key)
        if found is None:
            collapsed[key] = {
                "ring": entry["ring"],
                "name": entry["name"],
                "id": entry["id"],
                "count": 1,
                "wearable": bool(entry.get("wearable")),
                "container_item": bool(entry.get("container_item")),
            }
            order.append(key)
        else:
            found["count"] += 1
            if entry.get("wearable"):
                found["wearable"] = True
            if entry.get("container_item"):
                found["container_item"] = True
    return [collapsed[key] for key in order]


def _empty_void_touched() -> dict[str, Any]:
    return {"name": VOID_TOUCHED_NAME, "count": 0, "locations": []}


def _extract_currencies(
    rows: list[dict[str, Any]],
    keyring: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Bag and key-ring counts for the 10 mote grades, Void-Touched, and Wind Runes."""
    motes: dict[int, dict[str, Any]] = {}
    void_touched = _empty_void_touched()
    runes: dict[str, dict[str, Any]] = {}

    def observe(raw_name: str, count: int | None, location: str) -> None:
        if not isinstance(count, int) or count <= 0:
            return
        base, _tier, _star = _parse_item_name(raw_name)
        if not base or base.lower() == "empty":
            return
        grade = _MOTE_GRADE_BY_NAME.get(base)
        if grade is not None:
            slot = motes.get(grade)
            if slot is None:
                slot = {"grade": grade, "name": base, "count": 0, "locations": []}
                motes[grade] = slot
            slot["count"] += count
            slot["locations"].append(location)
            return
        if base == VOID_TOUCHED_NAME:
            void_touched["count"] += count
            void_touched["locations"].append(location)
            return
        if base in _WIND_RUNE_NAMES:
            slot = runes.get(base)
            if slot is None:
                slot = {"name": base, "count": 0, "locations": []}
                runes[base] = slot
            slot["count"] += count
            slot["locations"].append(location)

    for row in rows:
        observe(row.get("name_raw") or "", row.get("count"), row.get("location_raw") or "")
    for entry in keyring:
        observe(entry.get("name") or "", entry.get("count"), entry.get("ring") or "")
    return (
        [motes[grade] for grade in sorted(motes)],
        void_touched,
        list(runes.values()),
    )


def _unknown_row(section: dict[str, Any], raw: str, line: int) -> dict[str, Any]:
    return {
        "line": line,
        "header": section["header"],
        "header_line": section["header_line"],
        "raw": raw,
    }


def _catalog_match(name: str, item_id: str | None = None) -> dict[str, Any]:
    # Never let catalog/image I/O break Inventory.txt import.
    try:
        return item_catalog_mod.catalog_match(name, item_id=item_id)
    except Exception:
        return {
            "matched": False,
            "source": None,
            "has_stats": False,
            "name": (name or "").strip() or None,
            "itemID": None,
        }


def _catalog_has_name(name: str, item_id: str | None = None) -> bool:
    return bool(_catalog_match(name, item_id=item_id).get("matched"))


_BINARY_HINT = re.compile(
    r"(This program cannot be run in DOS mode|\x00MZ|^\x7fELF|^\x89PNG)",
    re.I | re.M,
)
_INVENTORY_HELP = (
    "Use Inventory.txt from in-game /outputfile inventory "
    "(not inventory.exe or other binaries)."
)


def looks_like_binary_inventory(text: str) -> bool:
    """True when payload looks like a PE/ELF/binary dump rather than Inventory.txt TSV."""
    if text is None:
        return False
    sample = text[:4096]
    if "\x00" in sample:
        return True
    if sample.startswith("MZ") or sample.startswith("\x7fELF"):
        return True
    if _BINARY_HINT.search(sample):
        return True
    # High ratio of non-text bytes in the sample
    if sample:
        weird = sum(1 for ch in sample if ord(ch) < 9 or (14 <= ord(ch) < 32 and ch not in "\t\n\r"))
        if weird / max(1, len(sample)) > 0.08:
            return True
    return False


def _is_empty_item(name: str, base_name: str) -> bool:
    # Empty inventory lines are noise for Search My Bags — drop them from all_items.
    return (
        not name
        or name.strip().lower() == "empty"
        or not base_name
        or base_name.lower() == "empty"
    )


def _legacy_entry(
    *,
    location: str,
    name: str,
    base_name: str,
    upgrade: int | None,
    item_id: str,
    count: str,
    slots_col: str,
) -> dict[str, Any]:
    match = _catalog_match(base_name, item_id=item_id or None)
    in_catalog = bool(match.get("matched"))
    return {
        "location": location,
        "name": name,
        "base_name": base_name,
        "upgrade_from_name": upgrade,
        "id": item_id,
        "count": count,
        "slots": slots_col,
        "in_catalog": in_catalog,
        "catalog_source": match.get("source"),
        "has_stats": bool(match.get("has_stats")),
        "unmatched": not in_catalog and bool(base_name),
        "planner_slot": None,
        "reason": None,
    }


def _keep_legacy(
    entry: dict[str, Any],
    *,
    reason: str | None,
    all_items: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    worn: list[dict[str, Any]] | None = None,
    count_unmatched: bool = True,
) -> None:
    entry["reason"] = reason
    if worn is not None:
        worn.append(entry)
    else:
        skipped.append(entry)
    all_items.append(entry)
    if count_unmatched and entry["unmatched"]:
        unmatched.append(entry)


def _tree_row(
    *,
    location: str,
    base: str,
    slot_nums: list[int],
    name: str,
    base_name: str,
    tier: int | None,
    flag_star: bool,
    item_id: str,
    count: str,
    slots_col: str,
    line: int,
) -> dict[str, Any]:
    socket_index = slot_nums[-1] if slot_nums else None
    kind = _container_kind(base)
    # Slot7–10 role names apply to worn gear and hoard aug slots. A bag's Slot9 is not "Worn?".
    label = (
        EXALTATION_SOCKET_LABELS.get(socket_index)
        if kind in ("worn", "dragonhorde") and socket_index is not None
        else None
    )
    wearable, container_item = _row_flags(name, base_name, item_id, kind, slot_nums)
    return {
        "location_raw": location,
        "container_kind": kind,
        "parent_idx": None,
        "depth": len(slot_nums),
        "socket_index": socket_index,
        "socket_label": label,
        "name_raw": name,
        "name": base_name,
        "tier": tier,
        "flag_star": flag_star,
        "id": item_id,
        "count": _parse_int(count),
        "slots": _parse_int(slots_col),
        "line": line,
        "wearable": wearable,
        "container_item": container_item,
    }


def parse_inventory_tsv(
    text: str,
    *,
    character: str | None = None,
    server: str | None = None,
    file_name: str | None = None,
    file_mtime: str | None = None,
    imported_at: str | None = None,
) -> dict[str, Any]:
    """Parse Inventory.txt. Worn gear still maps through LOCATION_TO_SLOTS.

    Also returns the §4.3 snapshot pieces: rows (with parent links), keyring,
    unknown_rows, and mote / currency counts. Header rows are never items.
    Raises ValueError when the payload looks like a binary/.exe file.
    """
    if looks_like_binary_inventory(text or ""):
        raise ValueError(_INVENTORY_HELP)

    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
    lines = normalized.split("\n")

    worn: list[dict[str, Any]] = []
    all_items: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    equipment: dict[str, str] = {}
    upgrade_hints: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    keyring_raw: list[dict[str, Any]] = []
    unknown_rows: list[dict[str, Any]] = []
    saw_known_header = False

    for section in _scan_sections(lines):
        kind = section["kind"]
        if kind == "unknown":
            records = section["records"]
            if not records:
                unknown_rows.append(_unknown_row(section, section["header"], section["header_line"]))
                continue
            for raw, line_no in records:
                unknown_rows.append(_unknown_row(section, raw, line_no))
            continue

        saw_known_header = True
        columns = section["columns"] or {}
        if kind == "keyring":
            for raw, line_no in section["records"]:
                cols = raw.split("\t")
                ring = _cell(cols, columns, "keyring")
                name = _cell(cols, columns, "name")
                item_id = _cell(cols, columns, "id")
                base_name, _tier, _star = _parse_item_name(name)
                if ring.casefold() not in _KNOWN_RINGS:
                    unknown_rows.append(_unknown_row(section, raw, line_no))
                    if _is_empty_item(name, base_name):
                        continue
                    entry = _legacy_entry(
                        location=ring,
                        name=name,
                        base_name=base_name,
                        upgrade=_tier,
                        item_id=item_id,
                        count="",
                        slots_col="",
                    )
                    _keep_legacy(
                        entry,
                        reason="unknown location",
                        all_items=all_items,
                        skipped=skipped,
                        unmatched=unmatched,
                    )
                    continue
                if _is_empty_item(name, base_name):
                    continue
                wearable, container_item = _row_flags(name, base_name, item_id, "keyring", [])
                keyring_raw.append({
                    "ring": ring,
                    "name": name,
                    "id": item_id,
                    "count": 1,
                    "wearable": wearable,
                    "container_item": container_item,
                })
                entry = _legacy_entry(
                    location=ring,
                    name=name,
                    base_name=base_name,
                    upgrade=_tier,
                    item_id=item_id,
                    count="",
                    slots_col="",
                )
                _keep_legacy(
                    entry,
                    reason="owned",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
            continue

        for raw, line_no in section["records"]:
            cols = raw.split("\t")
            location = _cell(cols, columns, "location")
            name = _cell(cols, columns, "name")
            item_id = _cell(cols, columns, "id")
            count = _cell(cols, columns, "count")
            slots_col = _cell(cols, columns, "slots")
            if not location and not name:
                continue
            base, slot_nums = _split_location(location)
            base_name, tier, flag_star = _parse_item_name(name)
            row = _tree_row(
                location=location,
                base=base,
                slot_nums=slot_nums,
                name=name,
                base_name=base_name,
                tier=tier,
                flag_star=flag_star,
                item_id=item_id,
                count=count,
                slots_col=slots_col,
                line=line_no,
            )
            container = row["container_kind"]
            if container == "unknown":
                unknown_rows.append(_unknown_row(section, raw, line_no))
            rows.append(row)
            if _is_empty_item(name, base_name):
                continue
            entry = _legacy_entry(
                location=location,
                name=name,
                base_name=base_name,
                upgrade=tier,
                item_id=item_id,
                count=count,
                slots_col=slots_col,
            )
            if container == "unknown":
                _keep_legacy(
                    entry,
                    reason="unknown location",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
                continue
            if slot_nums:
                # Nested unmatched rows stay out of `unmatched`, as before.
                _keep_legacy(
                    entry,
                    reason="nested/aug slot",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                    count_unmatched=False,
                )
                continue
            if container in ("general", "bank"):
                _keep_legacy(
                    entry,
                    reason="bag/bank",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
                continue
            if container == "sharedbank":
                _keep_legacy(
                    entry,
                    reason="shared bank",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
                continue
            if container == "depot":
                _keep_legacy(
                    entry,
                    reason="depot",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
                continue
            if container == "dragonhorde":
                _keep_legacy(
                    entry,
                    reason="dragon hoard",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
                continue

            targets = LOCATION_TO_SLOTS.get(base.upper())
            if not targets:
                _keep_legacy(
                    entry,
                    reason="unknown location",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
                continue
            planner_slot = None
            for cand in targets:
                if cand not in equipment:
                    planner_slot = cand
                    break
            if planner_slot is None:
                _keep_legacy(
                    entry,
                    reason="extra duplicate location",
                    all_items=all_items,
                    skipped=skipped,
                    unmatched=unmatched,
                )
                continue
            entry["planner_slot"] = planner_slot
            reason = None if entry["in_catalog"] else "not in item catalog (shown anyway)"
            _keep_legacy(
                entry,
                reason=reason,
                all_items=all_items,
                skipped=skipped,
                unmatched=unmatched,
                worn=worn,
            )
            equipment[planner_slot] = base_name
            if tier is not None:
                upgrade_hints[planner_slot] = tier

    warnings = _link_parents(rows)
    if not saw_known_header and any(line.strip() for line in lines):
        warnings.append("No inventory header found")
    keyring = _collapse_keyring(keyring_raw)
    motes, void_touched, wind_runes = _extract_currencies(rows, keyring)

    try:
        coverage = item_catalog_mod.catalog_coverage()
    except Exception:
        coverage = {}

    return {
        "character": character,
        "server": server,
        "file_name": file_name,
        "file_mtime": file_mtime,
        "imported_at": imported_at,
        "equipment": equipment,
        "upgrade_hints": upgrade_hints,
        "worn": worn,
        "rows": rows,
        "keyring": keyring,
        "unknown_rows": unknown_rows,
        "motes": motes,
        "void_touched": void_touched,
        "wind_runes": wind_runes,
        "all_items": all_items[:5000],
        "unmatched": unmatched[:500],
        "unmatched_count": len(unmatched),
        "skipped": skipped[:500],
        "skipped_count": len(skipped),
        "catalog_coverage": coverage,
        "warnings": warnings,
        "note": (
            "Parsed Inventory.txt TSV (Location/Name/ID/Count/Slots). "
            "Every line is retained in all_items. Names match eqlegendstools BiS data "
            "and/or eqlwiki Category:Items (wiki matches do not invent stats). "
            "Nested *-SlotN / bags / bank tagged in skipped but still visible in all_items."
        ),
    }


def _stats_at_level(item: dict[str, Any] | None, level: int) -> dict[str, Any]:
    """Catalog stats at an enchant level. Never invent; never use +10 for a lower worn level."""
    if not item:
        return {}
    level = max(0, min(10, int(level)))
    s0 = item.get("stats_plus0") or {}
    if s0:
        return engine.scale_stats_to_level(s0, level)
    if level >= 10:
        return dict(item.get("stats_plus10") or item.get("stats_at_upgrade") or {})
    # items_for_slot already filled stats_at_upgrade at this worn level
    return dict(item.get("stats_at_upgrade") or {})


def _stat_delta(worn_stats: dict, bis_stats: dict) -> list[dict[str, Any]]:
    keys = [
        "AC", "HP", "MANA", "END", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA",
        "Haste", "DMG", "DLY", "HP_REGEN", "MANA_REGEN", "END_REGEN",
        "SVF", "SVC", "SVM", "SVP", "SVD",
    ]
    out = []
    for k in keys:
        a = float(worn_stats.get(k) or 0)
        b = float(bis_stats.get(k) or 0)
        d = b - a
        if abs(d) < 1e-9:
            continue
        out.append({"stat": k, "worn": a, "bis": b, "delta": d})
    return out


def _slot_importance(slot: str) -> int:
    """Tie-break order when priorities match — weapons/chest before jewelry."""
    order = [
        "CHEST", "PRIMARY", "SECONDARY", "LEGS", "HEAD", "ARMS", "HANDS", "FEET",
        "BACK", "SHOULDERS", "WAIST", "FACE", "NECK", "WRIST1", "WRIST2", "EAR1", "EAR2",
        "FINGER1", "FINGER2", "RANGE", "AMMO",
    ]
    try:
        return len(order) - order.index(slot)
    except ValueError:
        return 0


def _norm_item_name(name: str | None) -> str:
    from .item_names import owned_name_key
    return owned_name_key(name or "")


def _dedicated_slots_for_recommendation(row: dict[str, Any]) -> set[str]:
    """Item's real planner slots (never Any). Empty if unknown — do not invent."""
    planner: set[str] = set()
    item = row.get("item") or {}
    for src in (row.get("planner_slots"), item.get("planner_slots")):
        planner |= {str(s).upper() for s in (src or []) if s}
    # row["slot"] is the recommendation target (e.g. ANY2), not the item type.
    for field in (item.get("slots"), item.get("slot"), row.get("slots")):
        if field:
            planner |= set(sc.expand_slots(field))
    planner -= sc.ANY_SLOTS
    planner.discard("")
    if planner:
        return planner
    name = (row.get("name") or "").strip()
    if not name:
        return set()
    try:
        cat = item_catalog_mod.get_item_by_name(name)
    except Exception:
        cat = None
    if not cat:
        return set()
    found = set(sc.expand_slots(cat.get("slots") or cat.get("slot") or []))
    found |= {str(s).upper() for s in (cat.get("planner_slots") or [])}
    return found - sc.ANY_SLOTS


def _equipped_real_slot(
    equipment: dict[str, str],
    item_name: str,
    *,
    dedicated: set[str] | None = None,
) -> str | None:
    """Dedicated (non-Any) planner slot where this item is already worn.

    When *dedicated* is known (e.g. CHEST for Valorium Chestplate), only that
    real slot counts — wearing the piece somewhere invalid is not this rule.
    """
    want = _norm_item_name(item_name)
    if not want:
        return None
    eq = {str(k).upper(): (v or "").strip() for k, v in (equipment or {}).items() if v}
    allowed = set(dedicated) if dedicated else None
    for slot in sc.PLANNER_SLOTS:
        if slot in sc.ANY_SLOTS:
            continue
        if allowed is not None and slot not in allowed:
            continue
        if _norm_item_name(eq.get(slot)) == want:
            return slot
    if allowed:
        return None
    for slot, worn in eq.items():
        if slot in sc.ANY_SLOTS or slot in sc.PLANNER_SLOTS:
            continue
        if _norm_item_name(worn) == want:
            return slot
    return None


def _recommendation_is_weapon(row: dict[str, Any], real_slot: str | None = None) -> bool:
    """True when the Any pick is a weapon — those must not interchange with real slots.

    Damage does not apply from Any (effective damage ≈ 0), so PRIMARY/SECONDARY/RANGE
    recommendations stay separate. Uses row flags and equipped location only — never
    invents stats.
    """
    if real_slot and real_slot in sc.WEAPON_SLOTS:
        return True
    if row.get("is_weapon"):
        return True
    item = row.get("item") or {}
    if item.get("is_weapon"):
        return True
    planner = {
        str(s).upper()
        for s in (row.get("planner_slots") or item.get("planner_slots") or [])
    }
    if planner & sc.WEAPON_SLOTS:
        return True
    if "is_weapon" in row or "is_weapon" in item:
        return False
    name = (row.get("name") or "").strip()
    if not name:
        return False
    try:
        cat = item_catalog_mod.get_item_by_name(name)
    except Exception:
        cat = None
    if cat and sc.is_weapon_item(cat):
        return True
    return False


def _clear_slot_recommendation(row: dict[str, Any]) -> None:
    slot = row.get("slot")
    row.clear()
    row["slot"] = slot
    row["name"] = ""
    row["alts"] = []
    row["why"] = ""


def _swap_recommendation_payload(a: dict[str, Any], b: dict[str, Any]) -> None:
    """Swap BiS recommendation fields; keep each row's slot id."""
    a_keep = {k: v for k, v in a.items() if k != "slot"}
    b_keep = {k: v for k, v in b.items() if k != "slot"}
    for key in list(a.keys()):
        if key != "slot":
            del a[key]
    for key in list(b.keys()):
        if key != "slot":
            del b[key]
    a.update(b_keep)
    b.update(a_keep)


def interchange_any_real_slot_recommendations(
    slots: list[dict[str, Any]],
    equipment: dict[str, str],
) -> list[dict[str, Any]]:
    """Non-weapons: if Any recommends an item already worn in its real slot, swap.

    Example: Valorium Chestplate recommended for ANY2 but equipped on CHEST → the
    CHEST recommendation moves into ANY2, and the equipped chestpiece covers CHEST.

    Weapons are never interchanged this way. Stats may score in Any, but damage
    does not (effective damage ≈ 0).
    """
    if not slots:
        return slots
    by_slot = {row.get("slot"): row for row in slots if row.get("slot")}
    swapped_real: set[str] = set()
    for any_slot in ("ANY1", "ANY2"):
        any_row = by_slot.get(any_slot)
        if not any_row:
            continue
        rec_name = (any_row.get("name") or "").strip()
        if not rec_name:
            continue
        dedicated = _dedicated_slots_for_recommendation(any_row)
        real_slot = _equipped_real_slot(equipment, rec_name, dedicated=dedicated or None)
        if not real_slot or real_slot in swapped_real:
            continue
        if _recommendation_is_weapon(any_row, real_slot):
            continue
        real_row = by_slot.get(real_slot)
        if not real_row:
            # Equipped real-slot piece covers this leftover Any pick.
            _clear_slot_recommendation(any_row)
            continue
        real_name = (real_row.get("name") or "").strip()
        if _norm_item_name(real_name) == _norm_item_name(rec_name):
            # Same piece on both recommendations; equipped covers the Any copy.
            _clear_slot_recommendation(any_row)
            continue
        _swap_recommendation_payload(any_row, real_row)
        any_row["_interchange"] = {
            "from_slot": real_slot,
            "equipped": rec_name,
        }
        swapped_real.add(real_slot)
    return slots


def _enrich_obtain(row: dict[str, Any], *, fetch_quest: bool = True) -> dict[str, Any]:
    """Attach zone/mob/quest obtain path for a BiS suggestion target.

    Degrades gracefully when quest wiki / zone research is unavailable — never raises.
    """
    name = (row.get("name") or "").strip()
    try:
        cat = item_catalog_mod.get_item_by_name(name) if name else None
    except Exception:
        cat = None
    base = {
        "zone": row.get("zone") or (cat or {}).get("zone") or "",
        "drops_mobs": row.get("drops_mobs") or (cat or {}).get("drops_mobs") or "",
        "quest_source": row.get("quest_source") or (cat or {}).get("quest_source") or (cat or {}).get("source") or "",
        "url": row.get("url") or (cat or {}).get("url") or "",
        "name": name,
    }
    try:
        obtain = quest_guides.obtain_path_for_item({**(cat or {}), **base}, fetch_quest=fetch_quest)
    except Exception:
        obtain = {
            "how": "unknown",
            "zone": base.get("zone") or "",
            "drops_mobs": base.get("drops_mobs") or "",
            "quest_source": base.get("quest_source") or "",
            "quest_name": None,
            "quest_guide": None,
            "item_url": base.get("url") or "",
            "error": "obtain path unavailable",
        }
    # Zone research summary (mobs with levels when available) — never invent
    zone_detail = None
    if obtain.get("zone"):
        try:
            zone_detail = zones_mod.zone_detail_for_item(obtain["zone"], obtain.get("drops_mobs") or "")
        except Exception:
            zone_detail = None
    return {
        **obtain,
        "zone_detail": {
            "found": bool((zone_detail or {}).get("found")),
            "zone": (zone_detail or {}).get("zone") or obtain.get("zone"),
            "drop_mobs": (zone_detail or {}).get("drop_mobs") or [],
            "level_requirement": ((zone_detail or {}).get("overview") or {}).get("level_requirement")
            or (zone_detail or {}).get("level_requirement"),
            "walkthrough_urls": (zone_detail or {}).get("walkthrough_urls") or [],
            "map_url": (zone_detail or {}).get("map_url"),
            "message": (zone_detail or {}).get("message") or "",
        } if obtain.get("zone") else None,
    }


def suggest_upgrades(
    classes: list[str],
    equipment: dict[str, str],
    *,
    upgrade: int = 10,
    slot_upgrades: dict[str, Any] | None = None,
    character_level: int = 50,
    prefer_ranged_damage: bool = True,
    alts: int = 3,
    mode: str = "ai",
    priority_stat: str = "HP",
    primary_stats: list[str] | None = None,
    secondary_stats: list[str] | None = None,
    tertiary_stats: list[str] | None = None,
    maximize_hp_regen: bool = False,
    fetch_quest_guides: bool = True,
) -> dict[str, Any]:
    """Compare current equipment vs BiS list for the trio; prioritize closing BiS gaps."""
    if not classes:
        return {"suggestions": [], "bis": None, "error": "Select at least one class"}

    upgrade = max(0, min(10, int(upgrade)))
    slot_upg: dict[str, int] = {}
    for k, v in (slot_upgrades or {}).items():
        try:
            slot_upg[str(k).upper()] = max(0, min(10, int(v)))
        except (TypeError, ValueError):
            continue

    bis = engine.recommend_bis(
        classes,
        mode=mode or "ai",
        priority_stat=priority_stat or "HP",
        alts=alts,
        upgrade=upgrade,
        prefer_ranged_damage=prefer_ranged_damage,
        character_level=character_level,
        primary_stats=primary_stats,
        secondary_stats=secondary_stats,
        tertiary_stats=tertiary_stats,
        maximize_hp_regen=maximize_hp_regen,
    )
    suggestions: list[dict[str, Any]] = []
    equipment_compare: list[dict[str, Any]] = []
    eq_norm = {str(k).upper(): v for k, v in (equipment or {}).items() if v}
    # Non-weapon Any↔real-slot interchange so Upgrade Priority does not
    # double-recommend a piece already worn in its dedicated slot.
    interchange_any_real_slot_recommendations(bis.get("slots") or [], eq_norm)

    for row in bis.get("slots") or []:
        slot = row["slot"]
        bis_name = (row.get("name") or "").strip()
        current = (eq_norm.get(slot) or "").strip()
        # Worn stats at the piece's actual enchant; BiS stats at planner ``upgrade`` (often +10).
        worn_level = slot_upg.get(slot, upgrade)
        bis_stats = _stats_at_level(row, upgrade)
        bis_alts = [{"name": bis_name, "why": row.get("why"), "url": row.get("url") or ""}]
        for a in row.get("alts") or []:
            if a.get("name"):
                bis_alts.append({
                    "name": a["name"],
                    "why": a.get("why"),
                    "url": a.get("url") or "",
                    "stats_at_upgrade": _stats_at_level(a, upgrade),
                })

        cur_item = None
        cur_stats: dict[str, Any] = {}
        if current:
            try:
                pool_items = engine.items_for_slot(
                    classes, slot=slot, upgrade=worn_level, prefer_ranged_damage=prefer_ranged_damage
                )
            except Exception:
                pool_items = []
            cur_item = next(
                (it for it in pool_items if (it.get("name") or "").lower() == current.lower()),
                None,
            )
            if cur_item:
                cur_stats = _stats_at_level(cur_item, worn_level)
            else:
                # Unmatched worn item — scale catalog +0 to worn_level; never invent stats
                cat = item_catalog_mod.get_item_by_name(current)
                if cat:
                    cur_stats = _stats_at_level(cat, worn_level)

        deltas = _stat_delta(cur_stats, bis_stats) if bis_name else []
        equipment_compare.append({
            "slot": slot,
            "worn": {
                "name": current or None,
                "in_catalog": bool(cur_item) or (bool(current) and _catalog_has_name(current)),
                "stats": cur_stats,
                "upgrade": worn_level,
                "url": (cur_item or {}).get("url") or "",
                "image_url": f"/api/item-image?name={current}" if current else "",
            },
            "suggested_upgrade": upgrade,
            "bis_options": bis_alts,
            "selected_bis": bis_name or None,
            "deltas": deltas,
        })

        if not bis_name:
            continue
        if current and current.lower() == bis_name.lower():
            continue

        positive_gap = sum(d["delta"] for d in deltas if d["delta"] > 0)
        negative_gap = sum(-d["delta"] for d in deltas if d["delta"] < 0)
        net_gap = positive_gap - negative_gap

        if not current:
            pri = 100
            reason = "missing BiS (slot empty) — upgrade to BiS list pick"
        else:
            worse = net_gap > 1e-9
            reason = (
                f"not current BiS — replace with {bis_name}"
                + (f" (net BiS gain ~{net_gap:.0f})" if deltas else "")
            )
            # Finer priority: empty=100, large gap=90-99, unmatched=85, small/neutral=50-70
            if not cur_item and not _catalog_has_name(current):
                pri = 85
                reason = f"worn item unmatched in DB; BiS list recommends {bis_name}"
            elif worse:
                pri = min(99, 90 + int(min(9, max(0, net_gap) // 20)))
            else:
                pri = 55

        obtain = _enrich_obtain(row, fetch_quest=fetch_quest_guides)
        how_bits = []
        if obtain.get("how") == "drop" and (obtain.get("zone") or obtain.get("drops_mobs")):
            how_bits.append(
                "Drop"
                + (f" in {obtain['zone']}" if obtain.get("zone") else "")
                + (f" from {obtain['drops_mobs']}" if obtain.get("drops_mobs") else "")
            )
        elif obtain.get("how") == "quest" and obtain.get("quest_name"):
            how_bits.append(f"Quest: {obtain['quest_name']}")
        elif obtain.get("zone"):
            how_bits.append(f"Zone: {obtain['zone']}")
        if how_bits:
            reason = f"{reason} · {' · '.join(how_bits)}"
        interchange = row.get("_interchange") or {}
        if interchange.get("from_slot") and interchange.get("equipped"):
            reason = (
                f"{reason} · Any↔{interchange['from_slot']} interchange "
                f"({interchange['equipped']} already equipped on {interchange['from_slot']})"
            )

        suggestions.append({
            "slot": slot,
            "priority": pri,
            "rank_score": pri * 1000 + _slot_importance(slot) * 10 + max(0, int(net_gap)),
            "reason": reason,
            "current": current or None,
            "current_upgrade": worn_level if current else None,
            "suggested": bis_name,
            "suggested_upgrade": upgrade,
            "interchange": interchange or None,
            "suggested_url": row.get("url") or obtain.get("item_url") or "",
            "suggested_zone": obtain.get("zone") or row.get("zone") or "",
            "suggested_drops_mobs": obtain.get("drops_mobs") or "",
            "suggested_quest_source": obtain.get("quest_source") or "",
            "suggested_quest_name": obtain.get("quest_name"),
            "suggested_ratio": row.get("ratio_at_upgrade"),
            "suggested_why": row.get("why") or "",
            "suggested_image_url": f"/api/item-image?name={bis_name}" if bis_name else "",
            "deltas": deltas,
            "obtain": obtain,
        })

    suggestions.sort(key=lambda s: (-s.get("rank_score", 0), -s["priority"], s["slot"]))
    # Stable 1-based display rank
    for i, s in enumerate(suggestions, start=1):
        s["rank"] = i

    return {
        "suggestions": suggestions,
        "equipment_compare": equipment_compare,
        "bis_summary": {
            "classes": bis.get("classes"),
            "mode": bis.get("mode"),
            "upgrade": bis.get("upgrade"),
            "character_level": bis.get("character_level"),
            "pool_size": bis.get("pool_size"),
        },
        "equipment": eq_norm,
        "note": (
            "Upgrade Priority list is ordered by importance (empty slots first, then largest "
            "BiS gaps). Each entry includes how to get the item: zone + drop mobs and/or quest "
            "name with steps from eqlwiki when available — never invented. "
            "If a non-weapon recommended for Any is already worn in its real slot "
            "(e.g. Valorium Chestplate on Chest while listed for Any2), those recommendations "
            "swap so the same piece is not double-listed. Weapons are never swapped this way "
            "(damage does not apply from Any)."
        ),
    }
