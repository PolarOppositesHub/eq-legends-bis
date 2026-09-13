#!/usr/bin/env python3
"""Tag eqlwiki_mob_names.json with EverQuest eras from eqlwiki era categories.

Never invents eras — only Category:Classic Era / Kunark Era / Velious Era and
plane era categories (Fear / Hate / Sky) from eqlwiki.

Writes desktop bundle, data/decoded, and packaging/required-decoded when present.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTS = [
    ROOT / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
    ROOT / "data" / "decoded" / "eqlwiki_mob_names.json",
    ROOT / "packaging" / "required-decoded" / "eqlwiki_mob_names.json",
]
API = "https://eqlwiki.com/api.php"
UA = {"User-Agent": "eq-legends-bis/1.0 (eqlwiki mob-era tag)"}

# Filter id → eqlwiki category title(s). Plane eras are grouped as "planes" in the UI.
ERA_CATEGORIES: list[tuple[str, str]] = [
    ("classic", "Category:Classic Era"),
    ("kunark", "Category:Kunark Era"),
    ("velious", "Category:Velious Era"),
    ("fear", "Category:Fear Era"),
    ("hate", "Category:Hate Era"),
    ("sky", "Category:Sky Era"),
]
ERA_ORDER = ("classic", "kunark", "velious", "fear", "hate", "sky")
_SKIP_PREFIX = ("Category:", "File:", "Template:", "User:", "Talk:", "Help:", "EQLwiki:", "Special:")


def api(params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API}?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def category_pages(cat: str) -> set[str]:
    out: set[str] = set()
    cont = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": cat,
            "cmlimit": "500",
            "format": "json",
            "cmtype": "page",
        }
        if cont:
            params["cmcontinue"] = cont
        data = api(params)
        for m in (data.get("query") or {}).get("categorymembers") or []:
            title = (m.get("title") or "").strip()
            if title and not title.startswith(_SKIP_PREFIX):
                out.add(title)
        cont = (data.get("continue") or {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(0.06)
    return out


def main() -> None:
    src = next((p for p in OUTS if p.is_file()), None)
    if not src:
        raise SystemExit("eqlwiki_mob_names.json not found — run refresh_eqlwiki_mob_names.py first")

    payload = json.loads(src.read_text(encoding="utf-8"))
    mobs = payload.get("mobs") or []
    if not isinstance(mobs, list) or not mobs:
        raise SystemExit("mob index empty")

    by_name = {(m.get("name") or "").strip(): m for m in mobs if isinstance(m, dict) and (m.get("name") or "").strip()}
    print(f"Index {len(by_name)} mobs from {src}")

    era_members: dict[str, set[str]] = {}
    for era_id, cat in ERA_CATEGORIES:
        print(f"Fetching {cat}…")
        pages = category_pages(cat)
        era_members[era_id] = pages
        print(f"  {len(pages)} pages · {len(pages & set(by_name))} in mob index")

    # Reset then apply
    for row in by_name.values():
        row["eras"] = []

    for era_id in ERA_ORDER:
        for name in era_members.get(era_id) or []:
            row = by_name.get(name)
            if not row:
                continue
            eras = row.setdefault("eras", [])
            if era_id not in eras:
                eras.append(era_id)

    for row in by_name.values():
        eras = [e for e in ERA_ORDER if e in (row.get("eras") or [])]
        row["eras"] = eras

    era_counts = {e: 0 for e in ERA_ORDER}
    tagged = 0
    for row in by_name.values():
        eras = row.get("eras") or []
        if eras:
            tagged += 1
        for e in eras:
            era_counts[e] = era_counts.get(e, 0) + 1
    era_counts["untagged"] = len(by_name) - tagged
    # UI bucket: planes = fear|hate|sky
    era_counts["planes"] = sum(
        1 for row in by_name.values()
        if any(e in (row.get("eras") or []) for e in ("fear", "hate", "sky"))
    )

    counts = dict(payload.get("counts") or {})
    counts["era"] = era_counts
    payload["counts"] = counts
    payload["eras"] = [
        {"id": "classic", "label": "Classic", "count": era_counts.get("classic", 0)},
        {"id": "kunark", "label": "Kunark", "count": era_counts.get("kunark", 0)},
        {"id": "velious", "label": "Velious", "count": era_counts.get("velious", 0)},
        {"id": "planes", "label": "Planes (Fear / Hate / Sky)", "count": era_counts.get("planes", 0)},
        {"id": "untagged", "label": "No era tag", "count": era_counts.get("untagged", 0)},
    ]
    payload["era_note"] = (
        "Eras from eqlwiki Category:Classic Era / Kunark Era / Velious Era "
        "and Fear/Hate/Sky Era categories. Not invented."
    )
    payload["eras_fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for out in OUTS:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"Wrote {out} (tagged {tagged}/{len(by_name)})")
        except Exception as e:
            print(f"Skip {out}: {e}")


if __name__ == "__main__":
    main()
