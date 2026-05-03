# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Lista de archivos de configuración seguros para incluir en el build
# Excluimos expresamente esi_session.json y otros archivos con datos del usuario
config_files = [
    ('config/contracts_filters.json', 'config'),
    ('config/eve_client.json', 'config'),
    ('config/market_filters.json', 'config'),
    ('config/performance_config.json', 'config'),
    ('config/quick_order_update_regions.example.json', 'config'),
    ('config/replicator.json', 'config'),
    ('config/table_layouts.json', 'config'),
    ('config/tax_overrides.example.json', 'config'),
    ('config/ui_inventory.json', 'config'),
    ('config/ui_my_orders.json', 'config'),
    ('config/ui_theme_market_command.json', 'config'),
]

# Assets (Imágenes y Sonidos)
added_files = [
    ('assets', 'assets'),
] + config_files

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['__pycache__', '.git', 'venv', 'logs', 'scratch'],
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
    name='SalvaSuite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # Modo Ventana
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.png'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SalvaSuite',
)
