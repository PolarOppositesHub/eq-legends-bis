# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.11** — Search My Bags + Quest Hub + import UX; Item Search token/class still pending
Canonical: backend/app/{main,engine,item_catalog,quest_hub,quest_guides,inventory,...}.py + frontend App.jsx + desktop/main.js
Branch: `cursor/bags-quest-hub-d4a5`

**Agent cannot** build Windows `.exe` or create GitHub Releases. Overnight grok bot / Josh publishes from **main**.

## 1.0.11 (this branch)
- Simulator import: unmatched names **closed by default** (debug only); highlight worn slots filled
- Menu **Search My Bags** — search imported Inventory.txt lines (worn/bags/bank)
- Menu **Quest Hub** — quest index from decoded catalog; guide + prerequisites + inventory ownership for components
- Upgrade Priority: **Open in Quest Hub** for quest-associated upgrades
- Versions: **1.0.11** / UI **1.0.11**

## Still pending (next notes)
- Item Search: token/anywhere-in-name match (`blade of ocean` → Aldryn, Blade of the Ocean)
- Item Search: usable class filter alongside slot

## Overnight (after merge)
1. Merge this PR → `main`
2. `powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1`
3. Publish GitHub Release **v1.0.11**
