"""
app.py — EVE ISK Tracker dashboard (Streamlit).
Orquestador principal modularizado.
"""

import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import time
import tempfile
import os

from core.session_tracker import MultiAccountTracker
from core.file_watcher import EVELogWatcher
from utils.demo_mode import DemoLogGenerator
from utils.i18n import t
from utils.eve_api import resolve_characters_async, get_cached, is_character_id

# Overlay HUD (importación lazy)
try:
    from overlay.overlay_server import OverlayServer, build_overlay_payload
    _OVERLAY_AVAILABLE = True
except ImportError:
    _OVERLAY_AVAILABLE = False

# ─── Configuración Streamlit ──────────────────────────────────────────────────
st.set_page_config(
    page_title="EVE ISK Tracker",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Imports Modularizados ──────────────────────────────────────────────────
from ui.dashboard.theme import render_theme
from ui.dashboard.state import init_session_state
from ui.dashboard.sidebar import render_sidebar
from ui.dashboard.welcome import render_welcome
from ui.dashboard.dashboard_view import render_dashboard_layout
from ui.dashboard.components.charts import render_charts_iframe, send_chart_data
from ui.dashboard.components.characters import render_chars_section

# Aplicar Estilos Globales
render_theme()

# ─── Funciones de Lógica de Negocio ───────────────────────────────────────────

def start_tracker(log_dir: str, demo_mode: bool = False):
    if st.session_state.watcher:
        st.session_state.watcher.stop()
    if st.session_state.demo_gen:
        st.session_state.demo_gen.stop()

    tracker = MultiAccountTracker(
        inactivity_threshold_minutes=st.session_state.inactivity_threshold
    )
    st.session_state.tracker = tracker
    st.session_state.session_start = datetime.now()
    st.session_state.char_resolved = set()
    st.session_state.chart_session_token += 1

    if demo_mode:
        demo_dir = tempfile.mkdtemp(prefix="eve_demo_")
        gen = DemoLogGenerator(demo_dir, activity=st.session_state.activity_type)
        chars = ["Capsuleer_Alpha", "Capsuleer_Beta", "Capsuleer_Gamma"][:st.session_state.demo_characters]
        gen.start(characters=chars)
        st.session_state.demo_gen = gen
        watcher = EVELogWatcher(
            tracker=tracker, log_dir=demo_dir, poll_interval=0.8,
            ess_retention=st.session_state.ess_retention, skip_existing=False,
        )
    else:
        watcher = EVELogWatcher(
            tracker=tracker,
            log_dir=log_dir or None,
            poll_interval=1.0,
            ess_retention=st.session_state.ess_retention,
            skip_existing=st.session_state.skip_existing,
            active_window_minutes=st.session_state.get('active_window_minutes', 30),
        )

    watcher.start()
    st.session_state.watcher = watcher
    st.session_state.initialized = True
    st.session_state.demo_mode = demo_mode

    if _OVERLAY_AVAILABLE:
        if st.session_state.overlay_server:
            st.session_state.overlay_server.stop()
        srv = OverlayServer()
        srv.start()
        st.session_state.overlay_server = srv

def reset_session():
    if st.session_state.tracker:
        st.session_state.tracker.reset_all()
    st.session_state.session_start = datetime.now()
    st.session_state.char_resolved = set()
    st.session_state.chart_session_token += 1

def ensure_chars_resolved(char_ids: list[str]):
    """Resuelve IDs en background mediante ESI."""
    from utils.eve_api import _failed_ids, RETRY_INTERVAL_SECS
    import time as _t
    pending = []
    for c in char_ids:
        if not is_character_id(c): continue
        cached = get_cached(c)
        if cached and cached.get('resolved'): continue
        with __import__('utils.eve_api', fromlist=['_cache_lock'])._cache_lock:
            failed_ts = _failed_ids.get(c, 0)
        if failed_ts and _t.time() - failed_ts < RETRY_INTERVAL_SECS: continue
        pending.append(c)
    if pending:
        resolve_characters_async(pending)

# ─── Helpers de UI ───────────────────────────────────────────────────────────

def render_gear_button():
    """Botón de configuración flotante."""
    import streamlit.components.v1 as components
    components.html("""
    <style>
      #gb{position:fixed;top:14px;left:14px;z-index:999999;width:38px;height:38px;
          background:rgba(3,8,20,0.97);border:1.5px solid rgba(0,180,255,0.55);
          border-radius:8px;display:flex;align-items:center;justify-content:center;
          cursor:pointer;font-size:18px;backdrop-filter:blur(12px);
          box-shadow:0 2px 18px rgba(0,0,0,0.6),0 0 8px rgba(0,180,255,0.15);
          transition:border-color 0.2s,box-shadow 0.2s;user-select:none;}
      #gb:hover{border-color:#00c8ff;box-shadow:0 2px 18px rgba(0,0,0,0.7),0 0 14px rgba(0,200,255,0.4);}
    </style>
    <div id="gb" title="Configuración" onclick="tgl()">⚙️</div>
    <script>
    function tgl(){
      var p=window.parent.document;
      var sels=['[data-testid="collapsedControl"] button', 'button[aria-label="Open sidebar"]', 'button[aria-label="Close sidebar"]'];
      for(var i=0;i<sels.length;i++){var b=p.querySelector(sels[i]);if(b){b.click();return;}}
      var btns=p.querySelectorAll('button');
      for(var j=0;j<btns.length;j++){
        var r=btns[j].getBoundingClientRect();
        if(r.left<80&&r.top<80&&r.width<60){btns[j].click();return;}
      }
    }
    </script>
    """, height=0, scrolling=False)

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    init_session_state()
    render_gear_button()
    
    # Renderizado Modular
    render_sidebar(
        start_tracker_func=start_tracker,
        reset_session_func=reset_session,
        overlay_available=_OVERLAY_AVAILABLE
    )
    
    render_dashboard_layout(
        tracker=st.session_state.tracker,
        lang=st.session_state.lang,
        render_welcome_func=render_welcome,
        ensure_chars_resolved_func=ensure_chars_resolved,
        render_charts_func=render_charts_iframe,
        send_chart_data_func=send_chart_data,
        render_chars_func=render_chars_section,
        start_tracker_func=start_tracker
    )

    # Bucle de actualización (Rerun)
    if st.session_state.initialized and st.session_state.tracker:
        if _OVERLAY_AVAILABLE and st.session_state.overlay_server:
            try:
                payload = build_overlay_payload(st.session_state.tracker)
                st.session_state.overlay_server.push(payload)
            except Exception: pass
        time.sleep(1.5)
        st.rerun()

if __name__ == "__main__":
    main()
