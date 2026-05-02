# -*- mode: python ; coding: utf-8 -*-
# build_windows.spec — PyInstaller spec for Salva Suite Windows distribution.
# Usage: python -m PyInstaller build_windows.spec
import glob
import os

block_cipher = None
APP_NAME = "Salva Suite"

from PyInstaller.utils.hooks import collect_all

# --- Third-party package collection (dynamic imports need full tree) ---
deep_trans_datas, deep_trans_bins, deep_trans_hidden = collect_all('deep_translator')
pandas_datas,     pandas_bins,     pandas_hidden     = collect_all('pandas')
pywinauto_datas,  pywinauto_bins,  pywinauto_hidden  = collect_all('pywinauto')

# --- Config files: bundle defaults, never bundle auth tokens or backups ---
_SKIP_CONFIG = {'esi_session.json'}
config_datas = []
for _f in sorted(glob.glob('config/*.json')):
    _name = os.path.basename(_f)
    if _name in _SKIP_CONFIG or _name.endswith('.bak.json'):
        continue
    config_datas.append((_f, 'config'))

# ---------------------------------------------------------------------------
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=(
        deep_trans_bins +
        pandas_bins +
        pywinauto_bins
    ),
    datas=(
        [
            # Static assets (images, audio)
            ('assets',               'assets'),
            # Root-level icon
            ('icon.ico',             '.'),
            # OCR hotfix — loaded by pyi_rthook_ocr_hotfix at startup
            ('sitecustomize.py',     '.'),
        ] +
        # translator_config.json may be gitignored; include only when present
        ([('translator_config.json', '.')] if os.path.exists('translator_config.json') else []) +
        config_datas +
        deep_trans_datas +
        pandas_datas +
        pywinauto_datas
    ),
    hiddenimports=(
        [
            # ---- PySide6 extras not always auto-detected ----
            'PySide6.QtCharts',
            'PySide6.QtSvg',
            'PySide6.QtSvgWidgets',
            'PySide6.QtOpenGL',
            'PySide6.QtOpenGLWidgets',
            'PySide6.QtMultimedia',
            'PySide6.QtMultimediaWidgets',

            # ---- pywin32 ----
            'win32con', 'win32api', 'win32gui', 'win32ui',
            'win32process', 'win32security', 'win32event',
            'pywintypes',

            # ---- Pillow ----
            'PIL', 'PIL.Image', 'PIL.ImageDraw',
            'PIL.ImageFont', 'PIL.ImageFilter', 'PIL.ImageOps',

            # ---- numpy / pandas extras ----
            'numpy.core._methods',
            'numpy.lib.format',

            # ---- requests ----
            'requests.adapters',
            'requests.auth',
            'requests.packages',
            'urllib3',
            'charset_normalizer',
            'certifi',
            'idna',

            # ---- OCR / automation ----
            'pytesseract',
            'pywinauto',
            'pywinauto.application',
            'pywinauto.findwindows',

            # ---- stdlib extras PyInstaller sometimes misses ----
            'sqlite3', '_sqlite3',
            'psutil', 'psutil._pswindows',
            'logging.handlers',
        ] +
        deep_trans_hidden +
        pandas_hidden +
        pywinauto_hidden
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rthook_ocr_hotfix.py'],
    excludes=[
        # Web UI stack — not used in the desktop build
        'streamlit', 'plotly', 'tornado', 'altair', 'bokeh',
        # Qt fallback (PySide6 is used directly)
        'PyQt6', 'PyQt5',
        # Python GUI toolkit not needed (Qt handles everything)
        'tkinter', '_tkinter', 'tkinter.messagebox',
        # Heavy scientific/ML libs not in the app
        'matplotlib', 'scipy', 'sklearn', 'sklearn',
        'IPython', 'jupyter', 'notebook', 'nbformat',
        # pyautogui not installed / not required at runtime
        'pyautogui',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                 # No console window — pure GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        # Never compress Qt DLLs — can break them
        'Qt*.dll',
        'PySide6\\*.pyd',
        'PySide6\\plugins\\*',
        'python3*.dll',
    ],
    name=APP_NAME,
)
