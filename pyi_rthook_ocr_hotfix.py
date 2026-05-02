"""
pyi_rthook_ocr_hotfix.py — PyInstaller runtime hook.
Loads sitecustomize.py from the bundle root so the OCR sell-budget
hotfix is applied before EveMarketVisualDetector is first imported.
"""
import sys
import os
import importlib.util

try:
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        hook_path = os.path.join(meipass, 'sitecustomize.py')
        if os.path.exists(hook_path):
            spec = importlib.util.spec_from_file_location('sitecustomize', hook_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules['sitecustomize'] = mod
            spec.loader.exec_module(mod)
except Exception:
    pass
