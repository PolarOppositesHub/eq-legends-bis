#!/usr/bin/env python3
"""Decode already-fetched / curl-fetched guarded API payloads."""
from __future__ import annotations

import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path

import os
from pathlib import Path as _Path

def _resolve_root():
    for key in ("EQ_LEGENDS_ROOT", "EQ_APP_ROOT"):
        v = os.environ.get(key)
        if v and _Path(v).exists():
            return _Path(v)
    if (_Path("/workspace/eq-legends") / "decoded").exists():
        return _Path("/workspace/eq-legends")
    data = os.environ.get("EQ_LEGENDS_DATA") or os.environ.get("EQ_DATA_ROOT")
    if data:
        d = _Path(data)
        return d.parent if d.name == "decoded" else d
    return _Path(__file__).resolve().parent

def _resolve_out(root):
    data = os.environ.get("EQ_LEGENDS_DATA") or os.environ.get("EQ_DATA_ROOT")
    if data and _Path(data).exists():
        return _Path(data)
    if (root / "decoded").exists():
        return root / "decoded"
    app_data = _Path(__file__).resolve().parents[2] / "data" / "decoded"
    if app_data.exists():
        return app_data
    return root / "decoded"

ROOT = _resolve_root()
OUT = _resolve_out(ROOT)
RUNTIME = ROOT / "catalog-runtime.js"
BASE = "https://eqlegendstools.com"

ALL_CLASSES = [
    "Bard", "Beastlord", "Berserker", "Cleric", "Druid", "Enchanter",
    "Magician", "Monk", "Necromancer", "Paladin", "Ranger", "Rogue",
    "Shadow Knight", "Shaman", "Warrior", "Wizard",
]

# Filled in main() from catalog-runtime.js / e_meta.json bis map + catalog/aggregate
ENDPOINTS: dict[str, str] = {}

CURL_HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "-H", "Accept: application/json",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Origin: https://eqlegendstools.com",
    "-H", "Referer: https://eqlegendstools.com/bis-gear/",
    "-H", "Sec-Fetch-Dest: empty",
    "-H", "Sec-Fetch-Mode: cors",
    "-H", "Sec-Fetch-Site: same-origin",
]

SCALABLE_STATS = {
    "AC", "HP", "MANA", "STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA", "END", "ATK",
    "SVM", "SVF", "SVC", "SVD", "SVP", "SVV",
}


def extract_meta(runtime_path: Path) -> dict:
    s = runtime_path.read_text(encoding="utf-8")
    start = s.find("const e=")
    if start < 0:
        raise RuntimeError("const e= not found")
    i = start + len("const e=")
    depth = 0
    end = None
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    tmp = ROOT / "_e_eval.js"
    tmp.write_text("const e=" + s[i:end] + ";\nprocess.stdout.write(JSON.stringify(e));\n", encoding="utf-8")
    out = subprocess.check_output(["node", str(tmp)], text=True)
    tmp.unlink(missing_ok=True)
    return json.loads(out)


def caesar(text: str, letter_shift: int, digit_shift: int) -> str:
    out = []
    for ch in str(text):
        o = ord(ch)
        if 65 <= o <= 90:
            out.append(chr(65 + (o - 65 + letter_shift) % 26))
        elif 97 <= o <= 122:
            out.append(chr(97 + (o - 97 + letter_shift) % 26))
        elif 48 <= o <= 57:
            out.append(chr(48 + (o - 48 + digit_shift) % 10))
        else:
            out.append(ch)
    return "".join(out)


def make_decoder(meta: dict):
    t, d, o, m, k, j = meta["t"], meta["d"], meta["o"], meta["m"], meta["k"], meta["j"]
    ident = set(meta["ident"])
    rk = meta["rk"]

    def decode(value, key: str = ""):
        if isinstance(value, str):
            return caesar(value, -t, -d)
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, int) and key not in ident:
            num = (value - o) / m
            if not float(num).is_integer():
                raise ValueError(f"Catalog data mismatch for key={key!r} value={value}")
            return int(num)
        if isinstance(value, float):
            return value
        if isinstance(value, list):
            return [decode(x, "") for x in value]
        if isinstance(value, dict):
            out = {}
            for raw_key, raw_val in value.items():
                if raw_key in rk:
                    new_key = caesar(rk[raw_key], -t, -d)
                elif str(raw_key).startswith("_"):
                    new_key = caesar(str(raw_key)[1:], -k, -j)
                else:
                    new_key = raw_key
                out[new_key] = decode(raw_val, new_key)
            return out
        return value

    def decode_catalog(bundle: dict) -> dict:
        rev = meta["rev"]
        decoded = {rev.get(k, k): decode(v, rev.get(k, k)) for k, v in bundle.items()}
        for w in decoded.get("weapons") or []:
            if not isinstance(w, dict) or "dps" in w:
                continue
            dmg, dly = w.get("dmg"), w.get("dly")
            dm_key = meta.get("dm", "__v")
            if dm_key in w:
                w["dps"] = float(w.pop(dm_key))
            elif isinstance(dmg, (int, float)) and isinstance(dly, (int, float)) and dly:
                w["dps"] = float(f"{dmg / dly:.4f}")
        return decoded

    return decode, decode_catalog


