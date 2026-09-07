# Next build notes

**v1.0.6 coding smoke-ready locally.** Josh must rebuild Windows + publish GitHub Release **v1.0.6** (agent cannot). Never invent item stats.

Confirm after install: header badge shows **UI 1.0.6**, Item Search `catalog_size` ≈ **940**, Inventory import works, binary/.exe → clear 400.

## 1.0.6 — Import/Search 500 harden + catalog completeness (2026-09-07)

### Josh report (after 1.0.5 / main)
- [x] Inventory import Internal Server Error again (worked in 1.0.3).
- [x] Item Search also Internal Server Error — suspected DB/data.
- [x] OneDrive Desktop Excel with item data?
- [x] Catalog shows ~940 — is that all game items?

### Findings / fixes
- [x] **940** = Item Search `catalog_size` = unique names from `flat_*` ∪ `aggregate` ∪ `catalog.json` list sections (weapons/focus/clickies/worn/proc). That *was* the full decoded union (~674 BiS armor + catalog extras).
- [x] Expanded search index with catalog **tooltip item maps** (real tooltip line stats only) to enrich slots/stats; unique count remains ~**940** after apostrophe dedupe. Still not every conceivable EQ item — only what eqlegendstools decoded ships. No invented stats.
- [x] OneDrive: **`Desktop/EQ Legends BiS/EQ_Legends_BiS.xlsx`** found (~1.4MB). Sheets: How to use, Class selector, Stat planner, lookups, all 16 class BiS, All gear, weapons tops, etc. Unique item names on gear/weapon sheets ≈ **863**, all ⊆ decoded catalog. **No Excel-only rows to integrate.**
- [x] Path harden: `decoded_dir()` ignores missing env overrides; Electron probes multiple decoded paths; recreate gitignored `data/decoded` symlink after clone.
- [x] API harden: item-search + inventory/import never uncaught 500; binary still 400.
- [x] 1.0.5 quest-cache / BiS any-class fixes confirmed present on main and retained.

### Rebuild checklist (Josh)
- [ ] `scripts/build-windows.ps1` → portable + prefer NSIS
- [ ] GitHub Release **v1.0.6** + `latest.yml`
- [ ] Confirm **UI 1.0.6** badge; re-test Inventory.txt import + Item Search

## 1.0.5 — UI visibility, class priority defaults, hover tips, AC softcap (2026-09-07)

### BiS gear eligibility — Josh feedback
- [x] Non-weapon BiS pool was **intersection** → now **union** (usable by any one selected class).
- [x] Weapons unchanged (already any-class).

### Upgrade Priority tab — Josh feedback
- [x] Dedicated left-menu **Upgrade Priority** tab.
- [x] **Import 500 fix:** long Zone:mob drop lists as quest names → OSError cache path; classify as drops + slug hash + graceful degrade. Binary → 400 Inventory.txt message.

### AC softcap (Max All / AI)
- [x] Softcap-aware AC; L50 target **364** with max CS+PE.
- [ ] Josh spot-check softcap numbers vs in-game EQL.

## Prior version notes
See git history for 1.0.4 inventory unmatched / BiS upgrades / hover / left nav requirements (done).
