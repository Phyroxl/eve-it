"""
overlay_server.py — Servidor de datos para el overlay HUD.

Puente entre el tracker de Streamlit y la ventana overlay PyQt.
Escucha en OVERLAY_PORT y envía datos JSON cada segundo a todos los
clientes conectados (el overlay).

Arquitectura:
  Streamlit (tracker) → overlay_server.push(data) → socket → overlay PyQt

Uso desde app.py:
    from overlay.overlay_server import OverlayServer
    server = OverlayServer()
    server.start()
    server.push(data_dict)   # llamar en cada ciclo de actualización
    server.stop()
"""

import json
import socket
import threading
import time
from typing import Optional


OVERLAY_PORT = 47291

class OverlayServer:
    """Servidor de datos bidireccional para el HUD."""

    def __init__(self, port: int = OVERLAY_PORT, command_callback=None):
        self._port       = port
        self._clients:   list[socket.socket] = []
        self._clients_lock = threading.Lock()
        self._last_data: Optional[bytes]     = None
        self._server:    Optional[socket.socket] = None
        self._running    = False
        self._thread:    Optional[threading.Thread] = None
        self._cmd_cb     = command_callback

    def start(self):
        """Inicia el servidor en un hilo de fondo."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()

    def push(self, data: dict):
        """
        Envía datos a todos los clientes conectados.
        Llamar desde el loop principal de Streamlit (1.5s ciclo).
        """
        payload = json.dumps(data, default=str) + '\n'
        encoded = payload.encode('utf-8')
        self._last_data = encoded

        dead = []
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.sendall(encoded)
                except Exception:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
                try:
                    c.close()
                except Exception:
                    pass

    def _accept_loop(self):
        """Acepta conexiones entrantes del overlay."""
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind(('127.0.0.1', self._port))
            self._server.listen(5)
            self._server.settimeout(1.0)
        except OSError:
            # Puerto en uso — otra instancia del servidor ya está corriendo
            return

        while self._running:
            try:
                conn, _ = self._server.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # Enviar último payload inmediatamente al conectar
                if self._last_data:
                    try:
                        conn.sendall(self._last_data)
                    except Exception:
                        pass
                with self._clients_lock:
                    self._clients.append(conn)
                
                # Iniciar hilo de escucha por cliente
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_client(self, conn):
        """Escucha comandos del cliente."""
        while self._running:
            try:
                data = conn.recv(1024)
                if not data: break
                if self._cmd_cb:
                    cmds = data.decode('utf-8', errors='ignore').strip().split('\n')
                    for cmd in cmds:
                        if cmd: self._cmd_cb(cmd)
            except Exception:
                break
        with self._clients_lock:
            if conn in self._clients:
                self._clients.remove(conn)
        try:
            conn.close()
        except Exception:
            pass


def build_overlay_payload(tracker, now=None) -> dict:
    """
    Construye el payload de datos para el overlay desde el tracker.
    Llama a get_summary() y extrae los campos relevantes.
    """
    from datetime import datetime
    now = now or datetime.now()

    try:
        summary = tracker.get_summary(now)
    except Exception:
        return _empty_payload()

    total_isk     = summary.get('total_isk', 0)
    isk_h_rolling = summary.get('isk_per_hour_rolling', 0)
    isk_h_session = summary.get('isk_per_hour_total', 0)
    char_count    = summary.get('character_count', 0)
    session_dur   = summary.get('session_duration')
    session_secs  = int(session_dur.total_seconds()) if session_dur else 0

    # Agregar tick_info de todos los personajes (usar el más reciente con datos)
    countdown     = '--:--'
    cycle_isk     = 0
    is_estimated  = True
    tick_count    = 0
    secs_until    = 0

    per_char = summary.get('per_character', [])
    main_char = summary.get('main_character', '')

    if main_char:
        main_cd = next((cd for cd in per_char if cd.get('character') == main_char or cd.get('display_name') == main_char), None)
        if main_cd:
            ti = main_cd.get('tick_info', {})
            countdown    = ti.get('countdown_str', '--:--')
            cycle_isk    = ti.get('current_cycle_isk', 0)
            is_estimated = ti.get('is_estimated', True)
            tick_count   = ti.get('tick_count', 0)
            secs_until   = ti.get('secs_until_next', 0)
        else:
            countdown = 'No main'
    else:
        countdown = 'No main'

    # Lista simplificada de personajes para el overlay
    chars = []
    for cd in per_char[:6]:  # máximo 6 en overlay
        ti = cd.get('tick_info', {})
        chars.append({
            'name':   cd.get('display_name', cd.get('character', '?')),
            'isk_h':  cd.get('isk_per_hour', 0),
            'status': cd.get('status', 'idle'),
            'isk':    cd.get('total_isk', 0),
        })

    # Detectar QSettings de forma segura
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        try:
            from PyQt6.QtCore import QSettings
        except ImportError:
            QSettings = None

    hud_preset = "balanced"
    show_total = "true"
    show_tick  = "true"
    show_dur   = "true"

    if QSettings:
        try:
            s_hud = QSettings("EVEISKTracker", "Overlay")
            hud_preset = s_hud.value("preset", "balanced")
            show_total = s_hud.value("show_total", "true")
            show_tick  = s_hud.value("show_tick", "true")
            show_dur   = s_hud.value("show_dur", "true")
        except Exception:
            pass

    return {
        'connected':        True,
        'hud_preset':       hud_preset,
        'show_total':       show_total == "true",
        'show_tick':        show_tick == "true",
        'show_dur':         show_dur == "true",
        'total_isk':        total_isk,
        'isk_h_rolling':    isk_h_rolling,
        'isk_h_session':    isk_h_session,
        'char_count':       char_count,
        'session_secs':     session_secs,
        'countdown':        countdown,
        'cycle_isk':        cycle_isk,
        'is_estimated':     is_estimated,
        'tick_count':       tick_count,
        'secs_until_next':  secs_until,
        'characters':       chars,
        'all_char_names':   [cd.get('display_name', cd.get('character', '?')) for cd in per_char],
        'main_char':        main_char,
        'is_paused':        summary.get('is_paused', False),
        'ts':               now.isoformat(),
    }

def _empty_payload() -> dict:
    return {
        'connected': False,
        'total_isk': 0, 'isk_h_rolling': 0, 'isk_h_session': 0,
        'char_count': 0, 'session_secs': 0,
        'countdown': '--:--', 'cycle_isk': 0,
        'is_estimated': True, 'tick_count': 0, 'secs_until_next': 0,
        'characters': [], 'all_char_names': [], 'main_char': '', 'is_paused': False, 'ts': '',
    }
