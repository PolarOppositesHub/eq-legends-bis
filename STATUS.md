# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.11** — READY TO SHIP (merged on `main`)
Canonical: backend/app/{main,engine,scoring,inventory,spell_buffs,quest_hub,...}.py + frontend App.jsx
Branch: `main` (PR #9 merged) · ship notes: `cursor/v111-ship-handoff-d4a5`

**Agent cannot** build Windows `.exe` or create GitHub Releases.

## 1.0.11 — ready for Windows build
Code is on **`main`**. No further merge needed before build.

Includes:
- Search My Bags + Quest Hub + quieter inventory import
- Cast Buffs / Quick Buff **level-gated** to Character Level
- **ANY1 / ANY2** Any Slot BiS + Simulator (DMG ignored in those slots)
- Simulator **keeps imported worn** when BiS mode changes; **Reset to imported worn**
- Header badge: **Version 1.0.11** (not UI)

## Overnight
```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```
Publish GitHub Release **v1.0.11** with NSIS + portable + `latest.yml`.
