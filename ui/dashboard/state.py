import streamlit as st
from utils.i18n import LANGUAGE_OPTIONS

def init_session_state():
    """Inicialización del estado de la sesión y valores por defecto."""
    defaults = {
        'tracker': None,
        'watcher': None,
        'demo_gen': None,
        'initialized': False,
        'demo_mode': False,
        'ess_retention': 1.0,
        'inactivity_threshold': 2.5,
        'log_dir': '',
        'skip_existing': False,
        'session_start': None,
        'last_save_path': None,
        'activity_type': 'ratting_null',
        'demo_characters': 1,
        'lang': 'es',
        'char_resolved': set(),
        # Token de versión para el iframe estático — cambia SOLO cuando inicia/resetea sesión
        'chart_session_token': 0,
        'chart_window_minutes': 0,  # 0 = toda la sesión
        'active_window_minutes': 30,  # ventana de actividad para logs
        'overlay_server': None,       # OverlayServer instance
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Leer idioma desde query_params (set por el selector)
    params = st.query_params
    if 'lang' in params and params['lang'] in LANGUAGE_OPTIONS:
        st.session_state.lang = params['lang']
