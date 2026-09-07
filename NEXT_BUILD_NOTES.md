# Next build notes

**Collecting for next build** (after **v1.0.3**). Windows rebuild on hold until Josh says start. Never invent item stats.

## Next version (after 1.0.3)

### Inventory import — show every item
- [ ] When importing Inventory.txt, some items do not show up (likely missing from our item DB).
- [ ] **Requirement:** every imported inventory line should still appear in the UI, even if the item is not in the catalog/database.
- [ ] Unknown / unmatched items: still list them (name from file); degrade gracefully (no invented stats); flag as unmatched if helpful.
- [ ] Josh may send example missing item names while testing.

### Upgrade priorities — drive from BiS list
- [ ] Sim “stats upgrade priorities” section feels wrong; Josh suspects it may weight **AC/HP only**.
- [ ] **Requirement:** upgrade suggestions should be driven by the **BiS list** for the selected class trio (what to upgrade *to*), not a narrow AC/HP heuristic.
- [ ] Compare current equipped (from inventory import) vs BiS/alternates per slot; prioritize upgrades that close the gap to BiS.

### Simulator equipment page — worn vs BiS vs deltas
- [ ] Equipment page of the simulator should show **imported worn gear** (from Inventory.txt).
- [ ] **Second column:** BiS gear for that slot (from the BiS list for selected classes), **selectable** (main + alternates as options).
- [ ] **Third column:** stat differences if the selected BiS item replaced the worn item — per-stat signed deltas (e.g. worn 10 AC, BiS 12 AC → `AC +2`).
- [ ] Only show meaningful deltas (non-zero); keep readable with current dark/gold theme.

### BiS tab — multi-tier priority stats (user-selectable)
- [ ] When choosing priority stats on the **BiS tab**, allow up to **3 primary**, **3 secondary**, and **3 tertiary** stats (all user-selectable; slots may be left empty).
- [ ] Ranking/weighting order: **primary → secondary → tertiary**. Within a tier, the selected stats share that tier’s priority.
- [ ] Example: primary STR + STA, secondary INT + WIS, tertiary CHA → gear ranking favors STR/STA first, then INT/WIS, then CHA.
- [ ] Do not hardcode a fixed priority set — the user must be able to pick which stats go in which tier.

### Josh testing notes (paste below as they arrive)
- Inventory import: some items missing from view — show all even if not in DB.
- Upgrade priorities: not good — looks like AC/HP only; should go off BiS list for what to upgrade to.
- Sim equipment: imported worn | selectable BiS column | stat delta column (e.g. AC +2).
- BiS priority stats: allow 3 primary / 3 secondary / 3 tertiary selectable stats; rank in that order (e.g. STR+STA then INT+WIS then CHA).

## 1.0.3 — Zone details, inventory import, theme, updater (2026-09-06) — shipped

Coding smoke-ready. CoS: Windows portable + NSIS + gh release (no packaging here).

## Prior notes (checked off)

### Was: Next version (after 1.0.2)

### One-click in-app update
- [x] Enable real one-click update flow (not “go download from release page”).
- [x] `autoUpdater.autoDownload = true` (or download after user clicks Update in the dialog).
- [x] On update-available: dialog with **Update** / **Later**; Update downloads then `quitAndInstall` (or download progress + Install).
- [x] Keep GitHub feed: `PolarOppositesHub/eq-legends-bis` via embedded `app-update.yml` + `latest.yml` on the release.
- [x] Prefer NSIS/`win-x64` path for seamless electron-updater installs; confirm portable behavior (portable often needs re-download — document or gate).
- [x] Bump version (likely **1.0.3**) after notes + this updater work; CoS does Windows portable + gh release only after Josh says start.

### BiS alternates UI
- [x] On BiS tab/mode, each alternate in the Alternates list should have viewable stats and a link like the main choice.
- [x] Cleaner UX: for alternates, show stats only on hover over the item name (not always expanded); keep link available like main.

