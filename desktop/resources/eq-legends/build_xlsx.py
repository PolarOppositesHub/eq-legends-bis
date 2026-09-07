#!/usr/bin/env python3
"""Build EQ_Legends_BiS.xlsx from decoded BiS JSON + catalog weapons (fixed)."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path("/workspace/eq-legends")
OUT = ROOT / "decoded"
XLSX = ROOT / "EQ_Legends_BiS.xlsx"
XLSX_FIXED = ROOT / "EQ_Legends_BiS_fixed.xlsx"

ALL_CLASSES = (
    "Bard", "Beastlord", "Berserker", "Cleric", "Druid", "Enchanter",
    "Magician", "Monk", "Necromancer", "Paladin", "Ranger", "Rogue",
    "Shadow Knight", "Shaman", "Warrior", "Wizard",
)
DEFAULT_TRIO = ("Paladin", "Monk", "Wizard")
TARGET_CLASSES = DEFAULT_TRIO  # planner / intersection default; sheets cover ALL_CLASSES


STAT_COLS = [
    ("AC", "AC"), ("HP", "HP"), ("MANA", "Mana"), ("END", "END"),
    ("STR", "STR"), ("STA", "STA"), ("AGI", "AGI"), ("DEX", "DEX"),
    ("WIS", "WIS"), ("INT", "INT"), ("CHA", "CHA"),
    ("SVF", "SV Fire"), ("SVC", "SV Cold"), ("SVM", "SV Magic"),
    ("SVP", "SV Poison"), ("SVD", "SV Disease"), ("SVV", "SV Void"),
    ("DMG", "DMG"), ("DLY", "DLY"), ("FIRE_DMG", "Fire DMG"),
    ("COLD_DMG", "Cold DMG"), ("ATK", "ATK"), ("Haste", "Haste"),
]

BASE_COLS = [
    ("bis_for_str", "BiS for"), ("classes_str", "Class(es)"), ("slot", "Slot"),
    ("name", "Item"), ("zone", "Zone"), ("drops_mobs", "Drops From / Mob(s)"),
    ("quest_source", "Quest/Source"), ("level", "Level"), ("effect", "Effect"),
    ("url", "Item URL"),
]

WEAPON_HEADERS = [
    "Class(es)", "Slot", "Item", "Zone", "Drops/Mobs", "Quest/Source", "Level",
    "1H/2H", "DMG +0", "DMG +10", "DLY", "Ratio +0", "Ratio +10",
    "Haste +0", "Haste +10", "Proc/Effect", "URL",
]

WORN_HASTE_PAT = re.compile(r"^Haste:\s*\+?(-?\d+)%?\s*$", re.I)


def tip_haste(tip) -> int | None:
    if not tip:
        return None
    for line in tip.get("lines") or []:
        m = WORN_HASTE_PAT.match(str(line).strip())
        if m:
            return int(m.group(1))
    return None


HIGHLIGHT = {
    "Truvinan": PatternFill("solid", fgColor="C6EFCE"),
    "Aldryn, Blade of the Ocean": PatternFill("solid", fgColor="FCE4D6"),
    "Thelvorn, Blade of Light": PatternFill("solid", fgColor="FFF2CC"),
    "Ghoulbane": PatternFill("solid", fgColor="DDEBF7"),
}

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)
THIN = Border(
    left=Side(style="thin", color="B0B0B0"),
    right=Side(style="thin", color="B0B0B0"),
    top=Side(style="thin", color="B0B0B0"),
    bottom=Side(style="thin", color="B0B0B0"),
)


def clean_num(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v
    return v


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
    if not name:
        return ""
    slug = slugify_name(name)
    if slug in slug_map:
        slug = slug_map[slug]
    elif slug.replace("-", "") in slug_map:
        slug = slug_map[slug.replace("-", "")]
    return f"https://eqlegendstools.com/items/{slug}/"


def scaled_dmg(dmg0, level: int = 10):
    """Match sample-item.html: Math.floor(dmg * (1 + t/10)); DLY does not scale."""
    if dmg0 is None:
        return None
    return int(math.floor(float(dmg0) * (1 + level / 10)))


def ratio(dmg, dly):
    if dmg is None or dly is None or float(dly) == 0:
        return None
    return round(float(dmg) / float(dly), 4)


def handedness(w: dict) -> str:
    oh = (w.get("oneHanded") or "").strip()
    if oh == "Yes":
        return "1H"
    if oh == "No":
        return "2H"
    if oh == "Ranged":
        return "Ranged"
    slots = [s.upper() for s in (w.get("slots") or [])]
    if "RANGE" in slots or "RANGED" in slots or "AMMO" in slots:
        return "Ranged"
    return oh or ""


def format_drops(w: dict) -> str:
    entries = w.get("dropsFromEntries") or []
    parts = []
    for e in entries:
        if isinstance(e, dict):
            loc = e.get("location") or ""
            npc = e.get("npc") or ""
            if loc and npc:
                parts.append(f"{loc}: {npc}")
            elif npc:
                parts.append(str(npc))
            elif loc:
                parts.append(str(loc))
        else:
            parts.append(str(e))
    if parts:
        return "; ".join(dict.fromkeys(parts))
    return (w.get("dropsFrom") or "").strip()


def format_quest(w: dict) -> str:
    entries = w.get("questRewardEntries") or []
    if entries:
        return "; ".join(str(x) for x in entries if x)
    qr = w.get("questReward") or ""
    if qr:
        return str(qr)
    src = w.get("source") or ""
    if "quest" in src.lower() or "reward" in src.lower():
        return src
    return ""


def extract_effect_from_tip(tip) -> str:
    if not tip:
        return ""
    effects = []
    for line in tip.get("lines") or []:
        if re.match(
            r"^(Effect|Clicky Effect|Focus Effect|Worn Effect|Proc Effect|Clicky|Focus|Worn|Proc)\s*:",
            str(line),
            re.I,
        ):
            effects.append(str(line))
    return "; ".join(effects)


def build_tooltip_by_name(catalog: dict) -> dict:
    tips = catalog.get("tooltips") or {}
    by_name = {}
    for tip in tips.values():
        if isinstance(tip, dict) and tip.get("name"):
            by_name[tip["name"]] = tip
    return by_name


def load_rows(planner_classes=None):
    """Load merged BiS + per-class flats + catalog.

    planner_classes: 1–3 class names used for intersection / default planner pool.
    Defaults to Paladin+Monk+Wizard.
    """
    planner_classes = tuple(planner_classes or DEFAULT_TRIO)
    merged_path = OUT / "merged_all_class_bis.json"
    if not merged_path.exists():
        merged_path = OUT / "merged_three_class_bis.json"
    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    per = {}
    for cls in ALL_CLASSES:
        p = OUT / f"flat_{cls}.json"
        if not p.exists():
            p = OUT / f"flat_{cls.replace(' ', '_')}.json"
        if p.exists():
            per[cls] = json.loads(p.read_text(encoding="utf-8"))
        else:
            per[cls] = []
    # Intersection of planner trio BiS membership
    want = set(planner_classes)
    tri = [r for r in merged if set(r.get("bis_for") or []) >= want]
    # Prefer file if it matches default trio
    if want == set(DEFAULT_TRIO) and (OUT / "tri_bis_intersection.json").exists():
        tri = json.loads((OUT / "tri_bis_intersection.json").read_text(encoding="utf-8"))
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    catalog = json.loads((OUT / "catalog.json").read_text(encoding="utf-8"))
    return merged, per, tri, summary, catalog, planner_classes


def is_broken_weapon_row(r: dict) -> bool:
    """Drop nameless / None PRIMARY stubs and bogus weapon rows without names."""
    name = r.get("name") or r.get("item")
    if name is None or str(name).strip() == "" or str(name).strip().lower() == "none":
        return True
    slot = str(r.get("slot") or "").upper()
    if slot == "PRIMARY":
        s0 = r.get("stats_plus0") or {}
        dmg = s0.get("DMG")
        dly = s0.get("DLY")
        if (r.get("ratio_plus0") or r.get("ratio_plus10")) and dmg is None:
            return True
        if dmg is not None and dly is None and (r.get("ratio_plus0") or 0):
            if float(r.get("ratio_plus0") or 0) < 0.7:
                return True
    return False


def filter_gear_rows(rows):
    return [r for r in rows if not is_broken_weapon_row(r)]


def style_header(ws, ncols):
    for col in range(1, ncols + 1):
        cell = ws.cell(1, col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = THIN
    ws.freeze_panes = "A2"
    if ws.max_row >= 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{max(ws.max_row, 1)}"


def autosize(ws, max_width=42):
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        length = 0
        for cell in col[:80]:
            val = "" if cell.value is None else str(cell.value)
            length = max(length, min(len(val), max_width))
        ws.column_dimensions[letter].width = max(8, length + 2)


def headers():
    hdrs = [label for _, label in BASE_COLS]
    for key, label in STAT_COLS:
        hdrs.append(f"{label} +0")
        hdrs.append(f"{label} +10")
    hdrs.append("Ratio +0")
    hdrs.append("Ratio +10")
    return hdrs


def write_gear_rows(ws, rows):
    hdrs = headers()
    ws.append(hdrs)
    for r in rows:
        line = []
        for key, _ in BASE_COLS:
            line.append(r.get(key))
        s0 = r.get("stats_plus0") or {}
        s10 = r.get("stats_plus10") or {}
        for key, _ in STAT_COLS:
            v0 = s0.get(key)
            v10 = s10.get(key) if key != "DLY" else s0.get(key)
            line.append(clean_num(v0))
            line.append(clean_num(v10))
        line.append(clean_num(r.get("ratio_plus0")))
        line.append(clean_num(r.get("ratio_plus10")))
        ws.append(line)
    style_header(ws, len(hdrs))
    autosize(ws)
    url_col = [i for i, (_, lab) in enumerate(BASE_COLS, 1) if lab == "Item URL"][0]
    for row_idx in range(2, ws.max_row + 1):
        cell = ws.cell(row_idx, url_col)
        if cell.value:
            cell.hyperlink = cell.value
            cell.style = "Hyperlink"


def weapon_records(catalog: dict, slug_map: dict, target_classes=None, any_class: bool = False):
    """Build weapon rows. If any_class, include all catalog weapons; else filter to target_classes."""
    tips_by_name = build_tooltip_by_name(catalog)
    target = set(target_classes or TARGET_CLASSES)
    records = []
    for w in catalog.get("weapons") or []:
        classes = list(w.get("classNames") or [])
        if not any_class:
            if not (target.intersection(classes) or "ALL" in classes):
                continue
        name = w.get("weaponName") or ""
        if not name:
            continue
        dmg0 = w.get("dmg")
        dly = w.get("dly")
        dmg10 = scaled_dmg(dmg0, 10) if dmg0 is not None else None
        tip = tips_by_name.get(name)
        haste = tip_haste(tip)
        zone = w.get("sourceZone") or ""
        if not zone:
            locs = []
            for e in w.get("dropsFromEntries") or []:
                if isinstance(e, dict) and e.get("location"):
                    locs.append(str(e["location"]))
            zone = ", ".join(dict.fromkeys(locs))
        records.append(
            {
                "classes": classes,
                "classes_str": ", ".join(classes),
                "slot": " / ".join(w.get("slots") or []),
                "name": name,
                "zone": zone,
                "drops_mobs": format_drops(w),
                "quest_source": format_quest(w) or (w.get("source") or ""),
                "level": w.get("minLevel"),
                "hand": handedness(w),
                "dmg0": clean_num(dmg0),
                "dmg10": clean_num(dmg10),
                "dly": clean_num(dly),
                "ratio0": ratio(dmg0, dly),
                "ratio10": ratio(dmg10, dly),
                "haste0": clean_num(haste),
                "haste10": clean_num(haste),  # worn haste does not scale
                "effect": extract_effect_from_tip(tip),
                "url": item_url(name, slug_map),
                "itemID": w.get("itemID"),
            }
        )
    records.sort(key=lambda r: (-(r["ratio10"] or 0), r["name"]))
    return records


def write_weapon_sheet(ws, records, highlight: bool = False):
    ws.append(WEAPON_HEADERS)
    for rec in records:
        ws.append(
            [
                rec["classes_str"],
                rec["slot"],
                rec["name"],
                rec["zone"],
                rec["drops_mobs"],
                rec["quest_source"],
                clean_num(rec["level"]),
                rec["hand"],
                rec["dmg0"],
                rec["dmg10"],
                rec["dly"],
                rec["ratio0"],
                rec["ratio10"],
                rec.get("haste0"),
                rec.get("haste10"),
                rec["effect"],
                rec["url"],
            ]
        )
    style_header(ws, len(WEAPON_HEADERS))
    autosize(ws)
    url_col = WEAPON_HEADERS.index("URL") + 1
    name_col = WEAPON_HEADERS.index("Item") + 1
    for row_idx in range(2, ws.max_row + 1):
        cell = ws.cell(row_idx, url_col)
        if cell.value:
            cell.hyperlink = cell.value
            cell.style = "Hyperlink"
        if highlight:
            name = ws.cell(row_idx, name_col).value
            fill = HIGHLIGHT.get(name)
            if fill:
                for col in range(1, len(WEAPON_HEADERS) + 1):
                    ws.cell(row_idx, col).fill = fill


def write_how_to_use(wb, summary, weapon_counts):
    ws = wb.create_sheet("How to use", 0)
    lines = [
        "Josh's EverQuest Legends BiS Spreadsheet",
        "",
        "Source: https://eqlegendstools.com (fan site — not affiliated with Daybreak/EQ)",
        f"Catalog/runtime version: {summary.get('meta_version', 'unknown')} (site v4.8.x; data refreshed ~Sep 2 2026 per site activity text when captured)",
        "Data decoded from guarded /api/r/* BiS bundles + catalog (Paladin, Monk, Wizard).",
        "",
        "*** WEAPON BUG FIX (Sep 2026) ***",
        "Prior workbook versions were WRONG on weapons: BiS gear bundles barely include weapon rows,",
        "and PRIMARY rows sometimes showed Item=None with bogus ~0.65 ratios. Real weapons live in",
        "catalog.weapons (202 total). This rebuild adds dedicated weapon sheets from the catalog,",
        "uses catalog.weaponName, and computes DMG/Ratio with the site formula from sample-item.html:",
        "  scaledDamage = Math.floor(dmg * (1 + level/10));  Ratio = scaledDamage / delay;  DLY does NOT scale.",
        "Verified examples (Paladin):",
        "  Ghoulbane: 15/34 = 0.4412 @+0 → 30/34 = 0.8824 @+10",
        "  Aldryn, Blade of the Ocean: 20/26 = 0.7692 @+0 → 40/26 = 1.5385 @+10",
        "  Thelvorn, Blade of Light: same 20/26 → 40/26 = 1.5385 @+10",
        "  Truvinan: 32/40 = 0.8000 @+0 → 64/40 = 1.6000 @+10 (highest Paladin ratio in catalog)",
        "",
        "How to use",
        "1. Open the Class selector sheet and pick Paladin, Monk, Wizard, or All from the dropdown (cell B2).",
        "2. Use class sheets (Paladin / Monk / Wizard) for that class's BiS armor/jewelry/shield list from the site.",
        "3. Use 'Weapons (by class)' for ALL catalog weapons usable by Paladin, Monk, and/or Wizard (sorted by Ratio +10).",
        "4. Use 'Paladin weapons top' / 'Monk weapons top' / 'Wizard weapons top' for per-class rankings.",
        "   On Paladin weapons top: Truvinan (green), Aldryn (orange), Thelvorn (yellow), Ghoulbane (blue) are highlighted.",
        "5. Sheet 'PAL+MNK+WIZ BiS' = items that appear on ALL THREE class BiS lists (intersection).",
        "6. Sheet 'All gear (3 classes)' = unique union of the three BiS lists (nameless/broken weapon stubs removed).",
        "",
        "Upgrade levels (+0 vs +10)",
        "EQ Legends Tools scales item stats client-side for upgrade levels 0–10.",
        "Bundles/catalog store BASE (+0) stats only. This workbook applies the site's published formula:",
        "  scaleItemStat(base, level) ≈ floor(base * (1 + level/10)), with max(base+level, …) for positives,",
        "  and special handling for small negatives / large negatives (matches sample-item.html JS).",
        "Weapon DMG uses the same floor(dmg*(1+level/10)); at +10 that is floor(dmg*2).",
        "Scalable: AC, HP, MANA, STR, STA, AGI, DEX, WIS, INT, CHA, END, ATK, SV resists, DMG.",
        "Does NOT scale: DLY (delay), elemental bonus DMG (Fire/Cold DMG), effects/focus text, charges.",
        "Ratio = DMG / DLY when both known.",
        "",
        "Columns (weapons sheets)",
        "- Class(es): wearable classes from catalog.weapons.classNames",
        "- 1H/2H: from catalog oneHanded (Yes→1H, No→2H, Ranged→Ranged)",
        "- DMG +0 / DMG +10 / DLY / Ratio +0 / Ratio +10",
        "- Proc/Effect: Effect lines joined from catalog.tooltips when available",
        "- URL: https://eqlegendstools.com/items/<slug>/",
        "",
        "Gaps / caveats (fields left blank when missing — nothing invented)",
        "- BiS bundles still under-represent weapons; use the Weapons sheets for true weapon rankings.",
        "- Some gear items lack itemID, zone, drops, or level in the BiS payload.",
        "- Intermediate upgrade levels (+1…+9) are not separate columns; recompute with the formula if needed.",
        "- URLs may 404 if slugification differs from the live site.",
        "",
        "Counts (this build)",
        f"- Unique merged BiS (raw): {summary['counts']['merged_unique']}",
        f"- Intersection (all 3 BiS lists, raw): {summary['counts']['tri_bis_intersection']}",
        f"- Catalog weapons total: {weapon_counts['total']}",
        f"- Weapons usable by Paladin/Monk/Wizard: {weapon_counts['usable']}",
        f"- Paladin / Monk / Wizard weapon rows: {weapon_counts['Paladin']} / {weapon_counts['Monk']} / {weapon_counts['Wizard']}",
        f"- +0 and +10 both available: YES (+10 derived via site formula from +0 base stats)",
        "",
        "Credit: Item/BiS data © respective authors on eqlegendstools.com. Spreadsheet assembly for Josh Monroe.",
    ]
    section_headers = {
        "How to use",
        "Upgrade levels (+0 vs +10)",
        "Columns (weapons sheets)",
        "Gaps / caveats (fields left blank when missing — nothing invented)",
        "Counts (this build)",
        "*** WEAPON BUG FIX (Sep 2026) ***",
    }
    for i, line in enumerate(lines, 1):
        cell = ws.cell(i, 1, line)
        if i == 1:
            cell.font = Font(bold=True, size=16, color="1F4E79")
        elif line in section_headers:
            cell.font = Font(bold=True, size=12, color="1F4E79")
    ws.column_dimensions["A"].width = 120


def write_class_selector(wb, summary, weapon_counts, gear_counts, planner_classes=None):
    """Class selector: pick any 1–3 of the 16 classes (defaults Paladin/Monk/Wizard)."""
    planner_classes = list(planner_classes or DEFAULT_TRIO)
    while len(planner_classes) < 3:
        planner_classes.append("")
    planner_classes = planner_classes[:3]

    ws = wb.create_sheet("Class selector", 1)
    ws["A1"] = "Class filter (pick 1–3 of 16)"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Class 1:"
    ws["B2"] = planner_classes[0] or "Paladin"
    ws["A3"] = "Class 2:"
    ws["B3"] = planner_classes[1] if len(planner_classes) > 1 and planner_classes[1] else "(none)"
    ws["A4"] = "Class 3:"
    ws["B4"] = planner_classes[2] if len(planner_classes) > 2 and planner_classes[2] else "(none)"
    for cell in (ws["B2"], ws["B3"], ws["B4"]):
        cell.fill = PatternFill("solid", fgColor="FFF2CC")
        cell.font = Font(bold=True)

    class_list = ",".join(ALL_CLASSES) + ",(none)"
    dv = DataValidation(type="list", formula1=f'"{class_list}"', allow_blank=False)
    dv.error = "Pick a class or (none)"
    dv.errorTitle = "Invalid class"
    ws.add_data_validation(dv)
    dv.add(ws["B2"])
    dv.add(ws["B3"])
    dv.add(ws["B4"])

    ws["A6"] = "Instructions"
    ws["A6"].font = Font(bold=True)
    ws["A7"] = (
        "Choose up to three classes in B2–B4 (use (none) to leave a slot empty). "
        "Open the matching class BiS sheet and '… weapons top' sheet for that class. "
        "Stat planner scores are precomputed for the planner trio shown here at build time "
        f"(default {', '.join(DEFAULT_TRIO)}). "
        "ONLY ONE worn haste item counts in a loadout — highest Haste% wins; do not stack multiple haste pieces. "
        "Source: eqlegendstools.com"
    )
    ws.merge_cells("A7:B7")
    ws["A7"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[7].height = 60

    ws["A9"] = "Quick counts (BiS gear after stub filter)"
    ws["A9"].font = Font(bold=True)
    row = 10
    for cls in ALL_CLASSES:
        ws.cell(row, 1, f"{cls} gear")
        ws.cell(row, 2, gear_counts.get(cls, 0))
        row += 1
    ws.cell(row, 1, "Intersection (planner trio BiS)")
    ws.cell(row, 2, gear_counts.get("tri", 0))
    row += 1
    ws.cell(row, 1, "Unique union gear (all 16)")
    ws.cell(row, 2, gear_counts.get("merged", 0))
    row += 2

    ws.cell(row, 1, "Catalog weapons (usable by class)")
    ws.cell(row, 1).font = Font(bold=True)
    row += 1
    ws.cell(row, 1, "All catalog weapons")
    ws.cell(row, 2, weapon_counts.get("total", 0))
    row += 1
    ws.cell(row, 1, "Usable by planner trio")
    ws.cell(row, 2, weapon_counts.get("usable", 0))
    row += 1
    for cls in ALL_CLASSES:
        ws.cell(row, 1, f"{cls} weapons")
        ws.cell(row, 2, weapon_counts.get(cls, 0))
        row += 1

    row += 1
    ws.cell(row, 1, "Haste note")
    ws.cell(row, 1).font = Font(bold=True, size=12)
    row += 1
    ws.cell(row, 1, (
        "Worn haste is the tooltip line 'Haste: +N%' (shown as Haste +0 / Haste +10; value does not scale). "
        "Spell Haste / Summoning Haste focus effects are NOT worn haste. "
        "BiS loadout ranking picks at most ONE haste item (highest %); other haste pieces are ranked without double-counting."
    ))
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    ws.cell(row, 1).alignment = Alignment(wrap_text=True)
    ws.row_dimensions[row].height = 48

    row += 2
    ws.cell(row, 1, "Upgrade level reference")
    ws.cell(row, 1).font = Font(bold=True, size=12)
    row += 1
    ws.cell(row, 1, "Desired upgrade level (info only; sheets already show +0 and +10):")
    ws.cell(row, 2, 10)
    dv2 = DataValidation(type="list", formula1='"0,1,2,3,4,5,6,7,8,9,10"', allow_blank=False)
    ws.add_data_validation(dv2)
    dv2.add(ws.cell(row, 2))
    row += 1
    ws.cell(row, 1, (
        "Weapon DMG at level L: =FLOOR(DMG0*(1+L/10),1). Ratio = DMG/DLY (DLY unchanged). "
        "Haste does NOT scale. Other positive stats: =MAX(FLOOR(S*(1+L/10),1), S+L)."
    ))

    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 18



def main():
    merged, per, tri, summary, catalog, planner_classes = load_rows()
    slug_map = load_slug_map()

    weapons_all = weapon_records(catalog, slug_map, target_classes=planner_classes)
    weapons_catalog_all = weapon_records(catalog, slug_map, any_class=True)
    per_weapons = {
        cls: [w for w in weapons_catalog_all if cls in w["classes"] or "ALL" in w["classes"]]
        for cls in ALL_CLASSES
    }
    for cls in ALL_CLASSES:
        per_weapons[cls].sort(key=lambda r: (-(r["ratio10"] or 0), r["name"]))

    gear_per = {cls: filter_gear_rows(per.get(cls, [])) for cls in ALL_CLASSES}
    gear_tri = filter_gear_rows(tri)
    gear_merged = filter_gear_rows(merged)

    weapon_counts = {
        "total": len(catalog.get("weapons") or []),
        "usable": len(weapons_all),
    }
    for cls in ALL_CLASSES:
        weapon_counts[cls] = len(per_weapons[cls])

    gear_counts = {cls: len(gear_per[cls]) for cls in ALL_CLASSES}
    gear_counts["tri"] = len(gear_tri)
    gear_counts["merged"] = len(gear_merged)

    wb = Workbook()
    default = wb.active
    wb.remove(default)

    write_how_to_use(wb, summary, weapon_counts)
    write_class_selector(wb, summary, weapon_counts, gear_counts, planner_classes)

    ws_wep = wb.create_sheet("Weapons (by class)")
    write_weapon_sheet(ws_wep, weapons_all, highlight=True)

    trio_label = "+".join(
        {"Paladin": "PAL", "Monk": "MNK", "Wizard": "WIZ"}.get(c, c[:3].upper())
        for c in planner_classes
    )
    ws_tri = wb.create_sheet(f"{trio_label} BiS"[:31])
    write_gear_rows(ws_tri, gear_tri)

    for cls in ALL_CLASSES:
        ws = wb.create_sheet(cls[:31])
        write_gear_rows(ws, gear_per[cls])

    ws_all = wb.create_sheet("All gear (all classes)")
    write_gear_rows(ws_all, gear_merged)

    for cls in ALL_CLASSES:
        ws = wb.create_sheet(f"{cls} weapons top"[:31])
        write_weapon_sheet(ws, per_weapons[cls], highlight=(cls == "Paladin"))

    for path_out in (XLSX, XLSX_FIXED):
        wb.save(path_out)
        print(f"Wrote {path_out}")
    print("sheets:", wb.sheetnames)


if __name__ == "__main__":
    main()
