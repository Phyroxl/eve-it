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
QTimer = C.QTimer; QApp = W.QApplication; QEvent = C.QEvent

from overlay.win32_capture import find_eve_windows
from overlay import replicator_config as cfg_mod
from overlay.replication_overlay import ReplicationOverlay

# 3. Estilo Visual Premium
STYLE = """
QWidget { background: #000000; color: #e0e0e0; font-family: 'Share Tech Mono', Consolas, monospace; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { background: transparent; border: none; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid rgba(0,200,255,0.4); border-radius: 4px; background: rgba(0,0,0,0.5); }
QCheckBox::indicator:checked { background: #00ff9d; border-color: #00ff9d; image: url(none); }
QPushButton.action_btn { 
    background: rgba(0,180,255,0.08); border: 1px solid rgba(0,180,255,0.3); border-radius: 6px; 
    color: #00c8ff; font-weight: bold; font-size: 10px;
}
QPushButton.action_btn:hover { background: rgba(0,180,255,0.2); border-color: #00c8ff; }
QPushButton#close_btn:hover { color: #ff4444; }
"""

# 4. HUB DE CONTROL (EL PANEL QUE BUSCAMOS)
class ReplicatorHub(W.QWidget):
    def __init__(self, cfg, initial_titles, region):
        super().__init__(None)
        self._cfg = cfg; self._region = region
        self._overlays = {}; self._handles = {}
        self._stale_handles = {} # [NUEVO] Cache para no perder handles en refrescos rápidos
        self._drag_pos = None
        
        self.setWindowTitle("Replicator Hub")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setMinimumSize(320, 480)
        self.setObjectName("ReplicatorHub")
        # Eliminada transparencia por hardware para evitar crasheos en algunos sistemas
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # FORZAR SIEMPRE ENCIMA (Nivel Win32)
        try:
            hwnd = int(self.winId())
            # HWND_TOPMOST = -1, SWP_NOMOVE = 2, SWP_NOSIZE = 1, SWP_SHOWWINDOW = 0x40
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        except Exception as e:
            print(f"Error forzando topmost: {e}")
        
        # Contenedor principal con fondo sólido para máxima estabilidad
        self._main_frame = W.QFrame(self)
        self._main_frame.setObjectName("MainFrame")
        self._main_frame.setStyleSheet("""
            QFrame#MainFrame {
                background: #050a15;
                border: 1px solid rgba(0,200,255,0.4);
                border-radius: 12px;
            }
        """)
        
        main_lay = QVBox(self); main_lay.setContentsMargins(0,0,0,0)
        main_lay.addWidget(self._main_frame)
        
        lay = QVBox(self._main_frame); lay.setContentsMargins(2,2,2,2); lay.setSpacing(0)
        
        # Cabecera Arrastrable
        hdr = W.QWidget()
        hdr.setFixedHeight(45)
        hdr.setStyleSheet("background: rgba(0,180,255,0.05); border-bottom: 1px solid rgba(0,180,255,0.15); border-top-left-radius: 11px; border-top-right-radius: 11px;")
        hl = QHBox(hdr); hl.setContentsMargins(15,0,10,0)
        
        title_icon = QLabel("⚡")
        title_icon.setStyleSheet("color: #00ff9d; font-size: 14px; border:none;")
        hl.addWidget(title_icon)
        
        t = QLabel("REPLICATOR HUB")
        t.setStyleSheet("color: #00c8ff; font-weight: 900; font-family: 'Orbitron'; letter-spacing: 2px; font-size: 11px; border:none;")
        hl.addWidget(t); hl.addStretch()
        
        # Botones de control (Minimizar / Compactar / Cerrar)
        b_min = QBtn("—"); b_min.setFixedSize(28, 28)
        b_min.setStyleSheet("QPushButton{background:transparent; border:none; color:rgba(200,230,255,0.4); font-size:14px;} QPushButton:hover{color:#00c8ff;}")
        b_min.clicked.connect(self.showMinimized)
        hl.addWidget(b_min)
        
        self.btn_comp = QBtn("▫"); self.btn_comp.setFixedSize(28, 28)
        self.btn_comp.setToolTip("Compactar Panel")
        self.btn_comp.setStyleSheet("QPushButton{background:transparent; border:none; color:rgba(200,230,255,0.4); font-size:16px;} QPushButton:hover{color:#00ff9d;}")
        self._is_compacted = False
        self.btn_comp.clicked.connect(self._toggle_compact_hub)
        hl.addWidget(self.btn_comp)
        
        bc = QBtn("✕"); bc.setObjectName("close_btn"); bc.setFixedSize(28, 28)
        bc.setStyleSheet("QPushButton{background:transparent; border:none; color:rgba(200,230,255,0.4); font-size:16px;} QPushButton:hover{color:#ff4444;}")
        bc.clicked.connect(self.close)
        hl.addWidget(bc)
        lay.addWidget(hdr)
        
        # Área de lista
        self._list_container = W.QWidget()
        llay = QVBox(self._list_container); llay.setContentsMargins(10,10,10,10)
        self._list = QList(); self._list.setSpacing(6)
        llay.addWidget(self._list)
        lay.addWidget(self._list_container)
        
        # Footer con botones de acción y PRESETS (NUEVO)
        self._footer = W.QWidget()
        self._footer.setFixedHeight(90) # Aumentado para presets
        self._footer.setStyleSheet("background: rgba(0,0,0,0.3); border-top: 1px solid rgba(0,180,255,0.1); border-bottom-left-radius: 11px; border-bottom-right-radius: 11px;")
        f_v = QVBox(self._footer); f_v.setContentsMargins(10, 10, 10, 10); f_v.setSpacing(10)
        
        # Presets Row
        p_lay = QHBox(); p_lay.setSpacing(8)
        p_lay.addWidget(QLabel("PRESETS:")); p_lay.addStretch()
        
        btn_all = QBtn("TODOS"); btn_all.setFixedSize(65, 24); btn_all.setProperty("class", "action_btn")
        btn_all.clicked.connect(self._preset_all)
        btn_none = QBtn("NINGUNO"); btn_none.setFixedSize(65, 24); btn_none.setProperty("class", "action_btn")
        btn_none.clicked.connect(self._preset_none)
        
        p_lay.addWidget(btn_all); p_lay.addWidget(btn_none)
        f_v.addLayout(p_lay)
        
        # Action Buttons Row
        fl = QHBox(); fl.setSpacing(10)
        br = QBtn("🔄 REFRESCAR"); br.setFixedHeight(30); br.setCursor(Qt.PointingHandCursor)
        br.setProperty("class", "action_btn")
        br.clicked.connect(lambda: self.refresh_windows()); fl.addWidget(br, 1)
        
        bo = QBtn("✕ APAGAR"); bo.setFixedHeight(30); bo.setCursor(Qt.PointingHandCursor)
        bo.setStyleSheet("QPushButton{background: rgba(255,60,60,0.1); border: 1px solid rgba(255,60,60,0.4); border-radius: 6px; color: #ff8888; font-weight: bold; font-size: 10px;} QPushButton:hover{background:rgba(255,60,60,0.2); border-color:#ff4444;}")
        bo.clicked.connect(self.close_all); fl.addWidget(bo, 1)
        f_v.addLayout(fl)
        
        lay.addWidget(self._footer)
        
        self.setStyleSheet(STYLE)
        
        # Eventos de arrastre
        hdr.mousePressEvent = self._hdr_press
        hdr.mouseMoveEvent = self._hdr_move
        hdr.mouseReleaseEvent = self._hdr_release
        
        self._timer = QTimer(); self._timer.timeout.connect(lambda: self.refresh_windows()); self._timer.start(5000)
        QTimer.singleShot(100, lambda: self.refresh_windows(initial_titles))

        # Timer de Persistencia Always-on-Top (Evita que EVE lo oculte al activarse)
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(1500) # Re-afirmar cada 1.5 seg

    def _toggle_compact_hub(self):
        self._is_compacted = not self._is_compacted
        if self._is_compacted:
            self._list_container.hide()
            self._footer.hide()
            self.setMinimumHeight(45)
            self.setFixedHeight(45)
            self.btn_comp.setText("▣")
        else:
            self._list_container.show()
            self._footer.show()
            self.setMinimumHeight(480)
            self.setMaximumHeight(1000)
            self.resize(self.width(), 480)
            self.btn_comp.setText("▫")

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if not self.isMinimized() and not self._is_compacted:
                # Forzar redibujado y tamaño al restaurar
                self.setMinimumHeight(480)
                self.resize(self.width(), 480)
        super().changeEvent(event)

    def _reassert_topmost(self):
        """Re-afirma el estado HWND_TOPMOST via Win32 API."""
        try:
            hwnd = int(self.winId())
            # HWND_TOPMOST = -1, SWP_NOMOVE = 2, SWP_NOSIZE = 1, SWP_NOACTIVATE = 0x10
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except: pass

    def _hdr_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._drag_pos = event.globalPosition().toPoint()
    def _hdr_move(self, event):
        if self._drag_pos:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta); self._drag_pos = event.globalPosition().toPoint()
    def _hdr_release(self, event): self._drag_pos = None

    def refresh_windows(self, force_titles=None):
        if not isinstance(force_titles, (list, tuple)): force_titles = None
        try:
            current = find_eve_windows()
            # Actualizar handles de forma incremental para evitar "parpadeos" de binding
            new_handles = {w['title']: w['hwnd'] for w in current}
            self._handles.update(new_handles)
            
            # Limpiar handles de ventanas que ya no existen (opcional, pero ayuda a la salud del dict)
            # Solo limpiamos si el título no está en uso por un overlay activo
            current_titles = set(new_handles.keys())
            active_titles = set(self._overlays.keys())
            for t in list(self._handles.keys()):
                if t not in current_titles and t not in active_titles:
                    del self._handles[t]

            active = force_titles if force_titles is not None else [t for t, ov in self._overlays.items()]
            
            # Guardar estado de scroll
            sbar = self._list.verticalScrollBar()
            sval = sbar.value()
            
            self._list.clear()
            for w in current:
                title = w['title']
                clean_name = title.replace("EVE - ", "").strip()
                is_running = title in self._overlays
                
                item = QItem(self._list)
                row = CharacterRow(title, clean_name, title in active or is_running, 
                                 is_running, self._toggle, self._adj_op)
                item.setSizeHint(row.sizeHint())
                self._list.addItem(item)
                self._list.setItemWidget(item, row)
                
                if (title in active or title in self._overlays) and title not in self._overlays:
                    self._launch_one(title)
            
            sbar.setValue(sval)
        except Exception as e:
            print(f"Error refresh: {e}")

    def _preset_all(self):
        current = find_eve_windows()
        titles = [w['title'] for w in current]
        self.refresh_windows(titles)

    def _preset_none(self):
        self.close_all()

    def _toggle(self, title, active):
        if active: self._launch_one(title)
        else: self._stop_one(title)

    def _launch_one(self, title):
        if title in self._overlays: return
        h = self._handles.get(title)
        if not h:
            # Si no hay handle, intentar un refresco rápido por si la ventana acaba de aparecer
            self.refresh_windows()
            h = self._handles.get(title)
            if not h: return

        try:
            ov = ReplicationOverlay(title=title, hwnd=h,
                                    region_rel=self._region, cfg=self._cfg, save_callback=self._save)
            ov.show()
            self._overlays[title] = ov
        except Exception as e:
            import logging
            logging.getLogger('eve.replicator').error(f"Error lanzando réplica '{title}': {e}")

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

