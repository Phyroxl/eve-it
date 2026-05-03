import ctypes
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QColorDialog
from PySide6.QtGui import QColor

logger = logging.getLogger('eve.dialog_utils')

def make_replicator_dialog_topmost(dialog: QDialog):
    """
    Configura un diálogo para estar siempre por encima de las réplicas
    y de la Salva Suite, asegurando el foco.
    """
    try:
        # Flags de Qt
        flags = dialog.windowFlags()
        # Aseguramos Tool para que no aparezca en barra de tareas (opcional)
        # y StaysOnTopHint para el gestor de ventanas de Qt
        flags |= Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        dialog.setWindowFlags(flags)
        
        # No modal para permitir interactuar con réplicas si se desea
        # (Ajustes es NoModal por diseño en el Replicador)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        
        # Refuerzo Win32 (SetWindowPos HWND_TOPMOST)
        hwnd = int(dialog.winId())
        if hwnd:
            # HWND_TOPMOST = -1, SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=0x40
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            
    except Exception as e:
        logger.debug(f"Error setting topmost for dialog: {e}")

def pick_color_topmost(parent, initial_color_hex, title="Seleccionar Color"):
    """
    Abre un QColorDialog que se mantiene encima de los overlays.
    """
    dlg = QColorDialog(QColor(initial_color_hex), parent)
    dlg.setWindowTitle(title)
    
    # IMPORTANTE: Usar DontUseNativeDialog en Windows para poder controlar los flags
    # y que no se pierda detrás de ventanas topmost.
    dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
    if hasattr(QColorDialog.ColorDialogOption, 'ShowAlphaChannel'):
        dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel)
    
    make_replicator_dialog_topmost(dlg)
    
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.selectedColor().name()
    return None
