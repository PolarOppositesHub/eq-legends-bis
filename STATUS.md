# EQ Legends BiS app status

Version: **1.1.18** — Health answers before the full catalog loads. Empty Item Search builds one page. Ask AI leaves chat lines out, copies the full pack, and can install or sign in to your own Grok account with no API key. Packaged zones in this build are the sourced zone files: 56 zones and 448 mobs, including Nektropos Castle and Lake Nerius. Source conflicts stay flagged. **1.1.17** — One Ask AI button sends your question with the gear or fight on screen and opens Grok in the browser, or answers in the app when your own signed-in Grok command is already on this PC. No API key and no stored token. **1.1.16** — Buff and debuff timers from the live log, per-mob respawn timers you fill in, a Maps tab, an exaltation planner, resist profiles per class loadout, profile export and import, and a perf readout with a feedback zip that leaves out sign-in tokens. **1.1.15** — Overview is the home screen, with loot history and your own drop rates, leveling and AA per class loadout, raid targets and the Tuesday weekly lockout, live level-up and notable-loot toasts, and XP and con card overlays. **1.1.14** — Google Drive sync uses the hidden app folder, the window has a themed title bar, and overlay meters stay on top without stealing focus from a text box. **1.1.13** — OneDrive file downloads follow Microsoft's redirect without sending the sign-in to the download host, so a personal Microsoft account can sync files. One file that cannot be downloaded is skipped, and Settings says how many. **1.1.12** — OneDrive personal Microsoft accounts request the full Graph App Folder scope, the App Folder is opened before sync, and Settings shows Microsoft's error plus Test connection. A saved sign-in from 1.1.11 asks you to sign in once more. **1.1.11** — OneDrive sync uploads and downloads after sign-in, Sync now shows progress and the result, and the window X quits unless Minimize to tray is on. A second launch focuses the running app. **1.1.10** — per-character sync through a folder you pick (iCloud Drive, Dropbox, or any folder) or OneDrive, plus Close all and a compact X on unlocked overlays. **1.1.9** — overlay title-bar drag, lock that also moves the window, Parser overlay controls, per-overlay appearance, and DPS/HPS shown to one decimal. **1.1.8** — overlay DPS and heal meters, verified log alerts, parser class and level from the newest /who or level-up line, currency starting counts, and inventory imports that merge by section. **1.1.7** — BiS mote and XP paths from the Currencies ledger, Plane of Sky progress, a per-character wish list, Item Search Damage/Delay ratio, and the shared item menu on Best in Slot names. **1.1.6** — Currencies ledger, Item Search compare-at level and three-class usable-by, collapsible Parser Group, Simulator class swaps that wait for a full set, owned-name matching for Slime Blood of Cazic-Thule, a full-width window, two wrist slots, and lore on paired slots. **1.1.5** — Item Search filters and three-level sort, collapsible Character sections, owned-only BiS re-rank, item icons, merge-list equipable rule, and Dragon's Hoard plus Storage from inventory dumps. **1.1.4** — Character item hover and click, bag search on the Character tab, a merge list, and stat-popup dismiss. 1.1.3 — inventory import v2 (PRs #45, #46, and #47): header-based inventory parsing, watching and dropping inventory dumps, the Character tab, and owned badges. 1.1.2 — parser rebuild no longer freezes the app on the first launch after an update. 1.1.1 is PR #36 (per-fight breakdowns; a 1.1.0 parse rebuilds from the log), PR #37 (Item Search quest links), PR #38 (fight history), PR #39 (pets, group, and Self/Group/Pets/All), PR #40 (desktop and Start Menu seal icons), PR #41 (Parser drill-down, timeline, tabs, merge, copy, and export), and PR #43 (first launch no longer fails with "database is locked"). Updater PolarOppositesHub/eq-legends-bis untouched.

