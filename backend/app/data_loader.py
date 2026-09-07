"""Load decoded EQ Legends JSON — never invent stats."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .scoring import (
    ensure_planner_slots,
    is_weapon_item,
    item_haste,
    num,
    planner_slots_for,
    usable_by_all,
    usable_by_any,
    bis_overlap,
    tri_class_count,
)

from .paths import APP_ROOT, decoded_dir, legends_root

DATA = decoded_dir()
EQ_LEGENDS = legends_root()
SRC_DECODED = EQ_LEGENDS / "decoded" if (EQ_LEGENDS / "decoded").exists() else decoded_dir()

ALL_CLASSES = (
    "Bard", "Beastlord", "Berserker", "Cleric", "Druid", "Enchanter",
    "Magician", "Monk", "Necromancer", "Paladin", "Ranger", "Rogue",
    "Shadow Knight", "Shaman", "Warrior", "Wizard",
)
DEFAULT_TRIO = ("Paladin", "Monk", "Wizard")

CLASS_FILE = {
    "Shadow Knight": "Shadow Knight",
    # flat file exists as both "Shadow Knight" and "Shadow_Knight"
}


class DataStore:
    def __init__(self) -> None:
        self.root = DATA if DATA.exists() else SRC_DECODED
        self.summary: dict = {}
        self.catalog: dict = {}
        self.by_name: dict[str, dict] = {}
        self.by_id: dict[str, dict] = {}
        self.flat_by_class: dict[str, list] = {}
        self.loaded = False

    def decoded_path(self, name: str) -> Path:
        p = self.root / name
        if p.exists():
            return p
        return SRC_DECODED / name

    def load(self) -> None:
        self.summary = json.loads(self.decoded_path("summary.json").read_text(encoding="utf-8"))
        catalog_path = self.decoded_path("catalog.json")
        self.catalog = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else {}

        pool: dict[str, dict] = {}
        for cls in ALL_CLASSES:
            fname = f"flat_{cls}.json"
            path = self.decoded_path(fname)
            if not path.exists() and cls == "Shadow Knight":
                path = self.decoded_path("flat_Shadow_Knight.json")
            if not path.exists():
                # try bis_ as fallback and normalize
                bis = self.decoded_path(f"bis_{cls}.json")
                rows = json.loads(bis.read_text(encoding="utf-8")) if bis.exists() else []
                rows = [self._normalize_bis_row(r) for r in rows]
            else:
                rows = json.loads(path.read_text(encoding="utf-8"))
            self.flat_by_class[cls] = rows
            for r in rows:
                self._upsert(pool, r, cls)

        # Enrich weapons from catalog if missing / incomplete
        tips = self.catalog.get("tooltips") or {}
        for w in self.catalog.get("weapons") or []:
            name = w.get("weaponName") or ""
            if not name:
                continue
            key = name.strip().lower()
            tip = tips.get(name) if isinstance(tips, dict) else None
            # tooltips may be keyed differently
            if tip is None and isinstance(tips, dict):
                for tk, tv in tips.items():
                    if str(tk).strip().lower() == key:
                        tip = tv
                        break
            item = self._weapon_from_catalog(w, tip)
            if key in pool:
                existing = pool[key]
                if item.get("ratio_plus10") is not None:
                    existing["ratio_plus0"] = item.get("ratio_plus0")
                    existing["ratio_plus10"] = item.get("ratio_plus10")
                    existing["is_weapon"] = True
                    s0 = dict(existing.get("stats_plus0") or {})
                    s10 = dict(existing.get("stats_plus10") or {})
                    for k, v in (item.get("stats_plus0") or {}).items():
                        s0.setdefault(k, v)
                    for k, v in (item.get("stats_plus10") or {}).items():
                        if k not in s10 or abs(num(v)) > abs(num(s10.get(k))):
                            s10[k] = v
                    existing["stats_plus0"] = s0
                    existing["stats_plus10"] = s10
                # merge classes
                cl = list(dict.fromkeys((existing.get("classes") or []) + (item.get("classes") or [])))
                existing["classes"] = cl
                existing["classes_str"] = ", ".join(cl)
                existing["planner_slots"] = list(dict.fromkeys(
                    (existing.get("planner_slots") or []) + (item.get("planner_slots") or [])
                ))
            else:
                pool[key] = item

        self.by_name = pool
        self.by_id = {}
        for it in pool.values():
            iid = it.get("itemID")
            if iid is not None:
                self.by_id[str(iid)] = it
        self.loaded = True

    def _upsert(self, pool: dict, row: dict, cls: str) -> None:
        name = row.get("name") or ""
        if not name or name.strip().lower() == "none":
            return
        key = name.strip().lower()
        item = ensure_planner_slots(dict(row))
        item["is_weapon"] = is_weapon_item(item)
        if not item.get("planner_slots"):
            return
        existing = pool.get(key)
        if existing is None:
            # ensure bis_for list
            bf = list(item.get("bis_for") or [])
            if cls and cls not in bf:
                # flat file is that class's BiS list, but bis_for may already list many
                pass
            item["bis_for"] = bf
            item["classes_str"] = item.get("classes_str") or ", ".join(item.get("classes") or [])
            pool[key] = item
            return
        # merge
        for fld in ("zone", "drops_mobs", "quest_source", "url", "level", "effect", "classes_str"):
            if not existing.get(fld) and item.get(fld):
                existing[fld] = item[fld]
        bf = list(dict.fromkeys((existing.get("bis_for") or []) + (item.get("bis_for") or [])))
        existing["bis_for"] = bf
        cl = list(dict.fromkeys((existing.get("classes") or []) + (item.get("classes") or [])))
        existing["classes"] = cl
        existing["classes_str"] = ", ".join(cl)
        s_old = dict(existing.get("stats_plus10") or {})
        for k, v in (item.get("stats_plus10") or {}).items():
            if k not in s_old or abs(num(v)) > abs(num(s_old.get(k))):
                s_old[k] = v
        existing["stats_plus10"] = s_old
        s0 = dict(existing.get("stats_plus0") or {})
        for k, v in (item.get("stats_plus0") or {}).items():
            s0.setdefault(k, v)
        existing["stats_plus0"] = s0
        if item.get("ratio_plus10") is not None:
            existing["ratio_plus0"] = item.get("ratio_plus0")
            existing["ratio_plus10"] = item.get("ratio_plus10")
            existing["is_weapon"] = True
        existing["planner_slots"] = list(dict.fromkeys(
            (existing.get("planner_slots") or []) + (item.get("planner_slots") or [])
        ))
        if item.get("itemID") and not existing.get("itemID"):
            existing["itemID"] = item["itemID"]

    def _normalize_bis_row(self, r: dict) -> dict:
        """Convert raw bis_*.json (stats dict) into flat-like shape if needed."""
        if r.get("stats_plus0") is not None or r.get("stats_plus10") is not None:
            return r
        stats0 = dict(r.get("stats") or {})
        # Parse haste from tooltip lines if present
        for line in r.get("tooltipLines") or []:
            s = str(line).strip()
            if s.lower().startswith("haste:"):
                try:
                    h = int("".join(ch for ch in s.split(":", 1)[1] if ch.isdigit() or ch == "-"))
                    stats0["Haste"] = h
                except ValueError:
                    pass
        stats10 = {}
        for k, v in stats0.items():
            if k in ("Haste", "DLY", "FIRE_DMG", "COLD_DMG"):
                stats10[k] = v
            elif k == "DMG":
                try:
                    stats10[k] = float(math.floor(float(v) * 2))
                except (TypeError, ValueError):
                    stats10[k] = v
            else:
                try:
                    o = float(v)
                    a = math.floor(o * 2)  # level 10 => * (1+10/10)
                    stats10[k] = float(max(a, o + 10)) if o > 0 else o
                except (TypeError, ValueError):
                    continue
        out = dict(r)
        out["stats_plus0"] = stats0
        out["stats_plus10"] = stats10
        out["zone"] = r.get("zone") or r.get("sourceZone") or ""
        out["level"] = r.get("level") if r.get("level") is not None else r.get("minLevel")
        out["classes_str"] = r.get("classes_str") or ", ".join(r.get("classes") or [])
        return out

    def _weapon_from_catalog(self, w: dict, tip: Any) -> dict:
        from .scoring import SLOT_ALIASES

        name = w.get("weaponName") or ""
        classes = list(w.get("classNames") or [])
        bases = [str(s).strip().upper() for s in (w.get("slots") or [])]
        # normalize RANGED -> RANGE
        bases = ["RANGE" if b == "RANGED" else b for b in bases]
        planner = []
        for b in bases:
            planner.extend(SLOT_ALIASES.get(b, []))
        planner = list(dict.fromkeys(planner))

        tip_stats: dict = {}
        if isinstance(tip, dict):
            import re
            pat = re.compile(
                r"(AC|HP|MANA|END|STR|STA|AGI|DEX|WIS|INT|CHA|ATK|DMG|Haste|"
                r"SV FIRE|SV COLD|SV MAGIC|SV POISON|SV DISEASE|SV VOID)\s*:\s*\+?(-?\d+)",
                re.I,
            )
            mmap = {
                "AC": "AC", "HP": "HP", "MANA": "MANA", "END": "END",
                "STR": "STR", "STA": "STA", "AGI": "AGI", "DEX": "DEX",
                "WIS": "WIS", "INT": "INT", "CHA": "CHA", "ATK": "ATK",
                "DMG": "DMG", "HASTE": "Haste",
                "SV FIRE": "SVF", "SV COLD": "SVC", "SV MAGIC": "SVM",
                "SV POISON": "SVP", "SV DISEASE": "SVD", "SV VOID": "SVV",
            }
            for line in tip.get("lines") or []:
                for m in pat.finditer(str(line)):
                    key = mmap.get(m.group(1).upper())
                    if key:
                        tip_stats[key] = int(m.group(2))
                m2 = re.search(r"Atk Delay:\s*(\d+)", str(line), re.I)
                if m2:
                    tip_stats["DLY"] = int(m2.group(1))

        dmg0 = w.get("dmg")
        dly = w.get("dly") if w.get("dly") is not None else tip_stats.get("DLY")
        if dmg0 is None and tip_stats.get("DMG") is not None:
            dmg0 = tip_stats.get("DMG")
        dmg10 = None
        if dmg0 is not None:
            try:
                dmg10 = float(math.floor(float(dmg0) * 2))
            except (TypeError, ValueError):
                dmg10 = None

        s0 = {k: v for k, v in tip_stats.items() if k not in ("DMG", "DLY")}
        if dmg0 is not None:
            s0["DMG"] = dmg0
        if dly is not None:
            s0["DLY"] = dly
        s10 = {}
        for k, v in s0.items():
            if k in ("Haste", "DLY", "FIRE_DMG", "COLD_DMG"):
                s10[k] = v
            elif k == "DMG":
                s10[k] = dmg10 if dmg10 is not None else v
            else:
                try:
                    o = float(v)
                    a = math.floor(o * 2)
                    s10[k] = float(max(a, o + 10)) if o > 0 else o
                except (TypeError, ValueError):
                    pass
        if dly is not None:
            s10["DLY"] = float(dly)

        def ratio(dmg, delay):
            try:
                d, y = float(dmg), float(delay)
                if y == 0:
                    return None
                return round(d / y, 4)
            except (TypeError, ValueError):
                return None

        zone = w.get("sourceZone") or ""
        return {
            "name": name,
            "itemID": w.get("itemID"),
            "slot": " / ".join(bases),
            "slots": bases,
            "planner_slots": planner,
            "classes": classes,
            "classes_str": ", ".join(classes),
            "bis_for": [],
            "zone": zone,
            "drops_mobs": "",
            "quest_source": w.get("source") or "",
            "level": w.get("minLevel"),
            "effect": "",
            "url": "",
            "stats_plus0": s0,
            "stats_plus10": s10,
            "ratio_plus0": ratio(dmg0, dly),
            "ratio_plus10": ratio(dmg10, dly),
            "is_weapon": True,
        }

    def filter_pool(
        self,
        classes: list[str],
        *,
        require_all: bool = True,
    ) -> list[dict]:
        selected = set(classes)
        out = []
        for item in self.by_name.values():
            cl = item.get("classes") or []
            ok = usable_by_all(cl, selected) if require_all else usable_by_any(cl, selected)
            if not ok:
                continue
            it = dict(item)
            it["bis_overlap"] = bis_overlap(it.get("bis_for"), selected)
            it["tri_classes"] = tri_class_count(cl, selected)
            it["planner_slots"] = it.get("planner_slots") or planner_slots_for(it)
            out.append(it)
        return out

    def get_item(self, key: str) -> dict | None:
        if not key:
            return None
        if key in self.by_id:
            return self.by_id[key]
        if key.isdigit() and key in self.by_id:
            return self.by_id[key]
        return self.by_name.get(key.strip().lower())


store = DataStore()
