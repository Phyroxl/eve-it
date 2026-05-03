import ctypes
import logging
# Qt shim
_qt_ok = False
for _qt_try in [
    ('PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'),
    ('PyQt6',   'PyQt6.QtWidgets',   'PyQt6.QtCore',   'PyQt6.QtGui'),
    ('PySide2', 'PySide2.QtWidgets', 'PySide2.QtCore', 'PySide2.QtGui'),
    ('PyQt5',   'PyQt5.QtWidgets',   'PyQt5.QtCore',   'PyQt5.QtGui'),
]:
    try:
        import importlib
        _w = importlib.import_module(_qt_try[1])
        _c = importlib.import_module(_qt_try[2])
        _g = importlib.import_module(_qt_try[3])
        QDialog = _w.QDialog
        QColorDialog = _w.QColorDialog
        Qt = _c.Qt
        QColor = _g.QColor
        _qt_ok = True
        break
    except ImportError:
        continue

if not _qt_ok:
    # Fallback minimalista para evitar crasheos si todo falla
    class Qt:
        class WindowType: WindowStaysOnTopHint = 0; Tool = 0
        class WindowModality: NonModal = 0
    class QDialog: pass
    class QColorDialog:
        class ColorDialogOption: DontUseNativeDialog = 0; ShowAlphaChannel = 0
        class DialogCode: Accepted = 1
    class QColor:
        def __init__(self, *args): pass
        def name(self): return "#ffffff"

logger = logging.getLogger('eve.dialog_utils')

# Helper para obtener atributos de forma compatible entre Qt5/Qt6
def _get_qt_attr(obj, name, default=None):
    if hasattr(obj, name):
        return getattr(obj, name)
    # Buscar en sub-enums si existen (Qt6 style)
    for enum_name in ['DialogCode', 'ColorDialogOption', 'WindowType', 'WindowModality']:
        enum_obj = getattr(obj, enum_name, None)
        if enum_obj and hasattr(enum_obj, name):
            return getattr(enum_obj, name)
    return default

def make_replicator_dialog_topmost(dialog: QDialog):
    """
    Configura un diálogo para estar siempre por encima de las réplicas
    y de la Salva Suite, asegurando el foco.
    """
    try:
        # Flags de Qt
        flags = dialog.windowFlags()
        
        # StaysOnTopHint y Tool
        topmost_flag = _get_qt_attr(Qt, 'WindowStaysOnTopHint', 0x00040000)
        tool_flag = _get_qt_attr(Qt, 'Tool', 0x00000001)
        flags |= topmost_flag | tool_flag
        dialog.setWindowFlags(flags)
        
        # No modal
        non_modal = _get_qt_attr(Qt, 'NonModal', 0)
        dialog.setWindowModality(non_modal)
        
        # Refuerzo Win32
        hwnd = int(dialog.winId())
        if hwnd:
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            
    except Exception as e:
        logger.debug(f"Error setting topmost for dialog: {e}")

def pick_color_topmost(parent, initial_color_hex, title="Seleccionar Color"):
    """
    Abre un QColorDialog que se mantiene encima de los overlays.
    """
    dlg = QColorDialog(QColor(initial_color_hex), parent)
    dlg.setWindowTitle(title)
    
    # DontUseNativeDialog
    dont_use_native = _get_qt_attr(QColorDialog, 'DontUseNativeDialog', 0)
    if dont_use_native:
        dlg.setOption(dont_use_native)
    
    show_alpha = _get_qt_attr(QColorDialog, 'ShowAlphaChannel', 0)
    if show_alpha:
        dlg.setOption(show_alpha)
    
    make_replicator_dialog_topmost(dlg)
    
    res = dlg.exec() if hasattr(dlg, 'exec') else dlg.exec_()
    accepted = _get_qt_attr(QDialog, 'Accepted', 1)
    
    if res == accepted:
        return dlg.selectedColor().name()
    return None
