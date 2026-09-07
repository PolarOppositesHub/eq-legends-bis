# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.8 — READY FOR OVERNIGHT WINDOWS SHIP / GitHub Release**
Canonical: backend/app/{main,engine,scoring,ac_softcap,quest_guides,class_roles,item_catalog,weapon_dps,zones,inventory,races,paths,character_pools,spell_buffs}.py + frontend **App.jsx** (+ styles.css) + desktop/main.js

**Agent cannot** build Windows `.exe` or create GitHub Releases. Overnight grok bot / Josh publishes from **main**.

## Ship checklist (overnight / Josh)
- [ ] `main` at **1.0.8** (this handoff)
- [ ] Windows rebuild: `powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1`
- [ ] Prefer **NSIS** `EQ-Legends-BiS-1.0.8-win-x64.exe`; portable also built
- [ ] Publish GitHub Release **v1.0.8** + `latest.yml`
- [ ] After install: header **UI 1.0.8** (and API · v1.0.8)

## Why 1.0.8 (after 1.0.7)
- BiS icons: eqlwiki 16-bit PNGs blank in Chromium → convert to 8-bit on download (Pillow)
- BiS hover tip to the right of cursor; weapon HandMod formulas hidden in UI (`why_ui`)
- Live Totals: eqlegendstools race+class+STA/INT/WIS pools (not gear-only)
- Simulator **Cast Buffs → Quick Buff** (max stacking lines for selected trio)
- Max AAs (sheet) toggle for Natural Durability / Eminence / Familiar-style AAs

## Smoke notes
- Versions: root / frontend / desktop package.json **1.0.8**; engine meta **1.0.8**; UI badge **UI 1.0.8**
- `POST /api/simulate` with `cast_buffs=quick` returns pool HP/Mana/END + active buff list
- Item icons ensure + serve as 8-bit PNG
- desktop/resources/backend/app synced (character_pools, spell_buffs, item_catalog, engine, races, main)
