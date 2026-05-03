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

REPLICATOR_STYLE = """
QDialog { background: #05070a; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
QTabWidget::pane { background: #0b1016; border: 1px solid #1e293b; }
QTabBar::tab { background: #0b1016; color: #64748b; padding: 6px 14px;
               border: 1px solid #1e293b; border-bottom: none; }
QTabBar::tab:selected { background: #05070a; color: #00c8ff; border-bottom: 1px solid #05070a; }
QLabel { color: #94a3b8; font-size: 11px; }
QLabel#section { color: #00c8ff; font-size: 10px; font-weight: 800;
                 letter-spacing: 1px; margin-top: 6px; }
QCheckBox { color: #e2e8f0; font-size: 11px; }
QCheckBox::indicator { width: 14px; height: 14px; background: #1e293b;
                       border: 1px solid #334155; border-radius: 2px; }
QCheckBox::indicator:checked { background: #00c8ff; border-color: #00c8ff; }
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
    background: #1e293b; border: 1px solid #334155;
    color: #e2e8f0; padding: 3px 6px; border-radius: 3px; font-size: 11px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: #1e293b; border-left: 1px solid #334155; width: 18px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #2d3748;
}
QPushButton {
    background: rgba(0,200,255,0.1); border: 1px solid rgba(0,200,255,0.3);
    color: #00c8ff; padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: 700;
}
QPushButton:hover { background: rgba(0,200,255,0.25); border-color: #00c8ff; }
QPushButton#close { background: rgba(255,50,50,0.1); border-color: rgba(255,50,50,0.3);
                    color: #ef4444; }
QPushButton#close:hover { background: rgba(255,50,50,0.25); }
QPushButton#green { background: rgba(0,255,100,0.1); border-color: rgba(0,255,100,0.3);
                    color: #00ff64; }
QPushButton#green:hover { background: rgba(0,255,100,0.25); border-color: #00ff64; }
QPushButton#blue { background: rgba(0,180,255,0.1); border-color: rgba(0,180,255,0.3);
                   color: #00c8ff; }
QPushButton#blue:hover { background: rgba(0,180,255,0.25); border-color: #00c8ff; }
QPushButton#primary { background: rgba(0,200,255,0.2); border-color: #00e0ff; color: #00ffff; }
QPushButton#primary:hover { background: rgba(0,200,255,0.35); border-color: #00ffff; }
"""

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

def make_replicator_dialog_topmost(dialog: QDialog, modal: bool = False):
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
        
        target_flags = flags | topmost_flag | tool_flag
        if flags != target_flags:
            was_visible = dialog.isVisible()
            dialog.setWindowFlags(target_flags)
            if was_visible:
                dialog.show()
        
        # Modalidad
        modality_key = 'ApplicationModal' if modal else 'NonModal'
        target_modality = _get_qt_attr(Qt, modality_key, 2 if modal else 0)
        if dialog.windowModality() != target_modality:
            dialog.setWindowModality(target_modality)
        
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
    
    make_replicator_dialog_topmost(dlg, modal=True)
    
    res = dlg.exec() if hasattr(dlg, 'exec') else dlg.exec_()
    accepted = _get_qt_attr(QDialog, 'Accepted', 1)
    
    if res == accepted:
        return dlg.selectedColor().name()
    return None
