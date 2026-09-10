# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.15** — version sync for Windows ship (UI/API match Electron)
Canonical: backend/app/{main,engine,scoring,inventory,spell_buffs,quest_hub,...}.py + frontend App.jsx
Branch: `cursor/sim-per-slot-upgrades-d4a5` (PR #13) rebased onto `main` (PRs #11 + #12)

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
