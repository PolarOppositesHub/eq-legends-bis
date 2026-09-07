# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.6** (local tree smoke-ready; Josh does Windows portable + gh release — do not package here)
Canonical: backend/app/{main,engine,scoring,ac_softcap,quest_guides,class_roles,item_catalog,weapon_dps,zones,inventory,races,paths}.py + frontend **App.jsx** (+ styles.css) + desktop/main.js

## Why 1.0.6 (Josh: import + Item Search 500s again; ~940 catalog)
- **Root cause (likely on Windows run):** `EQ_DATA_ROOT` pointed at missing `data/decoded` (symlink gitignored / not created) and `decoded_dir()` trusted the override even when absent → empty or brittle catalog path. Electron now probes multiple decoded candidates; `decoded_dir()` falls through when override missing.
- **Hardening:** `/api/item-search` and `/api/inventory/import` never uncaught-500; corrupt/missing JSON skipped; binary/.exe still **400** with Inventory.txt message. Prior 1.0.5 quest-cache path fix remains on main.
- **Catalog completeness:** Item Search `catalog_size` ~**940** = unique names from `flat_*` ∪ `aggregate` ∪ `catalog.json` list sections (+ tooltip maps enrich slots/stats from real lines; no new unique names after apostrophe dedupe). That is the full **decoded** item universe from eqlegendstools — not every EQ item ever. Never invent stats.
- **OneDrive:** Found `Desktop/EQ Legends BiS/EQ_Legends_BiS.xlsx` (Josh’s BiS planner workbook, ~1.4MB, 42 sheets). Real item names across gear/weapon sheets ≈ **863**, all already in decoded DB. Excel is **not** a larger master item dump — no extra verified rows to merge.
- Restore local symlink: `data/decoded` → `desktop/resources/data/decoded` (gitignored; recreate after clone).

Smoke (2026-09-07):
- meta **1.0.6**; item-search catalog_size ≈ **940** (full decoded union); tooltip maps enrich; Agilmente / Brahhms match on import
- import + binary 400; empty/missing decoded → search 200 with warning, not 500
- desktop/resources/backend/app synced

## Why 1.0.5 (after 1.0.4 complaints)
- Left Menu, AI Choice, 3×3 priority, hover tips, Upgrade Priority, AC softcap, BiS any-class union, quest-cache import fix

## Dual wield vs 2H (unchanged model, L50 cap)
- Module: `backend/app/weapon_dps.py`
- `DWChance = Skill÷400`; skill≈min(252, level*252/**50**)

## Packaging
- desktop/ Electron publish: github PolarOppositesHub/eq-legends-bis @ **1.0.6**
- NOT run here: Windows portable/NSIS (Josh via `scripts/build-windows.ps1`)
- After rebuild: publish GitHub Release **v1.0.6**; confirm header **UI 1.0.6**