def curl_fetch(path: str, dest: Path) -> None:
    url = BASE + path
    cmd = ["curl", "-sS", "-f", "-o", str(dest), *CURL_HEADERS, url]
    subprocess.check_call(cmd)


def scale_item_stat(base, level: int):
    try:
        o = float(base or 0)
    except (TypeError, ValueError):
        return base
    if not o or not level:
        return int(o) if float(o).is_integer() else o
    a = math.floor(o * (1 + level / 10))
    if o > 0:
        return max(a, o + level)
    if o < -10:
        return math.ceil(o * max(0, 10 - level) / 10)
    return min(0, o + level)


def scale_stats(stats: dict | None, level: int) -> dict:
    if not stats:
        return {}
    out = {}
    for k, v in stats.items():
        if k == "DMG":
            try:
                base = float(v)
                out[k] = math.floor(base * (1 + level / 10)) if level else (
                    int(base) if float(base).is_integer() else base
                )
            except (TypeError, ValueError):
                out[k] = v
        elif k in SCALABLE_STATS:
            out[k] = scale_item_stat(v, level)
        else:
            out[k] = v
    return out


def slugify_name(name: str) -> str:
    s = name.strip().lower().replace("`", "").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_slug_map() -> dict[str, str]:
    path = ROOT / "item-urls.txt"
    mapping: dict[str, str] = {}
    if not path.exists():
        return mapping
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"https?://eqlegendstools\.com/items/([^/]+)/?", line.strip())
        if not m:
            continue
        slug = m.group(1)
        if slug in {"weapons", "gear", "clickies", "focus-effects", "worn-effects"}:
            continue
        mapping[slug] = slug
        mapping[slug.replace("-", "")] = slug
    return mapping


def item_url(name: str, slug_map: dict[str, str]) -> str:
    slug = slugify_name(name)
    if slug in slug_map:
        slug = slug_map[slug]
    elif slug.replace("-", "") in slug_map:
        slug = slug_map[slug.replace("-", "")]
    return f"https://eqlegendstools.com/items/{slug}/"


def extract_effect(item: dict) -> str:
    special = item.get("special") or []
    if special:
        return "; ".join(str(x) for x in special if x)
    effects = []
    for line in item.get("tooltipLines") or []:
        if re.match(
            r"^(Effect|Clicky Effect|Focus Effect|Worn Effect|Proc Effect|Clicky|Focus|Worn)\s*:",
            str(line),
            re.I,
        ):
            effects.append(str(line))
    return "; ".join(effects)


def extract_delay(item, weapons_by_name, weapons_by_id):
    stats = item.get("stats") or {}
    if "DLY" in stats:
        return stats["DLY"]
    for line in item.get("tooltipLines") or []:
        m = re.search(r"(?:Atk )?Delay:\s*(\d+)", str(line), re.I)
        if m:
            return int(m.group(1))
    name = item.get("name") or ""
    wid = item.get("itemID")
    w = weapons_by_id.get(wid) if wid is not None else None
    if w is None:
        w = weapons_by_name.get(name)
    if w and w.get("dly") is not None:
        return w["dly"]
    return None


def extract_dmg(item, weapons_by_name, weapons_by_id):
    stats = item.get("stats") or {}
    if "DMG" in stats:
        return stats["DMG"]
    for line in item.get("tooltipLines") or []:
        m = re.search(r"^DMG:\s*(-?\d+)", str(line), re.I)
        if m:
            return int(m.group(1))
    name = item.get("name") or ""
    wid = item.get("itemID")
    w = weapons_by_id.get(wid) if wid is not None else None
    if w is None:
        w = weapons_by_name.get(name)
    if w and w.get("dmg") is not None:
        return w["dmg"]
    return None



def normalize_classes(classes):
    if classes is None:
        return []
    if isinstance(classes, str):
        s = classes.strip()
        if not s:
            return []
        if s.upper() == "ALL":
            return ["ALL"]
        return [p.strip() for p in s.split(",") if p.strip()]
    if isinstance(classes, list):
        out = []
        for c in classes:
            out.extend(normalize_classes(c))
        return out
    return [str(classes)]


