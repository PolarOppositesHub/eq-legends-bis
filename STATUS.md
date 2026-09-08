# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.11** — READY TO SHIP (merge cast-buffs icons PR, then build)
Canonical: backend/app/{main,engine,scoring,inventory,spell_buffs,quest_hub,...}.py + frontend App.jsx
Branch: `cursor/cast-buffs-icons-list-d4a5` (Quick Buff icons) · base `main` has PR #9

**Agent cannot** build Windows `.exe` or create GitHub Releases.

## 1.0.11 — ready for Windows build
Merge the Cast Buffs icons PR into `main`, then build.

Includes:
- Search My Bags + Quest Hub + quieter inventory import
- Cast Buffs / Quick Buff **level-gated** to Character Level
- **Quick Buff active list** above Live Totals: grouped by stacking type, spell icons, hover explanations (catalog tooltips + effects)
- **ANY1 / ANY2** Any Slot BiS + Simulator (DMG ignored in those slots)
- Simulator **keeps imported worn** when BiS mode changes; **Reset to imported worn**
- Header badge: **Version 1.0.11** (not UI)

## Overnight
```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```
Publish GitHub Release **v1.0.11** with NSIS + portable + `latest.yml`.