## 1.1.18
- `/api/health` answers from a small boot app while the full API imports. Empty Item Search builds public rows for the page only. On this machine, health answered in about 0.01s (the full import was 0.71s) and an empty search went from 4.11s to 0.15s.
- While a parser rebuild runs, the wait screen skips blur and the sliding bar. Meter overlays back off on a busy parser and subscribe only to alert events.
- Ask AI leaves chat lines out, copies the full pack, and puts only a short prompt in the grok.com address. The Grok Build CLI can be installed after a confirm and signed in with your own account. No API key. In-app answers are Beta, read-only, and can be cancelled.
- Packaged zone files are the sourced set: 56 zones and 448 mobs, including Nektropos Castle and Lake Nerius from the October update (24 and 4 mobs). The October files replace only those two zones. 50 items were added to the catalog. Source conflicts stay flagged and are not resolved.
- What's new dialog for 1.1.18.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.

## 1.1.17
- Ask AI is one header button. The question includes worn gear on other pages, Best in Slot picks on that page, Simulator picks on that page, or the selected Parser fight. A stat or number that is not already loaded stays unknown.
- Grok opens at grok.com in the default browser. The prompt is prefilled with ?q= when the link stays short. Otherwise the prompt is copied and a note says to paste it into Grok.
- If `grok` is on PATH, `grok version` succeeds, and `grok models` succeeds without an API key in the environment, the answer is shown in the app. The command's own sign-in is used. The app does not read auth files, store a token, or send one. Any other result uses the browser flow. The local command is started with tools denied and a single turn.
- What's new dialog for 1.1.17.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.

## 1.1.16
- Buff and debuff timers follow slow, charm, rune, and spell-worn-off lines. A cast line does not start a timer. Duration is a number you enter for the current class loadout, or the seconds between a start and a worn-off line already in your log. Anything else stays unknown. The buff overlay uses the same lock, raise, and focus path as the other meters.
- Respawn timers list the last time you killed each mob, and the fight zone when that kill sits inside a saved fight. The respawn seconds are yours to enter. Time between kills is not treated as a respawn.
- Maps lists zones from saved fights. A map link, level requirement, or mob location is shown only when a zone-research file already has it. Otherwise it says unknown.
- The exaltation planner lists Slot7–10 sockets and names ending in (Exaltation) from the inventory import. Catalog stats only. No best exaltation is chosen. A target you type is stored on the current class loadout.
- Resist profiles add decoded race saves and catalog resists on worn items, at that item's +N, for the current class loadout. A missing item or race is left out of the total and labeled unknown. Resist cap is unknown. The Warrior +25 magic save is the existing char-sheet pool formula.
- Export and import carry durations, respawn seconds, exaltation notes, resist snapshots, and UI settings. Sign-in tokens are dropped. Perf reports memory when the platform names the unit. The feedback zip contains allowlisted logs and redacted settings.
- What's new dialog for 1.1.16.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.

## 1.1.15
- Overview is the home screen. Cards show the current mob, the DPS curve from the saved fight, leveling pace, recent drops and kills, and the zones already on those fights.
- Loot history joins the existing loot stream to the catalog, mob hub, and quest links. Drop rate is your loot lines divided by your kills of that mob. A mob with no kill stays unknown. Favourites are starred. Notable means a BiS name already in the decoded lists, a wish-list item, a mote at or above the grade you set, or a Plane of Sky item. Item stats appear only when the catalog already has them.
- Leveling and AA follow each class loadout. A lower level after a class swap is kept. Pace is levels of progress from experience percents. A percent-less line is omitted, never treated as 0. New spells at a level come only from sourced spell levels. Zone bands stay unknown unless a sourced level requirement is already on file.
- Raid targets list named kills that are already in the mob index, with the instance difficulty stored on the fight. The weekly lockout reuses the currencies Tuesday 8:00 AM Pacific reset. Other lockouts are UNVERIFIED and entered by you. Recently considered and the per-mob page use consider lines and your loots.
- Level-up and notable-loot toasts publish only while the log is live. A replay does not toast. XP and con card overlays use the same lock, raise, and focus path as the other meters.
- What's new dialog for 1.1.15.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.