WORN_HASTE_PAT = re.compile(r"^Haste:\s*\+?(-?\d+)%?\s*$", re.I)


def extract_haste(item) -> int | None:
    """Parse worn haste percent from stats or tooltipLines (not spell/focus haste)."""
    stats = item.get("stats") or {}
    for key in ("Haste", "haste", "HASTE"):
        if key in stats and stats[key] is not None:
            try:
                return int(float(stats[key]))
            except (TypeError, ValueError):
                pass
    for line in item.get("tooltipLines") or []:
        m = WORN_HASTE_PAT.match(str(line).strip())
        if m:
            return int(m.group(1))
    return None


def flatten_item(item, bis_classes, slug_map, weapons_by_name, weapons_by_id):
    stats0 = dict(item.get("stats") or {})
    dmg0 = extract_dmg(item, weapons_by_name, weapons_by_id)
    dly = extract_delay(item, weapons_by_name, weapons_by_id)
    haste = extract_haste(item)
    if dmg0 is not None and "DMG" not in stats0:
        stats0["DMG"] = dmg0
    if dly is not None and "DLY" not in stats0:
        stats0["DLY"] = dly
    if haste is not None:
        stats0["Haste"] = haste

    # Haste / DLY / elemental bonus DMG do not scale with upgrade level
    nonscale = {"DLY", "Haste", "FIRE_DMG", "COLD_DMG"}
    stats10 = scale_stats({k: v for k, v in stats0.items() if k not in nonscale}, 10)
    for k in nonscale:
        if k in stats0:
            stats10[k] = stats0[k]

    dmg10 = stats10.get("DMG", dmg0)
    ratio0 = round(float(dmg0) / float(dly), 4) if dmg0 is not None and dly else None
    ratio10 = round(float(dmg10) / float(dly), 4) if dmg10 is not None and dly else None

    drops = item.get("dropsFrom") or []
    mobs, zones = [], []
    for d in drops:
        if isinstance(d, dict):
            if d.get("npc"):
                mobs.append(str(d["npc"]))
            if d.get("location"):
                zones.append(str(d["location"]))
        else:
            mobs.append(str(d))
    zone = item.get("sourceZone") or (", ".join(dict.fromkeys(zones)) if zones else "")
    if not zone and item.get("sourceZones"):
        zone = ", ".join(item["sourceZones"])

    quests = item.get("rewardFromQuests") or []
    quest_src = "; ".join(str(q) for q in quests if q)
    if not quest_src:
        quest_src = item.get("source") or ""

    name = item.get("name") or ""
    classes = normalize_classes(item.get("classes"))
    return {
        "name": name,
        "itemID": item.get("itemID"),
        "slots": item.get("slots") or [],
        "slot": " / ".join(item.get("slots") or []),
        "classes": classes,
        "classes_str": ", ".join(classes),
        "bis_for": bis_classes,
        "bis_for_str": ", ".join(bis_classes),
        "zone": zone,
        "drops_mobs": ", ".join(dict.fromkeys(mobs)),
        "quest_source": quest_src,
        "source": item.get("source") or "",
        "level": item.get("minLevel"),
        "effect": extract_effect(item),
        "flags": item.get("flags") or "",
        "url": item_url(name, slug_map) if name else "",
        "stats_plus0": stats0,
        "stats_plus10": stats10,
        "ratio_plus0": ratio0,
        "ratio_plus10": ratio10,
        "tooltipLines": item.get("tooltipLines") or [],
        "__catalogOrder": item.get("__catalogOrder"),
    }


def build_endpoints(meta: dict) -> dict[str, str]:
    """Build catalog + aggregate + all 16 class BiS API paths from runtime meta."""
    endpoints = {
        "catalog": meta.get("catalog") or "/api/r/54d677b1bf4b232e266192ea",
        "aggregate": meta.get("ba") or "/api/r/b000b8d9893ace54a420f407",
    }
    bis_map = meta.get("bis") or {}
    missing = [c for c in ALL_CLASSES if c not in bis_map]
    if missing:
        raise RuntimeError(f"Missing BiS endpoints in meta for: {missing}")
    for cls in ALL_CLASSES:
        endpoints[f"bis_{cls}"] = bis_map[cls]
    return endpoints


