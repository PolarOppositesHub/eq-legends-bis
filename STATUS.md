# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.4** (local tree smoke-ready; CoS does Windows portable + gh release — do not package here)
Canonical: backend/app/{main,engine,scoring,class_roles,item_catalog,weapon_dps,zones,inventory,races,paths}.py + frontend **App.jsx** (+ styles.css) + desktop/main.js
Smoke (2026-09-07):
- meta version **1.0.4**; modes Priority / Max All / AI Choice; character_levels 1..**50**
- Max All: class-weighted attrs from races.json classStats; tank AC/HP heavier; mana de-emphasized for non-mana
- Priority: up to 3 primary / secondary / tertiary selectable stats
- AI Choice: role-aware blend for trio; HP regen optional toggle
- GET /api/item-search Rubicite → catalog hit; GET /api/item-image fetches/caches eqlwiki icons under data/item-images/
- Inventory parse retains unmatched names (no invented stats); upgrade suggestions driven by BiS list + equipment_compare deltas
- Frontend: left nav BiS / Simulator / Item Search; alt hover shows real stats + icon; sim worn|BiS|deltas
- data/decoded → symlink to desktop/resources/data/decoded

## Dual wield vs 2H (unchanged model, L50 cap)
- Module: `backend/app/weapon_dps.py`
- `DWChance = Skill÷400`; skill≈min(252, level*252/**50**)
- If no DW class: ratio-only PRIMARY/SECONDARY

## 1.0.4 features shipped (local)
- Left nav: Best in Slot, Simulator, Item Search
- BiS multi-tier priority stats + Max All class weights + AI Choice + HP regen checkbox
- Alternate hover: real DB stats + item picture (eqlwiki cache)
- Inventory: show unmatched items; BiS-driven upgrade priorities; worn | BiS | deltas
- Full catalog item search API + UI

## 1.0.3 features shipped (local)
- One-click in-app update dialog (not browser-primary)
- BiS alts: link + stats on hover only
- Level cap/default 50
- Clickable zone panel (research-only)
- Theme black/grey/white/gold; trio banner by class selector
- Sim Inventory.txt import + Help + upgrade suggestions
- Named saved sim builds (localStorage)

Start: see README.md
Export: scripts/export_xlsx.py or scripts/run_planner_export.py
Owner: see .build_owner (do not wipe tree)

## Packaging
- desktop/ Electron publish: github PolarOppositesHub/eq-legends-bis @ **1.0.4** (bump when Josh says start Windows rebuild)
- NOT run here: Windows portable/NSIS (CoS / Josh on Joshs_Notebook via build-windows.ps1)
- Ready-for-CoS-Windows: **pending Josh validation of 1.0.4**
