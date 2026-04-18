"""
window_replicator.py — Versión DEFINITIVA y LIMPIA
"""

from __future__ import annotations
import sys
import subprocess
import ctypes
from pathlib import Path
from typing import Optional

# 1. Configuración de Rutas
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 2. Carga de Qt (Global)
from overlay import qt_loader
try:
    W, C, G, Qt = qt_loader.load_qt()
except Exception:
    # Fallback si falla el loader
    import PySide6.QtWidgets as W
    import PySide6.QtCore as C
    import PySide6.QtGui as G
    Qt = C.Qt

# Atajos Globales
QVBox = W.QVBoxLayout; QHBox = W.QHBoxLayout
QLabel = W.QLabel; QBtn = W.QPushButton
QList = W.QListWidget; QItem = W.QListWidgetItem
QTimer = C.QTimer; QApp = W.QApplication

from overlay.win32_capture import find_eve_windows
from overlay import replicator_config as cfg_mod
from overlay.replication_overlay import ReplicationOverlay

# 3. Estilo Visual
STYLE = """
QWidget { background: #080e1a; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QListWidget { background: #0b1528; border: 1px solid #00c8ff; border-radius: 4px; }
QPushButton { 
    background: #1a2a44; border: 1px solid #00c8ff; border-radius: 4px; 
    padding: 6px; color: #00c8ff; font-weight: bold;
}
QPushButton:hover { background: #253a5a; }
"""

# 4. HUB DE CONTROL (EL PANEL QUE BUSCAMOS)
class ReplicatorHub(W.QWidget):
    def __init__(self, cfg, initial_titles, region):
        super().__init__(None)
        self._cfg = cfg; self._region = region
        self._overlays = {}; self._handles = {}
        self._drag_pos = None
        
        self.setWindowTitle("EVE HUB")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setMinimumSize(280, 420)
        
        lay = QVBox(self); lay.setContentsMargins(10,10,10,10); lay.setSpacing(8)
        
        # Cabecera Arrastrable
        hdr = W.QWidget(); hdr.setStyleSheet("background: #00c8ff; border-radius: 4px;")
        hl = QHBox(hdr); hl.setContentsMargins(10,5,10,5)
        t = QLabel("CONTROL HUB"); t.setStyleSheet("color: black; font-weight: bold;")
        hl.addWidget(t); hl.addStretch()
        bc = W.QPushButton("✕"); bc.setFixedSize(20,20); bc.setStyleSheet("border:none; color:black; font-weight:bold;")
        bc.clicked.connect(self.close); hl.addWidget(bc)
        lay.addWidget(hdr)
        
        self._list = QList(); lay.addWidget(self._list)
        
        footer = QHBox()
        br = W.QPushButton("🔄"); br.setFixedWidth(40); br.clicked.connect(lambda: self.refresh_windows()); footer.addWidget(br)
        footer.addStretch()
        bo = W.QPushButton("✕ APAGAR TODO"); bo.setStyleSheet("background: #500; color: white;")
        bo.clicked.connect(self.close_all); footer.addWidget(bo)
        lay.addLayout(footer)
        
        self.setStyleSheet(STYLE + "\nQWidget { border: 2px solid #00c8ff; border-radius: 10px; }")
        
        self._timer = QTimer(); self._timer.timeout.connect(lambda: self.refresh_windows()); self._timer.start(5000)
        self.refresh_windows(initial_titles)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._drag_pos = event.globalPosition().toPoint()
    def mouseMoveEvent(self, event):
        if self._drag_pos:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta); self._drag_pos = event.globalPosition().toPoint()
    def mouseReleaseEvent(self, event): self._drag_pos = None

    def refresh_windows(self, force_titles=None):
        if not isinstance(force_titles, (list, tuple)): force_titles = None
        try:
            current = find_eve_windows()
            self._handles = {w['title']: w['hwnd'] for w in current}
            active = force_titles if force_titles is not None else [t for t, ov in self._overlays.items()]
            
            self._list.clear()
            for w in current:
                title = w['title']
                item = QItem(self._list)
                row = W.QWidget()
                rl = QHBox(row); rl.setContentsMargins(5,2,5,2); rl.setSpacing(5)
                
                chk = W.QCheckBox()
                chk.setChecked(title in active or title in self._overlays)
                chk.toggled.connect(lambda v, t=title: self._toggle(t, v))
                rl.addWidget(chk)
                
                name = QLabel(title[:14]); name.setStyleSheet("color: #00c8ff; font-size: 10px;")
                rl.addWidget(name); rl.addStretch()
                
                b1 = W.QPushButton("-"); b1.setFixedSize(22, 22); b1.clicked.connect(lambda _, t=title: self._adj_op(t, -0.1))
                b2 = W.QPushButton("+"); b2.setFixedSize(22, 22); b2.clicked.connect(lambda _, t=title: self._adj_op(t, 0.1))
                rl.addWidget(b1); rl.addWidget(b2)
                
                item.setSizeHint(row.sizeHint())
                self._list.setItemWidget(item, row)
                if chk.isChecked() and title not in self._overlays: self._launch_one(title)
        except: pass

    def _toggle(self, title, active):
        if active: self._launch_one(title)
        else: self._stop_one(title)

    def _launch_one(self, title):
        if title in self._overlays: return
        h = self._handles.get(title)
        if not h: return
        ov = ReplicationOverlay(title=title, hwnd_getter=lambda t=title: self._handles.get(t),
                                region_rel=self._region, cfg=self._cfg, save_callback=self._save)
        ov.show(); self._overlays[title] = ov

    def _stop_one(self, title):
        if title in self._overlays: self._overlays.pop(title).close()

    def _adj_op(self, title, d):
        if title in self._overlays:
            o = self._overlays[title]
            o.setWindowOpacity(max(0.1, min(1.0, o.windowOpacity() + d)))

    def close_all(self):
        for t in list(self._overlays.keys()): self._stop_one(t)
        self.refresh_windows([])

    def _save(self, t, x, y, w, h, op, ct):
        cfg_mod.save_overlay_state(self._cfg, t, x, y, w, h, op, ct)

