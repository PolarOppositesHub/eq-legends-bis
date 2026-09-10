# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.16** — free-port sidecar + ship eqlwiki item/mob catalogs in Windows packs
Canonical: backend/app + frontend App.jsx + desktop/main.js

## 1.0.16
- Electron picks a free localhost port (no fixed 8765); health requires our EQ_INSTANCE_NONCE
- packaging/required-decoded ships eqlwiki_item_names.json + eqlwiki_mob_names.json; bundle fails if missing from resources


**Agent cannot** build Windows `.exe` or create GitHub Releases.

## 1.0.12 — ready for Windows build
Includes 1.0.11 plus:
- Simulator **per-slot +0…+10** upgrades + Inventory.txt import levels
- Desktop **EQ folder Update** auto-import
- Inventory matching expanded with eqlwiki item names (**no invented stats**)
- Themes (Classic / Light / Dusk / Forge), settings cog, help, loading overlay
- Quick Buff grouped cast list with icons (PR #11)
- Quest Hub walkthrough steps + maximize layout (PR #12)
- Header badge: **Version 1.0.12**

## Overnight
```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```
Publish GitHub Release **v1.0.12** with NSIS + portable + `latest.yml`.

## 1.0.11 — shipped features (now on main)
- Search My Bags + Quest Hub + quieter inventory import
- Cast Buffs / Quick Buff **level-gated** to Character Level
- **Quick Buff active list** above Live Totals: grouped by stacking type, spell icons, hover explanations
- **ANY1 / ANY2** Any Slot BiS + Simulator (DMG ignored in those slots)
- Simulator **keeps imported worn** when BiS mode changes; **Reset to imported worn**
- Header badge: **Version 1.0.11** (superseded by 1.0.12)
