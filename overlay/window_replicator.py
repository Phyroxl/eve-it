"""
window_replicator.py — Versión ULTRA-LITE (Sin Panel de Control)
Lanza las réplicas directamente para evitar interferencias y congelamientos.
"""

from __future__ import annotations
import sys
import ctypes
from pathlib import Path

# Configuración de Rutas
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Carga de Qt
try:
    from PySide6 import QtWidgets as W, QtCore as C
    Qt = C.Qt
except ImportError:
    import PyQt6.QtWidgets as W, PyQt6.QtCore as C
    Qt = C.Qt

from overlay.win32_capture import find_eve_windows
from overlay import replicator_config as cfg_mod
from overlay.replication_overlay import ReplicationOverlay

def launch_overlays(cfg, titles, region):
    """Lanza las réplicas seleccionadas sin necesidad de un panel de control."""
    overlays = []
    current_eve = find_eve_windows()
    
    # Callback para guardar cambios de posición/ROI de forma individual
    def save_cb(t, x, y, w, h, op, ct):
        cfg_mod.save_overlay_state(cfg, t, x, y, w, h, op, ct)

    for title in titles:
        # Encontrar handle fresco para este título
        h = next((w['hwnd'] for w in current_eve if w['title'] == title), None)
        if not h:
            print(f"Advertencia: No se encontró la ventana '{title}'")
            continue
            
        try:
            ov = ReplicationOverlay(
                title=title, 
                hwnd=h, 
                region_rel=region, 
                cfg=cfg, 
                save_callback=save_cb
            )
            ov.show()
            overlays.append(ov)
        except Exception as e:
            print(f"Error lanzando réplica '{title}': {e}")
            
    return overlays

def main():
    app = W.QApplication(sys.argv)
    cfg = cfg_mod.load()
    
    titles = cfg.get('selected_windows', [])
    region = cfg.get('region', {'x':0,'y':0,'w':0.1,'h':0.1})
    
    # Si no hay configuración o no hay ventanas seleccionadas, lanzamos el asistente
    if not titles or not region:
        from overlay.window_replicator import ReplicatorWizard
        wiz = ReplicatorWizard(cfg)
        if wiz.exec() == W.QDialog.DialogCode.Accepted:
            titles, region = wiz._res
            # Guardar selección para la próxima vez
            cfg['selected_windows'] = titles
            cfg['region'] = region
            cfg_mod.save(cfg)
        else:
            sys.exit(0)

    # Lanzar réplicas directamente
    print(f"Iniciando {len(titles)} réplicas...")
    overlays = launch_overlays(cfg, titles, region)
    
    if not overlays:
        print("No se pudo iniciar ninguna réplica. Abortando.")
        sys.exit(1)

    sys.exit(app.exec())

if __name__ == "__main__":
    # Importar ReplicatorWizard solo si es necesario para evitar dependencias circulares
    # Pero como está en el mismo archivo originalmente, lo mantenemos o lo importamos dinámicamente.
    # Para esta versión ULTRA-LITE, asumimos que el Wizard sigue en el archivo o se importa de la versión previa.
    # Dado que estamos sobreescribiendo el archivo, incluiré una versión mínima del Wizard aquí también.
    
    class ReplicatorWizard(W.QDialog):
        def __init__(self, cfg):
            super().__init__(None)
            self._cfg = cfg; self._res = None
            self.setWindowTitle("EVE Replicator Setup")
            self.setFixedSize(400, 300)
            lay = W.QVBoxLayout(self)
            lay.addWidget(W.QLabel("<b>ASISTENTE DE CONFIGURACIÓN</b>"))
            
            self._list = W.QListWidget()
            for w in find_eve_windows():
                it = W.QListWidgetItem(f"  {w['title']}")
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked)
                self._list.addItem(it)
            lay.addWidget(self._list)
            
            btn_sel = W.QPushButton("1. SELECCIONAR REGIÓN")
            btn_sel.clicked.connect(self._sel); lay.addWidget(btn_sel)
            
            self._btn_fin = W.QPushButton("2. LANZAR RÉPLICAS")
            self._btn_fin.setEnabled(False)
            self._btn_fin.clicked.connect(self._fin); lay.addWidget(self._btn_fin)
            
            self._reg = None

        def _sel(self):
            self.hide()
            from overlay.region_selector import select_region
            r = select_region()
            self.show()
            if r:
                self._reg = r
                self._btn_fin.setEnabled(True)

        def _fin(self):
            titles = [self._list.item(i).text().strip() for i in range(self._list.count()) if self._list.item(i).checkState() == Qt.CheckState.Checked]
            if titles and self._reg:
                self._res = (titles, self._reg)
                self.accept()

    main()
