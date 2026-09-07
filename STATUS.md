# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.10 — BiS icons seed + sim deltas + search/import harden + clearer quest steps**
Canonical: backend/app/{main,engine,item_catalog,paths,inventory,quest_guides,...}.py + frontend App.jsx + desktop/main.js

**Agent cannot** build Windows `.exe` or create GitHub Releases. Overnight grok bot / Josh publishes from **main**.

## Ship checklist
- [ ] Windows rebuild: `powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1`
- [ ] Prefer NSIS `EQ-Legends-BiS-1.0.10-win-x64.exe`
- [ ] After install: header **UI 1.0.10** (API · v1.0.10)

## Why 1.0.10
- BiS icons: ship seeded `data/item-images` + read bundled seeds when userData cache is empty; copy seed→writable; softer ItemIcon fallback
- Simulator: live worn/BiS deltas without Suggest upgrades; remove that button; Apply/Recalculate also refreshes upgrade priorities; equipment table no inner scrollbar
- Item Search / Inventory import: stop 500s from image-cache coupling (`name_in_catalog`, hardened `_public_item`, endpoint guards)
- Upgrade Priority quest steps: expand tags like `4-KoS` to zone + mob names

## Smoke notes
- Ensure with empty EQ_IMAGES_DIR still serves icons from seed
- Search `aegis` returns hits; Inventory.txt Location/Name TSV imports
- Quest guide "Wizard Test of Focus" mentions Keeper of Souls / Island 4
