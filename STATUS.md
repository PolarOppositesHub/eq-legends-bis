# STATUS
App: /workspace (eq-legends-bis source)
Version: **1.0.11** — Bags + Quest Hub + Cast Buffs level-gate + Any Slots BiS
Canonical: backend/app/{main,engine,spell_buffs,quest_hub,quest_guides,scoring,inventory,...}.py + frontend App.jsx
Branch: `cursor/bags-quest-hub-d4a5` · PR https://github.com/PolarOppositesHub/eq-legends-bis/pull/9

**Agent cannot** build Windows `.exe` or create GitHub Releases.

## 1.0.11
- Search My Bags + Quest Hub + quieter inventory import
- **Cast Buffs / Quick Buff is level-gated** to Simulator Character Level (eqlwiki cast levels). Lower-rank lines added so L35 is not stuck waiting for L50 max spells (e.g. Symbol of Pinzarn instead of Naltron; no Resolution until L42).
- **ANY1 / ANY2** planner slots for EQ Legends worn Any Slot. BiS + Simulator include them; inventory `Location: Any Slot` maps into them. Scoring ignores weapon DMG/ratio in those slots (other stats still count); dedicated slots fill first.

## Overnight
Merge PR #9 → `main`, then `.\scripts\build-windows.ps1` → Release **v1.0.11**.
