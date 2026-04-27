import streamlit as st
from datetime import datetime
from utils.i18n import t
from utils.formatters import format_isk, format_duration

def render_dashboard_layout(tracker, lang, render_welcome_func, ensure_chars_resolved_func, 
                           render_charts_func, send_chart_data_func, render_chars_func,
                           start_tracker_func):
    """Render principal del Dashboard."""
    if tracker is None:
        render_welcome_func(lang, start_tracker_func)
        return

    now = datetime.now()
    summary = tracker.get_summary(now)

    # Resolución asíncrona de personajes
    char_ids = [cd['character'] for cd in summary['per_character']]
    ensure_chars_resolved_func(char_ids)

    # ── Indicador de sincronización (banner temporal) ──
    watcher = st.session_state.watcher
    if watcher:
        wstatus = watcher.get_status()
        discovery_done = wstatus.get('initial_discovery_done', True)
        if not discovery_done:
            st.markdown("""
            <div style="background:rgba(255,180,0,0.1);border:1px solid rgba(255,180,0,0.45);
                 border-radius:8px;padding:10px 18px;margin-bottom:12px;
                 font-family:Share Tech Mono,monospace">
              <span style="color:#ffb400">⏳</span>
              <span style="color:rgba(255,200,100,0.9);font-size:0.85rem;margin-left:8px">
                Detectando cuentas activas — las métricas se sincronizarán al completar...
              </span>
            </div>""", unsafe_allow_html=True)

    # ── Header ──
    mode_badge = "🎮 DEMO" if st.session_state.demo_mode else "🛸 LIVE"
    st.markdown(
        f"<h1 style='margin-bottom:0'>⚡ EVE ISK TRACKER &nbsp;"
        f"<span style='font-size:0.6rem;color:#00ff9d;border:1px solid #00ff9d;"
        f"padding:3px 8px;border-radius:3px'>{mode_badge}</span></h1>",
        unsafe_allow_html=True
    )
    st.caption(f"{t('session_started', lang)}: "
               f"{st.session_state.session_start.strftime('%H:%M:%S') if st.session_state.session_start else 'N/A'}")
    st.markdown("---")

    # ── Métricas ──
    total_isk     = summary['total_isk']
    isk_h_rolling = summary['isk_per_hour_rolling']
    isk_h_session = summary['isk_per_hour_total']
    isk_m         = summary['isk_per_minute']
    duration      = summary['session_duration']
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric(t('metric_isk_total', lang), format_isk(total_isk, short=True),
                  delta=f"+{format_isk(total_isk, short=True)}" if total_isk > 0 else None)
    with m2:
        st.metric(t('metric_isk_h_rolling', lang), format_isk(isk_h_rolling, short=True))
    with m3:
        st.metric(t('metric_isk_h_session', lang), format_isk(isk_h_session, short=True))
    with m4:
        st.metric(t('metric_isk_min', lang), format_isk(isk_m, short=True))
    with m5:
        st.metric(t('metric_session', lang), format_duration(duration),
                  delta=f"{summary['character_count']} {t('personajes', lang)}")

    st.markdown("---")

    # ── Gráficos ──
    _win_opts = {'5 min': 5, '20 min': 20, '1 h': 60, '24 h': 1440, 'Todo': 0}
    _cur_win = st.session_state.get('chart_window_minutes', 0)
    _cur_idx = next((i for i, v in enumerate(_win_opts.values()) if v == _cur_win), len(_win_opts)-1)
    _sel = st.radio("📊 Vista", list(_win_opts.keys()), index=_cur_idx, horizontal=True, key="chart_win_r", label_visibility="collapsed")
    st.session_state.chart_window_minutes = _win_opts[_sel]
    token = st.session_state.chart_session_token
    render_charts_func(token)
    send_chart_data_func(tracker, lang)

    # ── Por personaje ──
    if summary['per_character']:
        st.markdown(f"### {t('by_character', lang)}")
        render_chars_func(summary['per_character'], lang)
    elif st.session_state.initialized:
        _render_key = f"_search_msg_{st.session_state.chart_session_token}"
        if not st.session_state.get(_render_key, False):
            st.session_state[_render_key] = True
            st.info("🔍 Buscando personajes activos en los logs de EVE...")
        else:
            st.session_state[_render_key] = False
