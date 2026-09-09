#!/usr/bin/env python3
"""Refresh data/decoded/eqlwiki_item_names.json from eqlwiki Category:Items.

Name recognition only — never invents item stats. Run when wiki coverage drifts.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "decoded" / "eqlwiki_item_names.json"
API = "https://eqlwiki.com/api.php"
UA = {"User-Agent": "eq-legends-bis/1.0 (eqlwiki item-name refresh)"}

SEED_CATS = [
    "Category:Items",
    "Category:Equipment",
    "Category:Weapons",
    "Category:Armor",
    "Category:Jewelry",
    "Category:Food",
    "Category:Containers",
]


def api(params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API}?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    all_titles: set[str] = set()
    seen_cats: set[str] = set()
    queue = list(SEED_CATS)
    depth = 0
    while queue and depth < 4:
        depth += 1
        nxt: list[str] = []
        for cat in queue:
            if cat in seen_cats:
                continue
            seen_cats.add(cat)
            cont = None
            while True:
                params = {
                    "action": "query",
                    "list": "categorymembers",
                    "cmtitle": cat,
                    "cmlimit": "500",
                    "format": "json",
                    "cmtype": "page|subcat",
                }
                if cont:
                    params["cmcontinue"] = cont
                data = api(params)
                for m in (data.get("query") or {}).get("categorymembers") or []:
                    title = m.get("title") or ""
                    if m.get("ns") == 14:
                        if title and title not in seen_cats:
                            nxt.append(title)
                    elif title:
                        all_titles.add(title)
                cont = (data.get("continue") or {}).get("cmcontinue")
                if not cont:
                    break
                time.sleep(0.1)
            time.sleep(0.1)
        queue = nxt

    skip = ("Category:", "File:", "Template:", "User:", "Talk:", "Help:", "EQLwiki:", "Special:")
    items = sorted(t for t in all_titles if not t.startswith(skip))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "source": "https://eqlwiki.com Category:Items (+subcats)",
                "count": len(items),
                "names": items,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(items)} names -> {OUT}")


if __name__ == "__main__":
    main()
