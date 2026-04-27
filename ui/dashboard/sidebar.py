import streamlit as st
from datetime import datetime
from utils.i18n import t
from ui.dashboard.language import render_language_selector

def _launch_overlay():
    """Lanza el overlay HUD como proceso independiente."""
    import subprocess
    import sys
    from pathlib import Path
    overlay_script = Path(__file__).parent.parent.parent / 'overlay' / 'overlay_app.py'
    if not overlay_script.exists():
        st.error("overlay_app.py no encontrado")
        return
    try:
        import socket as _sock
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(('127.0.0.1', 47290))
        s.send(b'FOCUS\n')
        s.close()
        return
    except Exception:
        pass
    try:
        subprocess.Popen(
            [sys.executable, str(overlay_script)],
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
    except Exception as e:
        st.error(f"Error lanzando overlay: {e}")

def _launch_replicator():
    """Lanza el window replicator."""
    import subprocess as _sp
    import sys as _sys
    import time as _time
    from pathlib import Path as _Path
    script = _Path(__file__).parent.parent.parent / 'overlay' / 'window_replicator.py'
    if not script.exists():
        st.error("No se encontro overlay/window_replicator.py")
        return
    try:
        proc = _sp.Popen(
            [_sys.executable, str(script)],
            stdout=_sp.PIPE, stderr=_sp.PIPE,
            creationflags=_sp.CREATE_NO_WINDOW if hasattr(_sp, 'CREATE_NO_WINDOW') else 0,
        )
        _time.sleep(1.2)
        if proc.poll() is not None:
            _, err = proc.communicate()
            msg = err.decode('utf-8', errors='ignore')[:400]
            st.error("El replicador cerro con error. Verifica: pip install PySide6 | " + msg)
        else:
            st.success("Replicador iniciado. Busca la ventana en pantalla.")
    except Exception as e:
        st.error("Error lanzando replicador: " + str(e))

def render_sidebar(start_tracker_func, reset_session_func, overlay_available=False):
    """Renderiza la barra lateral con controles y configuración."""
    lang = st.session_state.lang

    with st.sidebar:
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button(t('btn_start', lang), use_container_width=True, key="btn_s"):
                _dm = st.session_state.get('demo_mode', False)
                start_tracker_func(st.session_state.log_dir, demo_mode=_dm)
                st.rerun()
        with _c2:
            if st.button(t('btn_stop', lang), use_container_width=True, key="btn_x"):
                if st.session_state.watcher: st.session_state.watcher.stop()
                if st.session_state.demo_gen: st.session_state.demo_gen.stop()
                st.session_state.initialized = False
                st.rerun()
        if st.button(t('btn_reset', lang), use_container_width=True, key="btn_r"):
            reset_session_func()
            st.rerun()
        st.markdown("---")

        st.markdown(f"## {t('config_title', lang)}")
        st.markdown("---")

        st.markdown(f"### {t('language', lang)}")
        render_language_selector(lang)

        st.markdown("---")
        st.markdown(f"### {t('demo_mode', lang)}")
        demo_mode = st.toggle(t('demo_toggle', lang), value=False, key="demo_tog")

        if demo_mode:
            am = {
                'ratting_null': t('ratting_null', lang),
                'ratting_low':  t('ratting_low', lang),
                'mission_l4':   t('mission_l4', lang),
                'abyss':        t('abyss', lang),
            }
            sel = st.selectbox(t('demo_activity', lang), list(am.values()), key="demo_act")
            st.session_state.activity_type = next(k for k, v in am.items() if v == sel)
            st.session_state.demo_characters = st.slider(t('demo_chars', lang), 1, 3, 1, key="demo_ch")

        st.markdown("---")

        if not demo_mode:
            st.markdown(f"### {t('logs_title', lang)}")
            from core.log_parser import find_all_log_dirs, find_log_files
            dirs = find_all_log_dirs()
            if dirs["Chatlogs"]:
                st.success(t('logs_detected', lang))
                st.caption(f"📂 `{dirs['Chatlogs'][0]}`")
            else:
                st.warning(t('logs_not_found', lang))
                st.caption(t('logs_hint', lang))
            if dirs["Gamelogs"]:
                st.success(t('gamelogs_detected', lang))
                st.caption(f"📂 `{dirs['Gamelogs'][0]}`")
            nf = len(find_log_files())
            if nf > 0:
                st.caption(f"📄 {nf} {t('logs_total', lang)}")
            custom_dir = st.text_input(t('logs_manual', lang), placeholder=r"C:\...\Gamelogs", key="log_dir_in")
            st.session_state.log_dir = custom_dir
            st.session_state.skip_existing = st.toggle(
                t('new_events_only', lang), value=False, help=t('new_events_help', lang), key="skip_tog"
            )
            st.session_state.active_window_minutes = st.slider(
                "⏱ Ventana activa (min)",
                min_value=5, max_value=120, value=30, step=5,
                help="Ignorar logs no modificados en este tiempo.",
                key="active_window_sl"
            )

        st.markdown("---")
        st.markdown(f"### {t('ess_title', lang)}")
        ess_pct = st.slider(t('ess_label', lang), 0, 100, 100, step=1, key="ess_sl")
        new_ess = ess_pct / 100.0
        if new_ess != st.session_state.ess_retention:
            st.session_state.ess_retention = new_ess
            if st.session_state.watcher:
                st.session_state.watcher.update_ess_retention(new_ess)

        st.markdown(f"### {t('inactivity_title', lang)}")
        st.session_state.inactivity_threshold = st.slider(
            t('inactivity_label', lang), 1.0, 10.0, 2.5, step=0.5, key="inact_sl"
        )

        st.markdown("---")
        if overlay_available:
            st.markdown(f"### 🎮 Herramientas HUD")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🖥️ Abrir Overlay", use_container_width=True, key="btn_overlay"):
                    _launch_overlay()
                st.caption("Métricas flotantes")
            with col_b:
                if st.button("🪟 Replicar ventanas", use_container_width=True, key="btn_replicator"):
                    _launch_replicator()
                st.caption("Clonar zona de otras cuentas")
        else:
            st.caption("💡 Instala PySide6 para overlay y replicador: `pip install PySide6`")

        st.markdown("---")
        st.markdown(f"### {t('save_title', lang)}")
        if st.button(t('btn_save', lang), use_container_width=True, key="btn_sv"):
            if st.session_state.tracker:
                sp = f"isk_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                st.session_state.tracker.save_history(sp)
                st.session_state.last_save_path = sp
                st.success(f"{t('last_save', lang)}: {sp}")
        if st.session_state.last_save_path:
            st.caption(f"{t('last_save', lang)}: {st.session_state.last_save_path}")

        if st.session_state.watcher:
            status = st.session_state.watcher.get_status()
            st.markdown("---")
            st.markdown(f"### {t('monitor_title', lang)}")

            discovery_done = status.get('initial_discovery_done', False)
            current_chars = len(st.session_state.tracker.sessions) if st.session_state.tracker else 0

            if not discovery_done:
                st.markdown("""
                <div style="background:rgba(255,180,0,0.12);border:1px solid rgba(255,180,0,0.5);
                     border-left:4px solid #ffb400;border-radius:6px;padding:8px 12px;margin:4px 0">
                  <span style="color:#ffb400;font-family:Share Tech Mono,monospace;font-size:0.8rem">
                    ⏳ Detectando cuentas...
                  </span>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:rgba(0,255,157,0.08);border:1px solid rgba(0,255,157,0.4);
                     border-left:4px solid #00ff9d;border-radius:6px;padding:8px 12px;margin:4px 0">
                  <span style="color:#00ff9d;font-family:Share Tech Mono,monospace;font-size:0.8rem">
                    ✅ Sincronización completa — {current_chars} cuenta(s)
                  </span>
                </div>""", unsafe_allow_html=True)

            st.caption(f"{t('monitor_files', lang)}: **{status['files_monitored']}**")
            st.caption(f"{t('monitor_events', lang)}: **{status['total_events']}**")
            names = status.get('monitored_file_names', [])
            if names:
                with st.expander(f"{t('monitor_active', lang)} ({len(names)})"):
                    for n in names: st.caption(f"• {n}")
            elif status['running']:
                st.warning(t('monitor_no_files', lang))
                st.caption(t('monitor_no_files_hint', lang))
            if status['recent_errors']:
                with st.expander(t('monitor_errors', lang)):
                    for e in status['recent_errors']: st.caption(e)
