"""Copy allowlisted zone-research files into the packaged resources tree.

Scripts and research digs stay out. An external full tree, when one exists,
is copied first. The October update is then merged by zone slug. A missing
packaged index is an error.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ALLOWLIST_FILES = ("zones_index.json", "mobs.csv", "SOURCES.md")


def copy_allowlist(src: Path, dst: Path) -> None:
    """Copy the index, mob table, sources note, and zone JSON files only."""
    dst.mkdir(parents=True, exist_ok=True)
    for name in ALLOWLIST_FILES:
        path = src / name
        if path.is_file():
            shutil.copy2(path, dst / name)
    zones = src / "zones"
    if not zones.is_dir():
        return
    out = dst / "zones"
    out.mkdir(parents=True, exist_ok=True)
    for path in sorted(zones.glob("*.json")):
        if path.is_file():
            shutil.copy2(path, out / path.name)


def _read_index(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _read_mobs(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        return [], []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        return list(reader.fieldnames or []), rows


def merge_zone_update(dst: Path, update: Path) -> None:
    """Union zones by slug. Update rows replace the same zone's mobs."""
    if not (update / "zones_index.json").is_file():
        return
    copy_allowlist(update, dst)
    base = _read_index(dst / "zones_index.json")
    upd = _read_index(update / "zones_index.json")
    # copy_allowlist just overwrote the index with the update. Re-read is the
    # update. Merge needs the previous index, so callers pass a tree that
    # already had the base files. Reconstruct from the file we just replaced
    # only when dst was empty. When dst already held a larger index, the
    # caller saves it first via merge_indexes.
    by_slug: dict[str, dict] = {}
    order: list[str] = []
    saved = dst / "zones_index.base.json"
    prior = _read_index(saved) if saved.is_file() else {}
    if saved.is_file():
        saved.unlink()
    for row in list(prior.get("zones") or []) + list(upd.get("zones") or []):
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        if slug not in by_slug:
            order.append(slug)
        by_slug[slug] = row
    out = dict(prior or upd)
    extra = str(upd.get("batches") or "").strip()
    current = str(out.get("batches") or "").strip()
    if extra and extra not in current:
        out["batches"] = f"{current}, {extra}".strip(", ") if current else extra
    if prior.get("generated"):
        out["generated"] = prior["generated"]
    elif upd.get("generated"):
        out["generated"] = upd["generated"]
    if not prior and upd.get("note"):
        out["note"] = upd["note"]
    out["zones"] = [by_slug[slug] for slug in order]
    zone_dir = dst / "zones"
    out["zone_file_count"] = len(list(zone_dir.glob("*.json"))) if zone_dir.is_dir() else 0
    (dst / "zones_index.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    names = {
        str(row.get("zone") or "").strip()
        for row in (upd.get("zones") or [])
        if isinstance(row, dict) and str(row.get("zone") or "").strip()
    }
    base_fields, base_rows = _read_mobs(dst / "mobs.csv")
    upd_fields, upd_rows = _read_mobs(update / "mobs.csv")
    # copy_allowlist replaced mobs.csv with the update. Keep prior rows from
    # the sidecar file when present.
    prior_mobs = dst / "mobs.base.csv"
    if prior_mobs.is_file():
        base_fields, base_rows = _read_mobs(prior_mobs)
        prior_mobs.unlink()
    fields = base_fields or upd_fields
    kept = [row for row in base_rows if str(row.get("zone") or "").strip() not in names]
    merged = kept + upd_rows
    if fields and merged:
        with (dst / "mobs.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in merged:
                writer.writerow(row)

    note = update / "SOURCES.md"
    dest_note = dst / "SOURCES.md"
    if note.is_file():
        incoming = note.read_text(encoding="utf-8").strip()
        current_text = dest_note.read_text(encoding="utf-8") if dest_note.is_file() else ""
        # copy_allowlist already wrote the update note. If a base note was
        # saved, append the update once.
        base_note = dst / "SOURCES.base.md"
        if base_note.is_file():
            current_text = base_note.read_text(encoding="utf-8")
            base_note.unlink()
        if incoming and incoming not in current_text:
            joined = current_text.rstrip() + "\n\n" + incoming + "\n" if current_text.strip() else incoming + "\n"
            dest_note.write_text(joined, encoding="utf-8")


def install_packaged_zones(dst: Path, external: Path | None, update: Path | None) -> None:
    """Build desktop/resources zone data. Raises when the index is missing."""
    dst.mkdir(parents=True, exist_ok=True)
    use_external = False
    if external and (external / "zones_index.json").is_file():
        try:
            use_external = external.resolve() != dst.resolve()
        except OSError:
            use_external = True
    if use_external and external is not None:
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)
        copy_allowlist(external, dst)
    if update and (update / "zones_index.json").is_file():
        prior_index = dst / "zones_index.json"
        if prior_index.is_file():
            shutil.copy2(prior_index, dst / "zones_index.base.json")
            mobs = dst / "mobs.csv"
            if mobs.is_file():
                shutil.copy2(mobs, dst / "mobs.base.csv")
            sources = dst / "SOURCES.md"
            if sources.is_file():
                shutil.copy2(sources, dst / "SOURCES.base.md")
        merge_zone_update(dst, update)
    index = dst / "zones_index.json"
    if not index.is_file() or index.is_symlink():
        raise RuntimeError(f"packaged zone index missing: {index}")
