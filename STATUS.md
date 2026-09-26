# EQ Legends BiS app status

Version: **1.1.1** — PR #36 (per-fight breakdowns; a 1.1.0 parse rebuilds from the log), PR #37 (Item Search quest links), PR #38 (fight history), PR #39 (pets, group, and Self/Group/Pets/All), PR #40 (desktop and Start Menu seal icons), PR #41 (Parser drill-down, timeline, tabs, merge, copy, and export). Updater PolarOppositesHub/eq-legends-bis untouched.

## 1.1.1
- After updating, the app automatically rebuilds the existing 1.1.0 parse from the log, so there is nothing to redo.
- Each fight keeps damage by attack and spell, healing, tanking, deaths, resists, and loot. Open a row for the breakdown, and use the timeline.
- Item Search quest names that said "not in Quest Hub" now open the quest. Woven Skull Cap shows Wizard Test of Focus.
- Fight history keeps everything by default. A full, long log is about 64 MB. The Parser tab can clear history for one character.
- The Parser tab tracks pets and your group. Limit a fight to Self, Group, Pets, or All.
- The desktop and Start Menu icons refresh to the dragon-eye seal on install and update.
- Merge selected fights. Copy the parse as text or TSV, or save CSV and HTML. Browse older fights in the history list.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.0
- Parser tab: finds the character log automatically, Live follow, Load old log with progress, fight list, per-source DPS/SDPS with Merge pets, and empty-state hints for /log on.
- What's new dialog for 1.1.0.
- Credits page.
- Automated safety-net tests in CI (Ubuntu and Windows).
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.0.23
- Merged PR #29 Item Search tooltip scaling with upgrade slider.
- Merged PR #30 workspace session restore (saved builds unaffected).
- Version bump across package.json + version.py sources.

## 1.0.22
- Merged PR #28 Item Search expand + eqlwiki confirm + haste scaling.
- Version bump across package.json + version.py sources.

## 1.0.21
- Merged PR #27 UX batch.
- Version bump across package.json + version.py sources.

## 1.0.20
- Merged PR #26: startup splash video with any-key/click skip; MP4 in `resources/splash/` via extraResources.
- Version bump across package.json + version.py sources.

## 1.0.19
- #20 Known Loot hover hint removed
- #21 Any-slot non-weapon upgrade interchange
- #22 Upgrade Priority hover/click parity with Known Loot
- #23 bare craft item-image parenthetical/eqlegendstools fallbacks
- #24 desktop chrome: themed scrollbars, no File menu, in-app Quit
- #25 dragon-eye seal app icon (`desktop/build/icon.ico`)
- Startup intro: `packaging/splash/polar-opposites-intro.mp4` via `desktop/splash.html`; any key / click / end → planner UI
- Conflict notes: App.jsx/uiSettings (#22), desktop/main.js (#24+#25 icon+chrome)

## 1.0.18
- Hotfix: do not cache eqlwiki bot interstitials / empty shells (was poisoning Known Loot to []).
- Merged PR #19: parse eqlwiki Known Loot, union catalog reverse-index, God/bare name merge, raised drop caps.
- Innoruuk (God): 4 → ~19 (15 wiki ∪ 4 catalog-only BiS).
- Version bump across package.json + version.py sources.

## 1.0.17
- Merged PR #17 (mob drop hover stats + Item Search/eqlwiki menu) and PR #18 (Mobs hub era/expansion filter).
- Conflict resolve: `uiSettings.js` kept BOTH help lines; `App.jsx` auto-merged with both features.
- Version bump across root/frontend/desktop package.json + backend version.py (+ desktop/resources copy).
- Packaging: required-decoded eqlwiki item + mob catalogs still present (1.0.16 fix preserved).

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
