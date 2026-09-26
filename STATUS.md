# EQ Legends BiS app status

Version: **1.0.23** — PR #29 (Item Search tooltip stat text follows the +0…+10 slider, labeled 'Tooltip at +N'; hover previews +0, collapsed rows +10) + PR #30 (remembers the working session across launches in userData workspace-session.json; Settings > Reset to defaults > Start fresh clears it). Updater PolarOppositesHub/eq-legends-bis untouched.

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
