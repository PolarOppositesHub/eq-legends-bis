# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.10 on main** (PR #7 merged). Next: **1.0.11** Item Search token match + class filter.
Canonical: backend/app/{main,engine,item_catalog,paths,inventory,quest_guides,...}.py + frontend App.jsx + desktop/main.js

**Agent cannot** build Windows `.exe` or create GitHub Releases. Overnight grok bot / Josh publishes from **main**.

## Overnight (1.0.10) if not published yet
1. `git pull origin main`
2. `powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1`
3. Publish GitHub Release **v1.0.10** (NSIS + portable + `latest.yml`)
4. Confirm header **UI 1.0.10**

## Next build (1.0.11) — Josh feedback
- [ ] Item Search: looser matching — every query token can appear anywhere in the name (order-independent). Example: `blade of ocean` finds **Aldryn, Blade of the Ocean** (ignore filler words like `of`/`the`).
- [ ] Item Search: add **usable class** selector/filter in addition to slot (AND with slot; empty = all classes).
- Details: `NEXT_BUILD_NOTES.md` → “Josh feedback — Item Search”

## 1.0.10 (shipped in source)
- BiS icons seed + sim live deltas + search/import 500 harden + clearer quest steps
