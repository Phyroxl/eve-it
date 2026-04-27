import streamlit as st
import os
import base64
from utils.i18n import LANGUAGE_OPTIONS

def get_flag_b64(lang: str):
    """Carga una bandera de assets y la devuelve en base64."""
    path = os.path.join("assets", f"flag_{lang}.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

def render_language_selector(lang: str):
    """
    Selector con st.radio() horizontal.
    Los emojis se renderizan via CSS font-family forzado.
    """
    options = LANGUAGE_OPTIONS
    cols = st.columns(len(options))
    for i, (code, label) in enumerate(options.items()):
        with cols[i]:
            b64 = get_flag_b64(code)
            border = "2px solid #00c8ff" if lang == code else "1px solid rgba(0,180,255,0.2)"
            opacity = "1.0" if lang == code else "0.5"
            st.markdown(f"""
                <div style="text-align:center; cursor:pointer;" onclick="document.querySelector('button[key=lang_{code}]').click()">
                    <img src="data:image/png;base64,{b64}" style="width:24px; height:16px; border-radius:2px; border:{border}; opacity:{opacity};">
                </div>
            """, unsafe_allow_html=True)
            if st.button(label.split()[-1], key=f"lang_{code}", use_container_width=True):
                if code != st.session_state.lang:
                    st.session_state.lang = code
                    st.query_params['lang'] = code
                    st.rerun()