# 5. ASISTENTE (DISEÑO LIMPIO)
class ReplicatorWizard(W.QDialog):
    def __init__(self, cfg):
        super().__init__(None)
        self._cfg = cfg; self._res = None
        self.setWindowTitle("EVE Replicator Setup")
        self.setFixedSize(450, 500)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)
        
        lay = QVBox(self); lay.setContentsMargins(20,20,20,20); lay.setSpacing(15)
        
        lay.addWidget(QLabel("1. SELECCIONA CUENTAS"))
        self._list = QList(); lay.addWidget(self._list)
        for w in find_eve_windows():
            it = QItem(f" {w['title']}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(it)
            
        lay.addWidget(QLabel("2. DEFINE REGIÓN"))
        self._lr = QLabel("Sin región"); lay.addWidget(self._lr)
        self._reg = None
        bs = W.QPushButton("✂ SELECCIONAR ÁREA EN PANTALLA")
        bs.clicked.connect(self._sel); lay.addWidget(bs)
        
        lay.addStretch()
        bf = W.QPushButton("LANZAR HUB Y RÉPLICAS 🚀")
        bf.setStyleSheet("background: #00c8ff; color: black; font-size: 14px;")
        bf.clicked.connect(self._fin); lay.addWidget(bf)

    def _sel(self):
        self.hide()
        from overlay.region_selector import select_region
        r = select_region()
        self.show(); self.raise_(); self.activateWindow()
        if r:
            self._reg = r
            self._lr.setText(f"Zona: {r['w']*100:.1f}% x {r['h']*100:.1f}%")

    def _fin(self):
        titles = [self._list.item(i).text().strip() for i in range(self._list.count()) if self._list.item(i).checkState() == Qt.CheckState.Checked]
        if not titles or not self._reg: return
        self._res = (titles, self._reg)
        self.accept()

# 6. ARRANQUE
def main():
    app = QApp(sys.argv)
    cfg = cfg_mod.load()
    
    titles = cfg.get('selected_windows')
    region = cfg.get('region')
    
    # Crear HUB oculto al principio
    hub = ReplicatorHub(cfg, [], region or {'x':0,'y':0,'w':0.1,'h':0.1})
    
    if not (titles and region):
        wiz = ReplicatorWizard(cfg)
        if wiz.exec() == W.QDialog.DialogCode.Accepted:
            titles, region = wiz._res
            hub._region = region
            hub.refresh_windows(titles)
        else:
            return

    hub.show(); hub.raise_(); hub.activateWindow()
    app.exec()

if __name__ == "__main__":
    main()
