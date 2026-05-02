# Salva Suite — Windows Release Build Guide

## Overview

Salva Suite is packaged as a self-contained Windows directory using
**PyInstaller `--onedir`**.  The output is `dist/Salva Suite/` — a folder
you can zip and distribute.  Users only need to run `Salva Suite.exe`; no
Python installation is required on their machine.

---

## Prerequisites (build machine only)

| Requirement | Version | Install |
|---|---|---|
| Python | 3.10 – 3.14 | [python.org](https://www.python.org/) |
| pip | latest | `python -m pip install --upgrade pip` |
| PyInstaller | ≥ 6.0 | `pip install pyinstaller` |
| All app deps | see below | `pip install -r requirements.txt` |

```bat
pip install -r requirements.txt
pip install pyinstaller
```

---

## Building the Executable

### Option A — One-click (recommended)

```bat
build_windows.bat
```

Double-click or run from a command prompt in the project root.  The script
cleans previous artifacts, verifies dependencies, runs PyInstaller, and
reports the result.

### Option B — Manual PyInstaller command

```bat
python -m PyInstaller build_windows.spec --noconfirm --clean
```

### Output

```
dist/
└── Salva Suite/
    ├── Salva Suite.exe        ← launcher
    └── _internal/             ← Python runtime + all bundled files
        ├── assets/            ← images and audio
        ├── config/            ← default settings (writable at runtime)
        ├── PySide6/           ← Qt6 runtime
        └── ...
```

---

## Testing the Build

### On the build machine (quick check)

```bat
"dist\Salva Suite\Salva Suite.exe"
```

The splash screen should appear and the suite should open normally.

### On a clean machine (release validation)

1. Copy the entire `dist\Salva Suite\` folder to a machine **without Python**.
2. Run `Salva Suite.exe`.
3. Verify:
   - Splash screen appears.
   - Main suite window opens.
   - Market Command tab loads.
   - EVE OAuth login completes and orders load.

---

## What Is (and Isn't) Bundled

### Included in the build

| Path | Purpose |
|---|---|
| `assets/` | App icon, splash image, login/logoff sounds, flag images |
| `config/*.json` | Default settings (market filters, UI theme, tax overrides…) |
| `translator_config.json` | Chat translator language profiles |
| `icon.ico` | Window icon |
| `sitecustomize.py` | OCR sell-budget hotfix (loaded at startup) |

### Excluded from the build

| Path | Reason |
|---|---|
| `config/esi_session.json` | Contains OAuth refresh tokens — never bundle |
| `data/` | Runtime cache/database — created automatically on first run |
| `tests/`, `tools/`, `scratch/`, `docs/` | Dev-only |
| `streamlit`, `plotly` | Web UI stack — not used in the desktop build |

---

## External Dependencies (not bundled)

### Tesseract OCR  *(optional — Quick Order Update visual feature)*

The visual OCR feature calls the `tesseract` binary via subprocess.
It must be installed separately on each end-user machine if they want
to use Quick Order Update:

1. Download from <https://github.com/UB-Mannheim/tesseract/wiki>
2. Install to the default path (`C:\Program Files\Tesseract-OCR\`)
3. Add to `PATH` or configure the path in `config/quick_order_update.json`

The rest of the suite works without Tesseract.

---

## Runtime Data Locations

| Data | Location |
|---|---|
| Application logs | `%APPDATA%\EVEISKTracker\eve_isk_tracker.log` |
| User config (market filters, theme…) | `_internal\config\` (next to the exe) |
| Cache files (item metadata, history…) | `_internal\data\` (created on first run) |
| SQLite performance database | `_internal\data\market_performance.db` |

---

## Build Troubleshooting

### `ModuleNotFoundError` after launch

A dependency was not detected by PyInstaller's analysis.  Add it to the
`hiddenimports` list in `build_windows.spec` and rebuild.

### Blank window / Qt platform error

Make sure `PySide6\plugins\platforms\qwindows.dll` is present inside
`_internal\PySide6\plugins\platforms\`.  PyInstaller should include it
automatically; if not, add it manually from your PySide6 installation.

### Antivirus flags the exe

Self-contained PyInstaller executables are commonly flagged by heuristics.
Submit the file to your AV vendor for whitelisting, or sign it with a
code-signing certificate.

### Build takes very long or runs out of memory

Exclude unused heavy packages.  The `excludes` list in `build_windows.spec`
already removes `streamlit`, `plotly`, `matplotlib`, `scipy`, and `tkinter`.

---

## Distributing the Release

1. Build with `build_windows.bat`.
2. Test `dist\Salva Suite\Salva Suite.exe` on a clean machine.
3. Zip the `dist\Salva Suite\` folder:
   ```bat
   powershell Compress-Archive "dist\Salva Suite" "SalvaSuite_v1.0_win64.zip"
   ```
4. Share `SalvaSuite_v1.0_win64.zip`.

Users extract the zip and run `Salva Suite.exe` — no installer needed.
