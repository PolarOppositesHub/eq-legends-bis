# Sim-tab Help button — numbered in-game steps

Copy-ready steps for a Help control. Steps cite Legends wiki or Legends community docs. Anything not Legends-documented is marked **UNKNOWN**.

---

1. **Log into EverQuest Legends** on the character whose gear you want to import.  
   Source: Posky import help (`.firecrawl/eqlposky-index.html`).

2. **Turn on logging** (needed so the game writes `eqlog_…` and so tools can see the dump announcement): type  
   `/log on`  
   in chat.  
   Sources: eqlwiki `/log`; EQL Log Reader / Spyxy / EQBuddy (“enable logging”).  
   Persistence: wiki says logging state persists across logins.

3. **Timestamps (for log parsers):** ensure chat log lines start with a bracketed date/time such as `[Tue Jul 21 …]`. Community docs say enable chat timestamps in **Options** if missing.  
   **UNKNOWN:** exact Options menu path / checkbox label on current Legends client.

4. **(Optional but recommended for full bags/bank)** Visit a banker; open **Bank**. If you store items in **Dragon’s Hoard**, open that window before dumping — community/wiki text: Hoard contents included only while that window is open.  
   Sources: Posky help; eqlwiki `/outputfile` inventory bullet.  
   **UNKNOWN:** whether every Legends build requires bank window open for bank rows (Posky advises opening Bank; dump fixtures include `Bank*` rows without proving window state).

5. **Dump inventory / worn gear to a file:** type  
   `/outputfile inventory`  
   (or `/outputfile` alone for in-game help per Posky).  
   Sources: eqlwiki; Posky; EQBuddy.

6. **Find the dump file** in the **EverQuest Legends install folder** (game root — **not** inside `Logs\`):  
   Typical path:  
   `C:\Users\Public\Daybreak Game Company\Installed Games\EverQuest Legends\`  
   Expected name shape (Legends community / wiki):  
   `<Character>_<server>-Inventory.txt`  
   Example from player-verified announcement: `Dranak_freeport-Inventory.txt`.  
   Sources: eqlwiki (“root folder”); EQBuddy `InventoryFile` / `OutputfileAutoImport`; Posky path (Posky’s on-screen `CharacterName-Inventory.txt` is a simplification — prefer `Char_server-Inventory.txt`).

7. **Confirm in the log (optional):** with logging on, the eqlog should gain a line like:  
   `[Thu Aug 20 18:47:36 2026] Outputfile Complete: Dranak_freeport-Inventory.txt`  
   Source: EQBuddy test constant (verbatim player log). Your timestamp and filename will differ.

8. **Import that `.txt` into the Sim tool** (file picker or paste). The file is tab-separated gear/inventory rows — **not** the whole eqlog.

---

## Example lines to show in Help (real)

**Inventory file (worn gear row):**

```
Head	Raw-Hide Skullcap +2	2137	1	10
```

Source: `samples/dranak-Inventory.txt`.

**Inventory file header:**

```
Location	Name	ID	Count	Slots
```

**Eqlog announcement only (gear body is in the Inventory.txt):**

```
[Thu Aug 20 18:47:36 2026] Outputfile Complete: Dranak_freeport-Inventory.txt
```

Source: EQBuddy `OutputfileAutoImportTests` RealLine.

---

## What this Help should **not** claim

- That worn gear appears as `Location	Name	…` rows **inside** `eqlog_*.txt` — **not evidenced**.
- That the dump includes AC/STR/resist **character** or **item stat columns** — inventory columns are only Location / Name / ID / Count / Slots (**no stat dump found**).
- A dedicated `/stats` file export — **UNKNOWN / not documented** on archived eqlwiki Commands for this research.
