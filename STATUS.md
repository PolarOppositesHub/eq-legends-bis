# STATUS
App: /workspace/eq-legends-app
Version: **1.0.3** (local tree smoke-ready; CoS does Windows portable + gh release — do not package here)
Canonical: backend/app/{main,engine,weapon_dps,zones,inventory,races,paths}.py + frontend **App.jsx** (+ styles.css) + desktop/main.js
Smoke (2026-09-06 ~11:42 CT / 16:42 UTC):
- meta version **1.0.3**; character_levels 1..**50**; default/clamp L50
- DW skill≈min(252, L*252/50) → L50 skill **252**, DWChance **0.63**
- MNK alone +10 @L50: DW path enabled; alts include url + stats_at_upgrade (hover UI)
- GET /api/zones → **54** zones from zone-research; GET /api/zones/Lower%20Guk + zone-detail OK; missing coords → **mob location unknown**
- POST /api/inventory/parse on samples/dranak-Inventory.txt → 18 planner slots (HEAD Raw-Hide Skullcap, etc.)
- POST /api/inventory/upgrade-suggestions → prioritized gaps vs BiS
- GET /api/help/inventory serves HELP_BUTTON.md
- Frontend vite build OK (black/gold theme); HELP_BUTTON.md in frontend/public + dist
- desktop/main.js: Update/Later → downloadUpdate → quitAndInstall; GitHub PolarOppositesHub/eq-legends-bis; portable note
- data/zone-research + data/log-research symlinks; bundle_desktop_resources copies zone-research + help for packs

## Dual wield vs 2H (unchanged model, L50 cap)
- Module: `backend/app/weapon_dps.py`
- `DWChance = Skill÷400`; skill≈min(252, level*252/**50**)
- If no DW class: ratio-only PRIMARY/SECONDARY

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


## Smoke (2026-09-06 ~11:50 CT)
- GET /api/zones -> **54** zones; Befallen + Splitpaw Lair zone-detail OK (research-only)
- POST /api/inventory/import (dranak-Inventory.txt) -> 18 worn slots; upgrade-suggestions @L50 Monk -> 19 suggestions
- POST /api/bis Paladin @L50; character_level 99 clamps to **50**; meta version **1.0.3**, levels 1..50
- Monk @L50 DW: PRIMARY Wu's Fist of Mastery + SECONDARY Whitened Treant Fists; DWChance=0.63
- Help markdown from data/HELP_BUTTON.md; frontend vite build OK
- **Ready for CoS Windows** portable + NSIS + gh release v1.0.3

## Packaging
- desktop/ Electron publish: github PolarOppositesHub/eq-legends-bis @ **1.0.3**
- NOT run here: Windows portable/NSIS (CoS / Josh on Joshs_Notebook via build-windows.ps1)
- Ready-for-CoS-Windows: **YES** (smoke green)
