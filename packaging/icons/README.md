# EQ Legends BiS desktop app icon

Josh-chosen art **D — dragon-eye seal** (dark teal + gold eye, BiS checklist badge).

Do not invent or regenerate the illustration. Resize/crop only via `scripts/make_app_icon.py`.

## Source (committed as-provided)

| File | Role |
| --- | --- |
| `eq-legends-bis-icon-chosen.png` | Chosen source (16:9 canvas; JPEG bytes in a `.png` name) |
| `eq-legends-bis-icon-D-dragon-eye.png` | Identical copy of the chosen source |

## Generated from that PNG only

| File | Role |
| --- | --- |
| `eq-legends-bis.ico` | Multi-size Windows ICO: 16, 24, 32, 48, 64, 128, 256 |
| `eq-legends-bis.png` | Square crop of the seal (native crop size) |
| `eq-legends-bis-512.png` | 512×512 PNG (Linux / electron-builder fallback) |

Regenerate:

```bash
python3 scripts/make_app_icon.py
```

## electron-builder / Electron paths

`directories.buildResources` is `desktop/build`. The script also writes:

| File | Role |
| --- | --- |
| `desktop/build/icon.ico` | **`build.win.icon`** — NSIS exe, portable exe, installer, shortcuts |
| `desktop/build/icon.png` | `build.linux.icon` + BrowserWindow fallback |

`desktop/package.json`:

- `build.icon` / `build.win.icon` → `build/icon.ico`
- `build.nsis.installerIcon` / `uninstallerIcon` / `installerHeaderIcon` → `icon.ico` (resolved under `buildResources`)
- `desktop/main.js` BrowserWindow `icon` → `desktop/build/icon.ico` (also listed in `build.files` so it is inside the asar)

Version stays **1.0.18** until the next ship batch (planned 1.0.19). Do not pack Windows in this change.
