"""
app.py — EVE ISK Tracker dashboard (Streamlit).
Orquestador principal modularizado.
"""

import streamlit as st
from datetime import datetime, timedelta
import time
import tempfile

from core.session_tracker import MultiAccountTracker
from core.file_watcher import EVELogWatcher
from utils.demo_mode import DemoLogGenerator

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
from ui.dashboard.theme import render_theme, render_gear_button
from ui.dashboard.state import init_session_state
from ui.dashboard.sidebar import render_sidebar
from ui.dashboard.welcome import render_welcome
from ui.dashboard.dashboard_view import render_dashboard_layout
from ui.dashboard.components.charts import render_charts_iframe, send_chart_data
from ui.dashboard.components.characters import render_chars_section, ensure_chars_resolved

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