# Widget personalizado para las filas de la lista (Estilo Foto)
class CharacterRow(W.QWidget):
    def __init__(self, title, clean_name, checked, is_running, toggle_cb, opacity_cb):
        super().__init__()
        self.title = title
        self.toggle_cb = toggle_cb
        self.opacity_cb = opacity_cb
        
        lay = QHBox(self); lay.setContentsMargins(15,8,15,8); lay.setSpacing(12)
        
        # 1. Ticker (Izquierda)
        self.chk = W.QCheckBox()
        self.chk.setChecked(checked)
        self.chk.setCursor(Qt.PointingHandCursor)
        self.chk.setFixedSize(20, 20)
        self.chk.setStyleSheet("""
            QCheckBox::indicator {
                width: 16px; height: 16px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(0,180,255,0.3);
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background: #00ff9d;
                border-color: #00ff9d;
                image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'><path d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>");
            }
        """)
        self.chk.toggled.connect(lambda v: self.toggle_cb(self.title, v))
        lay.addWidget(self.chk)
        
        # 2. Info (Centro)
        info_v = QVBox(); info_v.setSpacing(1)
        self.name = QLabel(clean_name.upper())
        self.name.setStyleSheet("color: white; font-weight: 900; font-size: 10px; letter-spacing: 1px;")
        
        status_lbl = QLabel("● ACTIVE" if is_running else "○ STANDBY")
        status_color = "#00ff9d" if is_running else "#4a5568"
        status_lbl.setStyleSheet(f"color: {status_color}; font-size: 8px; font-weight: bold;")
        
        info_v.addWidget(self.name)
        info_v.addWidget(status_lbl)
        lay.addLayout(info_v); lay.addStretch()
        
        # 3. Controles (Derecha)
        b_lay = QHBox(); b_lay.setSpacing(4)
        b1 = QBtn("-"); b1.setFixedSize(22, 20); b1.setStyleSheet("QPushButton{background:rgba(0,180,255,0.05); border:1px solid rgba(0,180,255,0.1); border-radius:3px; color:#00c8ff; font-size:10px;} QPushButton:hover{background:rgba(0,180,255,0.15);}")
        b1.clicked.connect(lambda: self.opacity_cb(self.title, -0.1))
        b2 = QBtn("+"); b2.setFixedSize(22, 20); b2.setStyleSheet("QPushButton{background:rgba(0,180,255,0.05); border:1px solid rgba(0,180,255,0.1); border-radius:3px; color:#00c8ff; font-size:10px;} QPushButton:hover{background:rgba(0,180,255,0.15);}")
        b2.clicked.connect(lambda: self.opacity_cb(self.title, 0.1))
        b_lay.addWidget(b1); b_lay.addWidget(b2)
        lay.addLayout(b_lay)
        
        self.setObjectName("CharRow")
        self.setStyleSheet("""
            QWidget#CharRow { background: rgba(0,0,0,0.3); border: 1px solid rgba(0,180,255,0.05); border-radius: 8px; }
            QWidget#CharRow:hover { background: rgba(0,180,255,0.08); border-color: rgba(0,180,255,0.2); }
        """)