def main():
    global ENDPOINTS
    OUT.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT / "raw"
    raw_dir.mkdir(exist_ok=True)

    print("Loading meta ...")
    meta = extract_meta(RUNTIME)
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    decode, decode_catalog = make_decoder(meta)
    print(f"  version={meta.get('v')} rk={len(meta['rk'])}")

    ENDPOINTS = build_endpoints(meta)
    print(f"  endpoints: catalog + aggregate + {len(ALL_CLASSES)} class BiS bundles")

    # Prefer existing /tmp caches from earlier session curl, else curl again
    tmp_map = {
        "bis_Paladin": Path("/tmp/pal.bin"),
        "bis_Monk": Path("/tmp/mnk.bin"),
        "bis_Wizard": Path("/tmp/wiz.bin"),
        "aggregate": Path("/tmp/agg.bin"),
        "catalog": Path("/tmp/cat.bin"),
        "bis_Bard": Path("/tmp/bis_bard_test.json"),
    }

    decoded = {}
    for label, path in ENDPOINTS.items():
        dest = raw_dir / f"{label}.json"
        src = tmp_map.get(label)
        if src and src.exists() and src.stat().st_size > 100:
            print(f"Using cache {src} for {label}")
            raw = json.loads(src.read_text(encoding="utf-8"))
            dest.write_text(json.dumps(raw), encoding="utf-8")
        elif dest.exists() and dest.stat().st_size > 100:
            print(f"Using existing {dest}")
            raw = json.loads(dest.read_text(encoding="utf-8"))
        else:
            print(f"curl {label}: {path}")
            bin_dest = raw_dir / f"{label}.bin"
            curl_fetch(path, bin_dest)
            raw = json.loads(bin_dest.read_text(encoding="utf-8"))
            dest.write_text(json.dumps(raw), encoding="utf-8")

        data = decode_catalog(raw) if label == "catalog" else decode(raw)
        decoded[label] = data
        (OUT / f"{label}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        if isinstance(data, list):
            print(f"  -> {len(data)} items")
        else:
            print(f"  -> keys {list(data.keys())}")

    weapons = (decoded["catalog"].get("weapons") or []) if isinstance(decoded["catalog"], dict) else []
    weapons_by_name = {w.get("weaponName"): w for w in weapons if w.get("weaponName")}
    weapons_by_id = {w.get("itemID"): w for w in weapons if w.get("itemID") is not None}
    slug_map = load_slug_map()

    # Enrich catalog weapon tip haste into a lookup for flatten / later builders
    tips = (decoded["catalog"].get("tooltips") or {}) if isinstance(decoded["catalog"], dict) else {}
    tip_haste_by_name: dict[str, int] = {}
    for tip in tips.values():
        if not isinstance(tip, dict):
            continue
        nm = tip.get("name")
        if not nm:
            continue
        fake = {"stats": {}, "tooltipLines": tip.get("lines") or []}
        h = extract_haste(fake)
        if h is not None:
            tip_haste_by_name[nm] = h

    class_lists = {cls: decoded[f"bis_{cls}"] for cls in ALL_CLASSES}
    bis_membership: dict[str, set[str]] = {}
    by_key: dict[str, dict] = {}
    for cls, items in class_lists.items():
        for it in items:
            key = (it.get("name") or "").strip().lower()
            bis_membership.setdefault(key, set()).add(cls)
            prev = by_key.get(key)
            if prev is None:
                by_key[key] = it
            else:
                score = lambda x: (
                    len(x.get("stats") or {}),
                    len(x.get("tooltipLines") or []),
                    1 if x.get("itemID") is not None else 0,
                )
                if score(it) > score(prev):
                    by_key[key] = it

    order = list(ALL_CLASSES)

    def flatten_with_tip_haste(it, bis_for):
        row = flatten_item(it, bis_for, slug_map, weapons_by_name, weapons_by_id)
        # If BiS payload lacked worn haste lines, fall back to catalog tooltip
        if "Haste" not in (row.get("stats_plus0") or {}):
            h = tip_haste_by_name.get(row.get("name") or "")
            if h is not None:
                row["stats_plus0"]["Haste"] = h
                row["stats_plus10"]["Haste"] = h
        return row

    flat_all = []
    for key, it in by_key.items():
        bis_for = sorted(
            bis_membership.get(key, set()),
            key=lambda c: order.index(c) if c in order else 99,
        )
        flat_all.append(flatten_with_tip_haste(it, bis_for))
    flat_all.sort(key=lambda r: (r.get("__catalogOrder") is None, r.get("__catalogOrder") or 0, r["name"]))
    (OUT / "merged_all_class_bis.json").write_text(json.dumps(flat_all, indent=2), encoding="utf-8")
    # Keep legacy filename for builders that still reference it
    (OUT / "merged_three_class_bis.json").write_text(json.dumps(flat_all, indent=2), encoding="utf-8")

    per_class = {}
    for cls, items in class_lists.items():
        rows = []
        for it in items:
            name = (it.get("name") or "").strip().lower()
            bis_for = sorted(
                bis_membership.get(name, {cls}),
                key=lambda c: order.index(c) if c in order else 99,
            )
            rows.append(flatten_with_tip_haste(it, bis_for))
        rows.sort(key=lambda r: (r.get("__catalogOrder") is None, r.get("__catalogOrder") or 0, r["name"]))
        per_class[cls] = rows
        safe = cls.replace(" ", "_")
        (OUT / f"flat_{cls}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        if safe != cls:
            (OUT / f"flat_{safe}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    default_trio = {"Paladin", "Monk", "Wizard"}
    tri = [r for r in flat_all if set(r["bis_for"]) >= default_trio]
    usable_all_three = [
        r
        for r in flat_all
        if ("ALL" in set(r["classes"])) or default_trio <= set(r["classes"])
    ]
    (OUT / "tri_bis_intersection.json").write_text(json.dumps(tri, indent=2), encoding="utf-8")
    (OUT / "usable_all_three.json").write_text(json.dumps(usable_all_three, indent=2), encoding="utf-8")

    haste_items = [
        {
            "name": r["name"],
            "haste": (r.get("stats_plus0") or {}).get("Haste"),
            "slot": r.get("slot"),
            "bis_for": r.get("bis_for"),
        }
        for r in flat_all
        if (r.get("stats_plus0") or {}).get("Haste") is not None
    ]
    haste_items.sort(key=lambda x: (-(x["haste"] or 0), x["name"]))

    samples = []
    for c in ("Paladin", "Monk", "Wizard", "Warrior", "Cleric"):
        if per_class.get(c):
            samples.append(per_class[c][0])

    counts = {
        "catalog_weapons": len(weapons),
        "aggregate": len(decoded["aggregate"]) if isinstance(decoded["aggregate"], list) else None,
        "merged_unique": len(flat_all),
        "tri_bis_intersection_PAL_MNK_WIZ": len(tri),
        "usable_by_PAL_MNK_WIZ": len(usable_all_three),
        "items_with_worn_haste": len(haste_items),
        "catalog_tip_worn_haste": len(tip_haste_by_name),
    }
    for cls in ALL_CLASSES:
        counts[f"bis_{cls}"] = len(class_lists[cls])

    summary = {
        "source": BASE,
        "meta_version": meta.get("v"),
        "classes": list(ALL_CLASSES),
        "default_planner_trio": ["Paladin", "Monk", "Wizard"],
        "counts": counts,
        "haste_note": (
            "Worn haste parsed from tooltip 'Haste: +N%' (does not scale with upgrade). "
            "Spell/focus/effect haste text is NOT treated as worn haste. "
            "Only ONE worn haste item counts in a loadout; that item haste stacks with Cast Buffs spell haste."
        ),
        "haste_top": haste_items[:20],
        "upgrade_scaling": {
            "available": True,
            "note": "Site computes +0..+10 client-side; +10 columns derived with site formula from base stats.",
            "scalable_stats": sorted(SCALABLE_STATS | {"DMG"}),
            "non_scalable": ["DLY", "Haste", "FIRE_DMG", "COLD_DMG"],
        },
        "stat_keys_seen": dict(Counter(k for r in flat_all for k in (r.get("stats_plus0") or {}))),
        "sample_items": [
            {
                "name": s["name"],
                "slot": s["slot"],
                "classes": s["classes"],
                "bis_for": s["bis_for"],
                "zone": s["zone"],
                "drops_mobs": s["drops_mobs"],
                "level": s["level"],
                "effect": s["effect"],
                "stats_plus0": s["stats_plus0"],
                "stats_plus10": s["stats_plus10"],
                "url": s["url"],
            }
            for s in samples
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: counts[k] for k in counts if k.startswith("bis_") or k in (
        "catalog_weapons", "aggregate", "merged_unique", "items_with_worn_haste", "catalog_tip_worn_haste"
    )}, indent=2))
    for s in summary["sample_items"][:3]:
        print(f"SAMPLE {s['name']} | {s['slot']} | {s['stats_plus0']} -> +10 {s['stats_plus10']}")
    if haste_items:
        print(f"HASTE top: {haste_items[0]['name']} +{haste_items[0]['haste']}% ({len(haste_items)} items with worn haste)")
    print(f"Done -> {OUT}")


if __name__ == "__main__":
    main()
