
import sys
import os

# Add workspace to path
sys.path.append(r'c:\Users\Azode\Downloads\eve-it-main\eve-it-main')

try:
    from overlay.replicator_settings_dialog import ReplicatorSettingsDialog
    print("Import successful")
    # Mock overlay
    class MockOverlay:
        def __init__(self):
            self._title = "Test"
            self._cfg = {}
            self._ov_cfg = {}
            self.setStyleSheet = lambda x: None
            self.windowFlags = lambda: 0
            self.setWindowFlags = lambda x: None
            self.setMinimumWidth = lambda x: None
            self.setWindowTitle = lambda x: None
            self.winId = lambda: 0
            self.width = lambda: 360
            self.height = lambda: 420
            self.resize = lambda w, h: None
            
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    
    overlay = MockOverlay()
    print("Instantiating dialog...")
    dlg = ReplicatorSettingsDialog(overlay)
    print("Instantiation successful")
except Exception as e:
    import traceback
    traceback.print_exc()