## 1.1.14
- Google Drive is a sync provider next to Sync folder and OneDrive. Scope is `https://www.googleapis.com/auth/drive.appdata` only. Sign-in is a public desktop client with PKCE, the system browser, and loopback `http://localhost:<port>`. The refresh token is stored with Electron safeStorage. Files use `EQLegendsBiS-sync/manifest.json` and `events/<character>/<device_id>.jsonl` in the Drive appDataFolder. The same event-log merge, queue, and sync schedule are reused.
- The desktop client id constant is `GOOGLE_DRIVE_CLIENT_ID` (`122260219418-2rhjatugpadqi99ofecm8quruernbb0d.apps.googleusercontent.com`). Downloads prefer a listing download URL, then the official `alt=media` URL. Authorization is not sent to a non-Google download host. One bad file is skipped. Settings shows the Drive error code and message, plus Sign in, Sign out, Test connection, Sync now, and last synced. An unverified-app warning is expected. No Google logo was added.
- The main window is frameless. The in-app title bar matches the theme and has minimize, maximize/restore, and close. Drag moves the window. Double-click toggles maximize. Windows snap still works. Close still quits, or minimizes to the tray, using the 1.1.11 X button setting.
- Overlay raise on the 2 second timer keeps the meter on top without focusing it or calling show. If a raise moves focus onto the overlay, focus goes back to the window that had it.
- What's new dialog for 1.1.14.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.

## 1.1.13
- OneDrive `:/content` downloads no longer send the Bearer token to the pre-authenticated download host. A 302 Location is fetched with a fresh request and no Authorization header. Uploads still authenticate only to graph.microsoft.com. When a listing includes `@microsoft.graph.downloadUrl`, that URL is used first.
- One file that cannot be downloaded is logged (method and URL path, no token) and skipped. Sync continues. Settings shows Synced with N file(s) skipped. A 401 from graph.microsoft.com is still sign-in expired.
- The splash video is packaged once. The resources extraResources rule excludes `splash/**`. The Windows build script removes untracked leftovers in `desktop/build` and `desktop/resources` before packaging and leaves tracked source in place.
- What's new dialog for 1.1.13.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.
- Google Drive and the custom title bar are not in this version.

## 1.1.12
- OneDrive authorize and token requests use `https://graph.microsoft.com/Files.ReadWrite.AppFolder offline_access` on the `/common` authority. The Authorization header stays `Bearer` plus the access token. `/consumers` is not used, because that authority rejects work accounts.
- Before listing events, sync calls `GET /me/drive/special/approot` once per access token so OneDrive creates the App Folder. Settings > Sync has Test connection, which calls that same URL and shows Connected to OneDrive App Folder, or Graph's status and error code and message.
- A Graph error keeps `error.code` and `error.message` from the JSON body, and `error` / `error_description` from WWW-Authenticate. Those are written to the sidecar log without the access token, and they are included in the Settings error text. A failed token refresh shows Microsoft's `error` and `error_description`.
- No saved refresh token says Sign in to OneDrive. Expired is used only when a refresh is rejected. A token saved for the old short scope says Sign in to OneDrive again to finish the update.
- What's new dialog for 1.1.12.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.
- Google Drive and the custom title bar are not in this version.

## 1.1.11
- OneDrive sign-in builds a real Microsoft Graph transport. Sync uploads this PC's events and downloads the other PC's. A 401 refreshes the saved sign-in once and retries. If the refresh fails, Settings says: OneDrive sign-in expired. Sign in again.
- Sync now shows Syncing…, then Synced at the local time, or the error text. Sync failures are shown in Settings.
- The window X quits unless X button is Minimize to tray (Settings, default Quit). The first time the app stays in the tray, a notice explains how to open it again. The tray menu Open EQ Legends BiS and a double-click show, restore, and focus the window. A second launch does the same. Quit closes overlay windows, destroys the tray, and stops the backend. On Windows that uses taskkill /PID /T /F so an orphaned Python process does not stay alive. A stale backend recorded in sidecar.pid, or answering health on the startup port, is stopped before this launch starts a new one.
- What's new dialog for 1.1.11.
- Version bump across package.json, package-lock.json, and version.py sources. No release publishing.
- Custom title bar is not in this version.

