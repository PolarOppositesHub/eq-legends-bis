# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.5** (local tree smoke-ready; Josh does Windows portable + gh release — do not package here)
Canonical: backend/app/{main,engine,scoring,class_roles,item_catalog,weapon_dps,zones,inventory,races,paths}.py + frontend **App.jsx** (+ styles.css) + desktop/main.js

## Why 1.0.5 (after 1.0.4 complaints)
Josh reported after updating to 1.0.4: no item images, no Item Search, tabs not on left, no hover stats, only Max All + Priority (no AI Choice), Priority not 3×3 selectable. Source inspection of the published **v1.0.4** portable *does* contain those UI strings — so either an old EXE was still launching, Chromium cached the SPA shell, or hover tips were clipped (CSS absolute tips inside overflow). **1.0.5** makes the UI unmistakable and fixes defaults/hover/cache:

- Header badge **UI 1.0.5** (confirm this after install)
- Left **Menu** nav (gold border): Best in Slot / Simulator / Item Search
- Modes: Priority Stat · Max All Stats · **AI Choice** + Maximize HP regen
- Priority: up to **3 primary / 3 secondary / 3 tertiary** selectable dropdowns
- Defaults from selected classes via `GET /api/priority-defaults` (classStats ranking)
- Fixed-position hover tip (stats + icon) on BiS / alternate names — not clipped
- Prefetch item icons after BiS; SPA `Cache-Control: no-store` on index.html
- Tank Max-all / AI: AC rebalanced (tank ~1.7 / others ~1.45); AI prefers STA/HP over AC stack

Smoke (2026-09-07):
- meta version **1.0.5**; Warrior/Cleric/Wizard defaults → primary STA,INT,STR · secondary WIS,AGI,DEX · tertiary CHA
- vite build → `frontend/dist` assets index-XHF-qixJ.js / index-C9glluE6.css
- desktop/resources/backend/app synced with canonical backend/app

## Dual wield vs 2H (unchanged model, L50 cap)
- Module: `backend/app/weapon_dps.py`
- `DWChance = Skill÷400`; skill≈min(252, level*252/**50**)
- If no DW class: ratio-only PRIMARY/SECONDARY

## Features (1.0.4 + 1.0.5)
- Left nav: Best in Slot, Simulator, Item Search
- BiS multi-tier priority + Max All class weights + AI Choice + HP regen
- Alternate/main hover: real DB stats + item picture (eqlwiki cache under data/item-images/)
- Inventory: unmatched items; BiS-driven upgrades; worn | BiS | deltas
- Full catalog item search

Start: see README.md
Owner: see .build_owner (do not wipe tree)

## Packaging
- desktop/ Electron publish: github PolarOppositesHub/eq-legends-bis @ **1.0.5**
- NOT run here: Windows portable/NSIS (Josh on Joshs_Notebook via `scripts/build-windows.ps1`)
- After rebuild: publish GitHub Release **v1.0.5** + `latest.yml`; prefer **NSIS** for updater; confirm header shows **UI 1.0.5**