### Character level cap
- [x] Cap character level at **50** (current EQ Legends max). No need for up to 60 in UI/defaults/DW formulas inputs.
- [x] Default level should be 50 (or current max), not 60.

### Zone drop details (clickable zone)
- [x] Zone name on BiS (and wherever drops show) is **clickable** → opens a detail panel/modal.
- [x] Panel contents:
  - Mobs the item drops from, **including mob levels**
  - Zone map if possible, with spawn markers for those mobs
  - If spawn/location data missing: still show zone map + **“mob location unknown”**
  - Brief zone overview: keys / level requirements to access
  - If a key is required: **link to the walkthrough**
- [x] Data note (current decode): items already have `zone` + `drops_mobs` (names). Mob levels, spawn coords/maps, and key/access/walkthroughs are **not** in decoded catalog yet — Research/source before or during next build; never invent.

### Class selector readability + theme
- [x] Move the selected **trio listing** up next to the class selector and make it more prominent (selected highlights alone are easy to miss).
- [x] Color scheme overhaul:
  - Background: **black**
  - Text: **greys and white**
  - Buttons: **gold** with readable contrast text on top
  - Drop blue/white UI dominance

### Simulator — inventory import → upgrade suggestions
- [x] Research finding (2026-09-06): gear is **not** in eqlog body. Use `/outputfile inventory` → install-root **Inventory.txt** (TSV). Eqlog only gets “Outputfile Complete” if `/log` on — optional trigger, not the gear source.
- [x] No Legends `/stats` dump found — don’t invent a stats parser from log.
- [x] Sim tab: import Inventory.txt (file picker / path); map to equipped slots; feed simulator; suggest upgrade-first priorities.
- [x] Help button: steps from `/workspace/eq-legends/log-research/HELP_BUTTON.md` (commands.md / patterns.md / REPORT.md).
- [x] Simulation tab: import **Inventory.txt** (not eqlog body) for currently equipped gear; no stats dump found.
- [x] Feed that loadout into the simulator.
- [x] From current gear vs BiS/pool, **suggest what to upgrade first** (prioritized upgrade path).
- [x] Research/verify Legends-relevant log lines (inventory/equip/stat output) before parsing — never invent item matches.

- [x] Include a **Help** button (near the import control) with steps from HELP_BUTTON.md (`/outputfile inventory` → Inventory.txt).
### Simulator — named saved builds
- [x] Allow saving different simulation builds inside the app with user-chosen **names**.
- [x] Load / switch / rename / delete saved builds (persist locally across sessions).

### Josh testing notes (paste below as they arrive)
- - Alternates: stats + link like main; stats only on hover over name.
- Level: game only goes to 50 — drop 60; default/cap at 50.
- Zone name clickable → mobs+levels, map/spawns (or map + location unknown), zone overview/keys/level reqs, key walkthrough links.
- UI: selected trio listed up by class selector (more prominent); theme black bg, grey/white text, gold buttons.
- Sim: import Inventory.txt via /outputfile inventory (eqlog is trigger only); upgrade suggestions; Help from log-research/HELP_BUTTON.md.
- Sim: saveable/nameable builds (persist in app).
- (more notes welcome)

## 1.0.2 — Dual wield vs 2H BiS (2026-09-06) — shipped
- [x] `backend/app/weapon_dps.py` working Legends DW vs 2H scoring.
- [x] DWChance = Skill÷400 (L60 capped skill 252 → 0.63); smoke green.
- [x] Windows portable + NSIS + gh release v1.0.2 published.
- Desktop: `EQ Legends BiS\EQ-Legends-BiS-1.0.2-portable.exe`
- Release: https://github.com/PolarOppositesHub/eq-legends-bis/releases/tag/v1.0.2

## 1.0.1 (prior)
- [x] Weapons any-class; empty defaults; +0…+10; level; ranged toggle; sim Clear / Load from BiS.
