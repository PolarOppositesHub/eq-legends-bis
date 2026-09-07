# Next build notes

**v1.0.5 READY TO SHIP — coding smoke green.** Agent cannot build Windows `.exe` or create GitHub Releases. Josh rebuilds + publishes on **Joshs_Notebook**. Never invent item stats.

## Josh Windows rebuild + GitHub Release v1.0.5

```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

Artifacts in `dist-desktop/`:
- Prefer **NSIS**: `EQ-Legends-BiS-1.0.5-win-x64.exe` (updater-friendly)
- Also: `EQ-Legends-BiS-1.0.5-portable.exe`

Publish: GitHub Release **v1.0.5** for `PolarOppositesHub/eq-legends-bis` including `latest.yml` (electron-builder GitHub publish already configured in `desktop/package.json`).

### Post-install verify
- [ ] Header badge **UI 1.0.5** (and API · v1.0.5)
- [ ] Left Menu: Best in Slot / Simulator / **Upgrade Priority** / Item Search
- [ ] Mode includes **AI Choice**; Priority Primary/Secondary/Tertiary (3 each)
- [ ] BiS with Paladin in trio allows single-class armor (any-class / `mode=any`)
- [ ] Import **Inventory.txt** from `/outputfile inventory` — never pick `.exe`

## 1.0.5 — UI visibility, class priority defaults, hover tips, AC softcap (2026-09-07)

### BiS gear eligibility — Josh feedback
- [x] Non-weapon BiS pool was **intersection** (must fit all selected classes) → now **union** (usable by any one selected class).
- [x] Example: Paladin-only armor stays BiS-eligible when Paladin is in the trio.
- [x] Scoring still prefers multi-class overlap on near ties (`prefer_multi_class` / `bis_overlap`); does not exclude single-class items.
- [x] Weapons unchanged (already any-class). UI/meta copy updated.

### Upgrade Priority tab — Josh feedback
- [x] Dedicated left-menu **Upgrade Priority** tab (not only a Sim subsection).
- [x] Ordered rundown by importance (empty slots → largest BiS gaps).
- [x] Each entry: what to get, worn → BiS, deltas, **how to get it**.
- [x] Drops: zone + mob names (zone-research levels/spawns when available).
- [x] Quests: quest name + eqlwiki steps/components when fetchable (Plane of Sky class-test tables supported); never invent steps.
- [x] Import Inventory.txt from this tab; Sim keeps a short top-5 teaser linking here.
- [x] **Import 500 fix:** catalog drop lists misread as quest names blew up quest-guide cache filenames (`OSError: File name too long`) after import → Upgrade Priority. Now classify Zone:mob lists as drops, truncate/hash cache slugs, wrap obtain/quest/zone enrich so suggestions never 500. Binary/.exe picker → clear 400 pointing at Inventory.txt from `/outputfile inventory`.

### AC softcap (Max All / AI) — Josh feedback
- [x] Do not over-emphasize tank AC at the expense of everything else.
- [x] Respect AC soft caps; include AA soft-cap increases.
- [x] Working model (eqlwiki): softcap ≈ `level × 6 + 25` (L≤50); Combat Stability +2/+5/+10%; Physical Enhancement +2%; BiS assumes max CS+PE → L50 target **364**.
- [x] Loadout greedy: value AC fully until softcap, then lightly (class post-cap return); prefer STA/HP/attrs after.
- [x] Combat Agility = avoidance only (does not raise softcap).
- [ ] Josh spot-check softcap numbers vs in-game EQL (wiki notes caps may differ).

### Josh feedback after 1.0.4 update
- [x] No item images → prefetch icons after BiS; hover tip shows icon; eqlwiki cache under data/item-images/ (needs network first time).
- [x] No Items tab → left Menu **Item Search** (make nav unmissable).
- [x] Tabs not on left → sticky left **Menu** with gold border (Best in Slot / Simulator / Item Search).
- [x] Hover item names → fixed-position tip with real DB stats + picture (main BiS + alternates).
- [x] Only Max All + Priority → Mode select includes **AI Choice** + hint text.
- [x] Priority not 3×3 → Primary / Secondary / Tertiary (3 dropdowns each), all selectable.
- [x] Defaults from selected classes → `GET /api/priority-defaults` ranks classStats; most important → primary, next → secondary, next → tertiary.
- [x] Tank AC over-emphasized → softcap-aware AC (hit AA-raised softcap, then other stats) + STA/HP focus.
- [x] Stale UI risk → SPA index `Cache-Control: no-store`; version badge **UI 1.0.5**.

## Prior version (after 1.0.3) → **1.0.4** (shipped; rebuild superseded by 1.0.5)

### Inventory import — show every item
- [x] When importing Inventory.txt, some items do not show up (likely missing from our item DB).
- [x] **Requirement:** every imported inventory line should still appear in the UI, even if the item is not in the catalog/database.
- [x] Unknown / unmatched items: still list them (name from file); degrade gracefully (no invented stats); flag as unmatched if helpful.
- [ ] Josh may send example missing item names while testing.

### Upgrade priorities — drive from BiS list
- [x] Sim “stats upgrade priorities” section feels wrong; Josh suspects it may weight **AC/HP only**.
- [x] **Requirement:** upgrade suggestions should be driven by the **BiS list** for the selected class trio (what to upgrade *to*), not a narrow AC/HP heuristic.
- [x] Compare current equipped (from inventory import) vs BiS/alternates per slot; prioritize upgrades that close the gap to BiS.

### Simulator equipment page — worn vs BiS vs deltas
- [x] Equipment page of the simulator should show **imported worn gear** (from Inventory.txt).
- [x] **Second column:** BiS gear for that slot (from the BiS list for selected classes), **selectable** (main + alternates as options).
- [x] **Third column:** stat differences if the selected BiS item replaced the worn item — per-stat signed deltas (e.g. worn 10 AC, BiS 12 AC → `AC +2`).
- [x] Only show meaningful deltas (non-zero); keep readable with current dark/gold theme.

### BiS tab — multi-tier priority stats (user-selectable)
- [x] When choosing priority stats on the **BiS tab**, allow up to **3 primary**, **3 secondary**, and **3 tertiary** stats (all user-selectable; slots may be left empty).
- [x] Ranking/weighting order: **primary → secondary → tertiary**. Within a tier, the selected stats share that tier’s priority.
- [x] Example: primary STR + STA, secondary INT + WIS, tertiary CHA → gear ranking favors STR/STA first, then INT/WIS, then CHA.
- [x] Do not hardcode a fixed priority set — the user must be able to pick which stats go in which tier.

### Left nav pane — BiS, Simulator, Item Search
- [x] Move **Best in Slot** and **Simulator** into a **left-side selectable pane** (sidebar navigation), not only top tabs.
- [x] Add a third left-nav entry: **Item Search**.
- [x] Item Search: searchable list of **all items in the game** from the item database/catalog.
- [x] Requirement: every game item should be present in the DB and findable via this search (name and useful filters as fitting existing data — never invent stats). *(search index = flat_* ∪ aggregate ∪ catalog.json weapons/focus/clickies/worn/proc)*

### BiS alternates hover — real stats + item picture (fix)
- [x] Current bug/UX: hovering alternate items shows placeholder text like **"hover over stats"** — that is **not** what was requested.
- [x] **Requirement:** hovering the **alternate item name** shows that item’s **actual stats from the database** (tooltip/popover), same data used elsewhere — never invent stats.
- [x] Also show the **item picture** in that hover UI (and wherever items are listed when available).
- [x] If an equipable item has **no picture saved** in the DB/assets: look it up from a reliable source, **download/save** it into the project/data store, and reuse that image throughout the app (BiS, Sim, Item Search, etc.).
- [x] Do not leave “hover over stats” as the visible content; that was only meant as the interaction cue, not the tooltip body.

### BiS modes — Max all stats, Priority stats, AI choice
- [x] BiS mode currently has **Max all stats** and **Priority stats**. Keep both; refine Max all; add a third mode.
- [x] **Max all stats:** do **not** treat every stat equally. Weight by the **important/primary stats of the three classes in the selected trio** (look up each class’s primary stats from reliable EQ Legends sources if not already in-app).
- [x] **AC and HP:** matter for **all** classes; tanks get a **light** AC bump (not dominant) plus HP/STA preference so class attrs still compete.
- [x] **HP regen:** add a **toggleable checkbox** (e.g. “Maximize HP regen”) that, when on, includes/weights HP regen in BiS gear ranking.
- [x] **Mana / mana regen:** only weigh for **mana-using classes** in the trio; ignore for non-mana classes.
- [x] **Priority stats mode:** still uses the user-selected primary/secondary/tertiary tiers (see above).
- [x] **New third mode — AI choice:** pick BiS per slot for every trio using best available knowledge of class roles, primary stats, tank vs mana needs, EQ Legends item/data realities, and trio synergy — never invent item stats.
- [ ] Cross-check AI choice results against other online EQ Legends tools (including community “EQ Legends” gear/BiS tools). Answers should be similar, or differ only with a clear documented reason. *(Josh validation / spot-check still open)*

### Josh testing notes (paste below as they arrive)
- Inventory import: some items missing from view — show all even if not in DB.
- Upgrade priorities: not good — looks like AC/HP only; should go off BiS list for what to upgrade to.
- Sim equipment: imported worn | selectable BiS column | stat delta column (e.g. AC +2).
- BiS priority stats: allow 3 primary / 3 secondary / 3 tertiary selectable stats; rank in that order (e.g. STR+STA then INT+WIS then CHA).
- Left pane: BiS + Simulator selectable; add Item Search with full game item DB searchable.
- BiS alternates hover: show real DB stats + item picture on name hover (not “hover over stats” text); fetch/save missing item images for reuse app-wide.
- BiS modes: Max all weights trio primary stats + light AC + HP/STA for tanks; HP regen checkbox; mana/mana regen only for mana classes; add AI choice mode cross-checked vs online EQ Legends tools.

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
