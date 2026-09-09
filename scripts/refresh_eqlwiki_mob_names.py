#!/usr/bin/env python3
"""Refresh decoded/eqlwiki_mob_names.json from eqlwiki NPC categories.

Never invents mobs or kinds. Classification:
  - raid: Category:Raid Encounters
  - named: Category:Named Mobs without leading A/An (and not raid)
  - standard: Category:Named Mobs with leading A/An (and not raid)
  - mini_boss: names linked from Plane of Hate "Map Locations" (documented wiki list)
  - merchant: Category:Merchants (kept for search; not a combat kind filter)

Writes both desktop bundle and data/decoded when present.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTS = [
    ROOT / "desktop" / "resources" / "data" / "decoded" / "eqlwiki_mob_names.json",
    ROOT / "data" / "decoded" / "eqlwiki_mob_names.json",
]
API = "https://eqlwiki.com/api.php"
UA = {"User-Agent": "eq-legends-bis/1.0 (eqlwiki mob-name refresh)"}

_ARTICLE = re.compile(r"^(a|an)\s+", re.I)
_SKIP_PREFIX = ("Category:", "File:", "Template:", "User:", "Talk:", "Help:", "EQLwiki:", "Special:")


def api(params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API}?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
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
        time.sleep(0.08)
    return out


def hate_map_minibosses() -> set[str]:
    """Plane of Hate map-location named encounters (eqlwiki Plane of Hate)."""
    try:
        data = api({
            "action": "parse",
            "page": "Plane of Hate",
            "prop": "wikitext",
            "format": "json",
        })
    except Exception:
        return set()
    wt = ((data.get("parse") or {}).get("wikitext") or {}).get("*") or ""
    # Only the Map Locations section (before next == heading)
    m = re.search(r"==\s*Map Locations\s*==([\s\S]*?)(?:\n==\s|\Z)", wt, re.I)
    section = m.group(1) if m else ""
    names: set[str] = set()
    for link in re.findall(r"\[\[([^|\]]+)(?:\|[^\]]*)?\]\]", section):
        title = link.strip()
        if not title or title.startswith(_SKIP_PREFIX) or title.startswith("File:"):
            continue
        # Skip armor / zone meta links
        low = title.lower()
        if any(x in low for x in ("armor", "map of", "plane of", "ethereal mist", "woven shadow", "apothic")):
            continue
        names.add(title)
    return names


def wiki_url(name: str) -> str:
    return f"https://eqlwiki.com/{urllib.parse.quote(name.replace(' ', '_'))}"


def main() -> None:
    print("Fetching Category:Raid Encounters…")
    raid = category_pages("Category:Raid Encounters")
    print(f"  {len(raid)}")
    print("Fetching Category:Named Mobs…")
    named_cat = category_pages("Category:Named Mobs")
    print(f"  {len(named_cat)}")
    print("Fetching Category:Merchants…")
    merchants = category_pages("Category:Merchants")
    print(f"  {len(merchants)}")
    print("Parsing Plane of Hate Map Locations for mini bosses…")
    mini = hate_map_minibosses()
    print(f"  {len(mini)}")

    by_name: dict[str, dict] = {}

    def ensure(name: str) -> dict:
        row = by_name.get(name)
        if not row:
            row = {
                "name": name,
                "kinds": [],
                "wiki_categories": [],
                "url": wiki_url(name),
            }
            by_name[name] = row
        return row

    for name in sorted(raid):
        row = ensure(name)
        row["wiki_categories"].append("Raid Encounters")
        if "raid" not in row["kinds"]:
            row["kinds"].append("raid")

    for name in sorted(named_cat):
        row = ensure(name)
        if "Named Mobs" not in row["wiki_categories"]:
            row["wiki_categories"].append("Named Mobs")
        if "raid" in row["kinds"]:
            continue
        kind = "standard" if _ARTICLE.match(name) else "named"
        if kind not in row["kinds"]:
            row["kinds"].append(kind)

    for name in sorted(mini):
        row = ensure(name)
        if "Plane of Hate Map Locations" not in row["wiki_categories"]:
            row["wiki_categories"].append("Plane of Hate Map Locations")
        if "mini_boss" not in row["kinds"]:
            row["kinds"].append("mini_boss")
        # Hate map bosses that aren't raid stay searchable as named too
        if "raid" not in row["kinds"] and "named" not in row["kinds"] and "standard" not in row["kinds"]:
            row["kinds"].append("named")

    for name in sorted(merchants):
        row = ensure(name)
        if "Merchants" not in row["wiki_categories"]:
            row["wiki_categories"].append("Merchants")
        if "merchant" not in row["kinds"]:
            row["kinds"].append("merchant")

    mobs = sorted(by_name.values(), key=lambda r: (r["name"] or "").lower())
    counts = {
        "all": len(mobs),
        "raid": sum(1 for m in mobs if "raid" in m["kinds"]),
        "mini_boss": sum(1 for m in mobs if "mini_boss" in m["kinds"]),
        "named": sum(1 for m in mobs if "named" in m["kinds"]),
        "standard": sum(1 for m in mobs if "standard" in m["kinds"]),
        "merchant": sum(1 for m in mobs if "merchant" in m["kinds"]),
    }
    payload = {
        "source": "eqlwiki",
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Kinds from eqlwiki only: Raid Encounters; Named Mobs split by leading A/An "
            "(standard vs named); Plane of Hate Map Locations as mini_boss; Merchants tagged."
        ),
        "counts": counts,
        "mobs": mobs,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    for out in OUTS:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")
            print(f"Wrote {out} ({counts})")
        except Exception as e:
            print(f"Skip {out}: {e}")


if __name__ == "__main__":
    main()
