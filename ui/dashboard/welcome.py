import streamlit as st
from utils.i18n import t

def render_welcome(lang: str, start_tracker_func):
    """Pantalla de bienvenida del Dashboard."""
    st.markdown(f"""
    <div style="text-align:center;padding:40px 20px 20px 20px">
      <h1 style="font-size:2.5rem;margin-bottom:8px">⚡ EVE ISK TRACKER</h1>
      <p style="color:rgba(0,200,255,0.6);font-family:'Share Tech Mono',monospace;font-size:1rem">
        {t('welcome_subtitle', lang)}
      </p>
    </div>""", unsafe_allow_html=True)
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"""
        <div style="background:rgba(0,20,50,0.8);border:1px solid rgba(0,180,255,0.3);
                    border-radius:12px;padding:28px 32px 20px 32px">
          <h3 style="text-align:center;margin-bottom:16px">{t('quick_start', lang)}</h3>
          <p>{t('qs_1', lang)}</p><p>{t('qs_2', lang)}</p>
          <p>{t('qs_3', lang)}</p>
          <br>
          <p style="color:rgba(200,220,255,0.5);font-size:0.8rem">
            {t('qs_path', lang)}<br>
            <code style="color:#00c8ff">Documentos/EVE/logs/Gamelogs/</code>
          </p>
        </div>""", unsafe_allow_html=True)
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        # Botón INICIAR funcional directamente en el panel de bienvenida
        if st.button(
            f"▶ {t('btn_start', lang)}",
            use_container_width=True,
            key="btn_welcome_start",
            type="primary",
        ):
            start_tracker_func(st.session_state.get('log_dir', ''), demo_mode=False)
            st.rerun()