# 5. ASISTENTE (DISEÑO LIMPIO)
class ReplicatorWizard(W.QDialog):
    def __init__(self, cfg):
        super().__init__(None)
        self._cfg = cfg; self._res = None
        self.setWindowTitle("EVE Replicator Setup")
        self.setFixedSize(450, 550)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._frame = W.QFrame(self)
        self._frame.setStyleSheet("""
            QFrame { background: #050a15; border: 1px solid rgba(0,200,255,0.4); border-radius: 12px; }
        """)
        flay = QVBox(self); flay.setContentsMargins(0,0,0,0); flay.addWidget(self._frame)
        
        lay = QVBox(self._frame); lay.setContentsMargins(25,25,25,25); lay.setSpacing(15)
        
        t1 = QLabel("⚡ CONFIGURACIÓN DE RÉPLICAS")
        t1.setStyleSheet("color: #00c8ff; font-family: 'Orbitron'; font-weight: bold; font-size: 14px; border:none;")
        lay.addWidget(t1)
        
        lay.addWidget(QLabel("1. SELECCIONA CUENTAS ACTIVAS"))
        self._list = QList(); self._list.setFixedHeight(180)
        self._list.setStyleSheet("QListWidget { background: rgba(0,0,0,0.3); border: 1px solid rgba(0,180,255,0.2); border-radius: 6px; }")
        lay.addWidget(self._list)
        for w in find_eve_windows():
            it = QItem(f"  {w['title']}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setForeground(G.QColor("#e0e0e0"))
            self._list.addItem(it)
            
        lay.addWidget(QLabel("2. DEFINE REGIÓN A CLONAR (P.EJ. LOCAL)"))
        self._lr = QLabel("Región no definida"); self._lr.setStyleSheet("color: rgba(200,230,255,0.5); font-size: 10px;")
        lay.addWidget(self._lr)
        
        self._reg = None
        bs = QBtn("✂ SELECCIONAR ÁREA EN PANTALLA")
        bs.setFixedHeight(40); bs.setCursor(Qt.PointingHandCursor)
        bs.setStyleSheet("QPushButton { background: rgba(0,180,255,0.1); border: 1px solid #00c8ff; color: #00c8ff; border-radius: 6px; font-weight: bold; } QPushButton:hover { background: rgba(0,180,255,0.2); }")
        bs.clicked.connect(self._sel); lay.addWidget(bs)
        
        lay.addStretch()
        
        b_box = QHBox()
        bc = QBtn("CANCELAR")
        bc.setFixedHeight(35); bc.setStyleSheet("QPushButton { background: transparent; color: rgba(255,255,255,0.4); border:none; } QPushButton:hover { color: white; }")
        bc.clicked.connect(self.reject); b_box.addWidget(bc)
        
        bf = QBtn("LANZAR REPLICADOR 🚀")
        bf.setFixedHeight(40); bf.setCursor(Qt.PointingHandCursor)
        bf.setStyleSheet("QPushButton { background: #00c8ff; color: black; border-radius: 6px; font-weight: bold; font-size: 12px; } QPushButton:hover { background: #00ff9d; }")
        bf.clicked.connect(self._fin); b_box.addWidget(bf)
        lay.addLayout(b_box)

    def _sel(self):
        self.hide()
        from overlay.region_selector import select_region
        r = select_region()
        self.show(); self.raise_(); self.activateWindow()
        if r:
            self._reg = r
            self._lr.setText(f"✓ Zona capturada: {r['w']*100:.1f}% x {r['h']*100:.1f}%")
            self._lr.setStyleSheet("color: #00ff9d; font-size: 10px; font-weight:bold;")

    def _fin(self):
        titles = [self._list.item(i).text().strip() for i in range(self._list.count()) if self._list.item(i).checkState() == Qt.CheckState.Checked]
        if not titles: 
            W.QMessageBox.warning(self, "Error", "Selecciona al menos una cuenta.")
            return
        if not self._reg:
            W.QMessageBox.warning(self, "Error", "Debes seleccionar un área de pantalla.")
            return
        self._res = (titles, self._reg)
        self.accept()

# 6. ARRANQUE
def main():
    app = QApp(sys.argv)
    cfg = cfg_mod.load()
    
    titles = cfg.get('selected_windows')
    region = cfg.get('region')
    
    # Crear HUB y mostrarlo
    hub = ReplicatorHub(cfg, [], region or {'x':0,'y':0,'w':0.1,'h':0.1})
    
    if not (titles and region):
        wiz = ReplicatorWizard(cfg)
        if wiz.exec() == W.QDialog.DialogCode.Accepted:
            titles, region = wiz._res
            hub._region = region
            hub.refresh_windows(titles)
            hub.show(); hub.raise_(); hub.activateWindow()
        else:
            sys.exit(0)
    else:
        hub.refresh_windows(titles)
        hub.show(); hub.raise_(); hub.activateWindow()
        
    app.exec()

if __name__ == "__main__":
    main()