## 1.1.10
- Sync is off until a provider is chosen. The sidecar keeps an append-only event log per character: currency ledger rows (including manual counts and starting counts), wish list pins, Parser class and level, per-character settings, and one event per inventory section. Replay is sorted by timestamp, device id, and event id. Devices merge by union of id. The newest set is the count; the other stays in History. A log line's id is a hash of the character, the raw line, the line timestamp, and this device, so each PC adds only its own lines. Existing local data is copied into the log once, with the timestamps it already had.
- Files live in `EQLegendsBiS-sync/manifest.json` and `events/<character>/<device_id>.jsonl` inside the folder you pick, or in the OneDrive App Folder (`/me/drive/special/approot`). This device writes only its own jsonl, via a temp file and rename. A conflicted copy is merged by id. Offline edits stay in a local queue and upload on a later sync. Sync runs on launch, about every 2 minutes, about 10 seconds after a change, on Sync now, and on quit.
- OneDrive uses the public client `868f921b-3445-4b09-90bf-13b343145256`, the `/common` authority, and scopes `Files.ReadWrite.AppFolder offline_access`. Sign-in opens the system browser and a loopback `http://localhost:<port>` with PKCE. The refresh token is stored with Electron safeStorage and is not sent to the page. Google Drive is not in this version.
- Settings shows the provider, Choose folder or Sign in/out, the device name, last synced, Sync now, and errors. A Sync folder shows: If this folder is in iCloud Drive, mark it Always keep on this device. A file iCloud has not downloaded yet says waiting for iCloud to download.
- The Parser Overlays panel has Close all. The unlocked drag bar closes with a compact X (no-drag, aria-label Close overlay). Closing still saves open false.
- What's new dialog for 1.1.10.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.9
- Unlocked overlays show a title-bar grip (`-webkit-app-region: drag`). Buttons and controls are no-drag, and the meter body does not cover the grip. Lock calls setIgnoreMouseEvents with forward, setMovable(false), and setResizable(false), and hides the grip. Unlock calls setMovable(true) and setResizable(true), including a window that was created locked. Position and size are saved per overlay and restored on launch. A saved spot that misses every monitor moves back on screen.
- The Parser page has an Overlays panel: open and close DPS, Heal, and Alerts, lock or unlock one or all, and the row shows Open/Closed and Locked/Unlocked. Those buttons use the same preload IPC as the rest of the desktop shell. The tray menu still opens the meters and unlocks them.
- Appearance is saved per overlay and pushed to the open meter as the control moves: background opacity, text opacity, text size, background color, accent color, title text while locked, and reset to defaults. Background opacity does not fade the text.
- DPS and HPS display through formatPerSecond, one decimal place, on the meters, the fight list, fight detail, group and pet rows, saved history, copy and export, and alert text. Stored damage, heals, and the raw rates are not rounded. Sorts use the raw rates.
- Overlays are raised with setAlwaysOnTop(true, 'screen-saver'), falling back to 'pop-up-menu', setVisibleOnAllWorkspaces including fullscreen, skipTaskbar, and focusable false while locked. Blur, show, lock, display changes, and a 2 second timer only raise the window. Blur does not hide or close it. The alert banner clears its text and leaves the window open. Spoken and file alerts play in a hidden window. No injection. The panel tells you to use borderless or windowed fullscreen. eqclient.ini is read only; Fullscreen=1 under [VideoMode] shows a warning. The game file is not written.
- What's new dialog for 1.1.9.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.8
- Overlay: frameless transparent always-on-top DPS and heal meters. Lock calls setIgnoreMouseEvents so the meter is click-through. Position is saved per meter and snaps to the screen edge. Fight scope shows the stored fight DPS and heals. Zone scope sums damage and heals and does not invent a DPS rate. Exclusive fullscreen draws over every window. No input is sent to the game. Auto-hide stays off because this version does not query the foreground window. Close to tray is off, so the window X still quits.
- Alerts: slow, your death, and a spell wearing off. A raid-target rule matches a name you type against a slain or died line. Charm break stays off. Share strings are base64 JSON and import only adds rules. OS speech and a user .wav or .mp3. Tray menu. Alert banner overlay.
- Parser class and level: newest timestamp wins. Manual override, then the character's own /who trio and level, then `You have gained a level! Welcome to level N!` for level only. A level drop clears classes and says `Type /who to refresh classes`. A newer /who replaces a manual override and says so. The Parser header has class pickers and a level box, with Clear.
- Currencies: + and − beside each count, Starting count, Set all counts, History, and Combine into next grade. Before a starting count, Seen in log since the date is shown and is not added to storage. The tab refreshes every 20 seconds while open and after parser batches. Last picked up from log is shown. No log loaded has an empty state.
- Inventory imports merge by section. A file replaces only worn, bags, bank, shared bank, Dragon's Hoard, depot, storage, or other sections it contains. Each section shows Last updated. A section older than the newest import is stale. Owned counts still include a stale section and say may include stale section. Equipped names come from worn. Clear section and Replace everything. An old single snapshot is dated at its original import time.
- What's new dialog for 1.1.8.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.7
- Requirements tab: for each Best in Slot item, XP to the target +N (2^t per step, cumulative 2^T − 1), the motes that takes, the cheapest path from the Currencies ledger, and the shortfall. Mote item XP is the SPEC §8.1 table already on the ledger. Void-Touched Potential is spent on the highest remaining tier gap first. Intra-tier progress is manual because the inventory export does not include it. A duplicate at +k adds 2^k XP. A copy with no +N is not treated as +0. Score per mote reuses the engine score already on the slot. The path does not recompute weapon damage. eqlwiki says 5% per tier and eqlegendstools says 10%; the tracker follows `scale_stats_to_level`.
- Plane of Sky uses the existing 95 eqlwiki tests (CC BY-SA). Wind Rune counts come from the Currencies ledger, filled from inventory only when the ledger total for that rune is 0. Turn-in items come from the inventory import. Classes are ordered by how close they are to unlocking. Achievements use the verified I/C tab tree. A completed autocomplete or "can be bypassed" component marks the class Unlocked (granted) and does not count Obtain rows as turn-ins. The token case stays UNVERIFIED. A status letter other than I or C stays UNVERIFIED. Log turn-ins use `You offered <n> <item> to <npc>.`. Reward lines that do not match a test stay unmatched, including "Obtain Windhowl and Spirit Render" and "Griffin-Hide Armguards".
- Wish list: pin or unpin from Item Search, Best in Slot, Character, and the item menu. The view shows owned status and the mote path when that item is in the plan. Stored per character.
- Item Search Damage/Delay ratio is damage divided by delay, higher is better, shown to two decimals. It is a choice on all three sort keys and a minimum next to Has stat. Compare at +N uses `scale_stats_to_level` on stats_plus0. If damage does not change at +10, the ratio uses the base values and says so. Items with no damage or delay sort last and are left out of the minimum.
- Click a Best in Slot name for the same Item Search and eqlwiki menu used elsewhere. Hover still shows the stat popup.
- What's new dialog for 1.1.7.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.6
- Currencies tab: 10 mote grades with SPEC §8.1 item XP, 15 Wind Runes, and Void-Touched Potential. Manual storage anchor. Log loot and given add, offers subtract, auto-sold motes count 0. Lines before the anchor are ignored. Merge lines do not decrement; they show a pending chip until I used. Inventory import reconciles bag counts and can be undone. Condense is offered up to Grand → Ascendant with an item-XP warning. Void-Touched shows held n/3, earned this week n/3, and a Central-time countdown to Tuesday 8:00 AM Pacific. The ledger does not plan Void-Touched spending. Wind Rune need is not tracked. XLSX gains a Currencies sheet only.
- Item Search usable-by accepts up to 3 classes, Any by default or All. The stat minimum is a compact field. Compare at +N filters, sorts, and lists stats at that upgrade using the same scaling as the simulator.
- Parser Group panel collapses with the Character-tab chevron, and the choice is remembered.
- Simulator waits for a full class set before recalculating or showing the loading screen. A full set is 3 classes, or 2 when Character Level is below 10.
- Owned matching uses the in-game name Slime Blood of Cazic-Thule. The old spaced spelling still resolves. Case, hyphens, apostrophes, and extra spaces fold, and a catalog item id wins when the import has one. Long names wrap with their badges. The window fills the width. Wrist is two slots. A lore item fills only one of a wrist, finger, or ear pair.
- What's new dialog for 1.1.6.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.5
- Item Search filters by slot or type, usable class, and any stat present on catalog items, with an optional minimum. Primary, secondary, and tertiary sort keys each go ascending or descending. The primary key orders the list. Later keys only break ties. Token name matching, the slot filter, and the +0…+10 slider stay.
- Character sections and sub-sections collapse (down open, right closed). The choice is remembered. Items that can be merged sit above bags. An item icon is to the left of each name on that tab.
- BiS Owned only re-ranks every slot from owned items (worn, bags, bank, shared bank, Dragon's Hoard, storage, and any other imported container) with the same scoring, class, level, and single-haste rules. A recorded +N is used. A slot is empty only when nothing owned fits it. Item Search Owned only still hides names and keeps order.
- Merge list: https://eqlwiki.com/Item_Upgrade_System says all gear can be upgraded by merging an item of the same name, or a Mote of Potential. It does not say whether bags, other non-equipable items, or exaltations can be merged. Where the wiki is silent, equipable items are mergeable except names ending “(Exaltation)”, and non-equipable items, bags, and boxes are not. A stack in one slot is left out. Hoard and storage copies count.
- Inventory `Hoard N` rows are Dragon's Hoard. `Hoard N-SlotK` is that item's aug slot, not a bag. The KeyRing table is shown as Storage with Equipment, Augmentation, and Activated. The saved field name stays `keyring`. An export with no Hoard rows says to open the Dragon's Hoard window before `/outputfile inventory`.
- What's new dialog for 1.1.5.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.4
- Character item names use the same hover stat popup as the rest of the app. Click a name for Item Search, which opens the item stats panel, or eqlwiki. A name with no wiki page does not offer eqlwiki.
- Search My Bags is now the search bar at the top of Character. Each result is one copy, with the bag, bank, slot, or other container it is in. Click a result to scroll to that slot and highlight it.
- Character lists items that can be merged: the same item (base name, tier, and id) in more than one place. A Location Count greater than 1 is a stack in one slot and is left out. The inventory file and the catalog have no other merge rule, so anything else is left out. Rule id: `same-item-separate-copies-exclude-location-stacks`.
- Dragon hoard: `/outputfile inventory` in this repo has no hoard item table. Location rows whose token is a dragon hoard are included. A raw Dragon Hoard section that is not an item table stays under Other sections and is not turned into items. If the import has no hoard rows, the Character tab says so.
- An item stat popup closes when the pointer leaves its trigger. A detail fetch that finishes after that leave cannot show the popup again. Scroll, blur, tab changes, Escape, an outside click, and the close control also dismiss it. Menus already closed on Escape and an outside click; they now have a Close control too.
- What's new dialog for 1.1.4.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.3
- Inventory dumps are read by their column headers, anywhere in the file. A header row is not an item. Table 1 is Location, Name, ID, Count, and Slots. Table 2 is KeyRing, Name, and ID. Nested slots stay on the item they belong to. Bags, bank, shared bank, depot, and key rings are included. A section the parser does not recognise is kept as the header and line text.
- With an EQ folder set, the app watches for inventory dumps and imports one after the file stops changing, including a delete-and-recreate. Auto-import follows the chosen character file, or the newest dump when none is chosen. Dropping a file on the window imports it only when it is an inventory dump. Anything else is rejected.
- The Character tab shows worn gear, bags, bank, shared bank, depot, and key rings from the last import. Empty slots can be hidden. A name that is not in the catalog is marked unknown. Stats are not added.
- Best in Slot and Item Search mark a name from the last import with an Owned badge. Owned only hides names you do not have. Scores and order stay the same.
- What's new dialog for 1.1.3.
- Version bump across package.json, package-lock.json, and version.py sources.

## 1.1.2
- After an update, the app rebuilds parser data from the log in the background. That rebuild no longer freezes the rest of the app. Best in Slot icons and the other pages keep working while it runs, and the Parser tab refreshes once when it finishes.
- If the rebuild stops moving for a minute, the Parser tab says so. A thread stack is saved to logs\parser-stall.log in the app data folder.
- One app window per user. Main-process and sidecar output is written under logs in the app data folder, so a stuck launch leaves a trace.
- 1.1.1 also fixed a first launch that could stop with "database is locked" (PR #43). The 1.1.1 notes missed that.
- Version bump across package.json, package-lock.json, and version.py sources.

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
