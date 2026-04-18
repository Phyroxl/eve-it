"""
app.py — EVE ISK Tracker dashboard (Streamlit).

ARQUITECTURA ANTI-REGRESIÓN:

El problema raíz de todos los bugs anteriores era mezclar datos variables con
estructura HTML estática en components.html(). Cada vez que cambian los datos,
el hash del componente cambia → Streamlit destruye y recrea el iframe → parpadeo.

SOLUCIÓN ARQUITECTURAL:
  1. El iframe de gráficos es ESTÁTICO (su HTML nunca cambia).
     Los datos llegan via postMessage desde Python→JS en cada ciclo.
     Plotly.react() actualiza trazas in-place sin destruir canvas.

  2. Las cards de personaje se renderizan en un iframe separado estático
     que recibe datos via postMessage. Cero HTML escaping issues.

  3. El selector de idioma usa st.radio() nativo con CSS que fuerza
     font-family emoji en las opciones — solución probada que no depende
     de iframe communication (que Streamlit bloquea via CSP).

  4. postMessage funciona porque Streamlit permite comunicación
     iframe→parent via window.addEventListener('message').
     Un componente receptor minimalista escucha y actualiza query_params.
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
from datetime import datetime, timedelta
import time
import tempfile
import base64
import os

from core.session_tracker import MultiAccountTracker
from core.file_watcher import EVELogWatcher
from utils.formatters import format_isk, format_duration, format_inactivity
from utils.demo_mode import DemoLogGenerator
from utils.i18n import t, LANGUAGE_OPTIONS
from utils.eve_api import resolve_characters_async, get_cached, is_character_id, resolve_character_name_only

# Overlay HUD (importación lazy — no falla si PyQt no está instalado)
try:
    from overlay.overlay_server import OverlayServer, build_overlay_payload
    _OVERLAY_AVAILABLE = True
except ImportError:
    _OVERLAY_AVAILABLE = False

# ─── Config ────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="EVE ISK Tracker",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS global — solo estilos de Streamlit nativo, nunca de iframes
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;900&family=Share+Tech+Mono&display=swap');

  .stApp {
    background: #030810;
    background-image:
      radial-gradient(ellipse at 20% 50%, rgba(0,180,255,0.04) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 20%, rgba(0,255,157,0.03) 0%, transparent 50%);
  }
  [data-testid="stSidebar"] {
    background: #060e1a !important;
    border-right: 1px solid rgba(0,180,255,0.2);
  }
  [data-testid="stMetric"] {
    background: rgba(0,20,40,0.8);
    border: 1px solid rgba(0,180,255,0.25);
    border-radius: 8px;
    padding: 16px 20px;
  }
  [data-testid="stMetricValue"] {
    font-family: 'Orbitron', monospace !important;
    font-size: 1.4rem !important;
    color: #00c8ff !important;
    font-weight: 600 !important;
  }
  [data-testid="stMetricLabel"] {
    font-family: 'Share Tech Mono', monospace !important;
    color: rgba(0,200,255,0.6) !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  [data-testid="stMetricDelta"] {
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 0.8rem !important;
  }
  h1, h2, h3 {
    font-family: 'Orbitron', monospace !important;
    color: #00c8ff !important;
    letter-spacing: 2px;
  }
  h1 { text-shadow: 0 0 20px rgba(0,200,255,0.5); }
  p, label, .stMarkdown {
    font-family: 'Share Tech Mono', monospace;
    color: rgba(200,230,255,0.85);
  }
  .stButton > button {
    background: rgba(0,180,255,0.1) !important;
    border: 1px solid rgba(0,180,255,0.4) !important;
    color: #00c8ff !important;
    font-family: 'Orbitron', monospace !important;
    font-size: 0.75rem !important;
    letter-spacing: 1px;
    border-radius: 4px;
    transition: all 0.2s;
  }
  .stButton > button:hover {
    background: rgba(0,180,255,0.25) !important;
    border-color: #00c8ff !important;
    box-shadow: 0 0 15px rgba(0,200,255,0.3);
  }
  /* Forzar emojis en radio buttons de idioma */
  div[data-testid="stRadio"] label span {
    font-family: "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji","Twemoji Mozilla",sans-serif !important;
    font-size: 1.05rem !important;
  }
  div[data-testid="stRadio"] > div {
    gap: 6px !important;
  }
  hr { border-color: rgba(0,180,255,0.15) !important; }
  footer { visibility: hidden; }
  #MainMenu { visibility: hidden; }
  /* Ocultar toolbar nativa de Streamlit (botones Stop/Deploy) */
  [data-testid="stToolbar"] { display: none !important; }
  header[data-testid="stHeader"] { display: none !important; }
  /* Toggle del sidebar — siempre visible en todas las versiones de Streamlit */
  /* Versiones recientes usan collapsedControl */
  [data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    position: fixed !important;
    top: 10px !important;
    left: 10px !important;
    z-index: 99999 !important;
    background: rgba(3,8,16,0.97) !important;
    border: 1px solid rgba(0,180,255,0.5) !important;
    border-radius: 7px !important;
    padding: 3px 5px !important;
    backdrop-filter: blur(12px) !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.7), 0 0 8px rgba(0,180,255,0.15) !important;
  }
  [data-testid="collapsedControl"]:hover {
    border-color: #00c8ff !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.7), 0 0 14px rgba(0,200,255,0.4) !important;
  }
  [data-testid="collapsedControl"] button,
  [data-testid="collapsedControl"] svg {
    display: flex !important;
    visibility: visible !important;
    color: #00c8ff !important;
    opacity: 1 !important;
  }
</style>
""", unsafe_allow_html=True)


# ─── Estado ────────────────────────────────────────────────────────────────────

def init_session_state():
    defaults = {
        'tracker': None,
        'watcher': None,
        'demo_gen': None,
        'initialized': False,
        'demo_mode': False,
        'ess_retention': 1.0,
        'inactivity_threshold': 2.5,
        'log_dir': '',
        'skip_existing': True,
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


def _launch_overlay():
    """
    Lanza el overlay HUD como proceso independiente.
    Si ya está activo, le envía señal de focus (singleton socket).
    No bloquea la UI de Streamlit.
    """
    import subprocess
    import sys
    from pathlib import Path

    overlay_script = Path(__file__).parent / 'overlay' / 'overlay_app.py'
    if not overlay_script.exists():
        st.error("overlay_app.py no encontrado")
        return

    # Intentar señalizar instancia existente primero
    try:
        import socket as _sock
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(('127.0.0.1', 47290))
        s.send(b'FOCUS\n')
        s.close()
        return   # ya había instancia, foco enviado
    except Exception:
        pass    # no hay instancia → lanzar nueva

    try:
        subprocess.Popen(
            [sys.executable, str(overlay_script)],
            creationflags=subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
    except Exception as e:
        st.error(f"Error lanzando overlay: {e}")


def _launch_replicator():
    """Lanza el window replicator con diagnostico de errores visible."""
    import subprocess as _sp
    import sys as _sys
    import time as _time
    from pathlib import Path as _Path

    script = _Path(__file__).parent / 'overlay' / 'window_replicator.py'
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
    # Nuevo token → los iframes estáticos se recrean una sola vez al iniciar sesión
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

    # Iniciar servidor overlay si disponible
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
    """
    Resuelve IDs en background. No bloquea la UI.
    NO marca como resuelto hasta que ESI confirme — permite reintentos
    automáticos cada RETRY_INTERVAL_SECS si la primera llamada falló.
    """
    from utils.eve_api import _failed_ids, RETRY_INTERVAL_SECS
    import time as _t
    pending = []
    for c in char_ids:
        if not is_character_id(c):
            continue
        cached = get_cached(c)
        if cached and cached.get('resolved'):
            continue  # ya resuelto con éxito
        # Comprobar si está en fallidos y si es tiempo de reintentar
        import threading as _th
        with __import__('utils.eve_api', fromlist=['_cache_lock'])._cache_lock:
            failed_ts = _failed_ids.get(c, 0)
        if failed_ts and _t.time() - failed_ts < RETRY_INTERVAL_SECS:
            continue  # esperar al retry window
        pending.append(c)
    if pending:
        resolve_characters_async(pending)


# ─── Selector de idioma ────────────────────────────────────────────────────────

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
    Los emojis se renderizan via CSS font-family forzado (definido en el CSS global).
    Es la única solución 100% compatible con Streamlit sin depender de iframes.
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


# ─── Gráficos: iframe estático + postMessage ──────────────────────────────────

# HTML del iframe de gráficos — se genera UNA sola vez por sesión.
# Los datos llegan via postMessage en cada ciclo de actualización.
_CHARTS_IFRAME_HTML = """
<html><head>
<meta charset="UTF-8">
<script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:transparent; overflow:hidden; }
  #c1 { width:100%; height:310px; }
  #c2 { width:100%; height:215px; margin-top:6px; }
</style>
</head><body>
<div id="c1"></div>
<div id="c2"></div>
<script>
const CFG = { displayModeBar: false, responsive: true };

const L1 = {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,5,15,0.88)',
  font:{ family:'Share Tech Mono,monospace', color:'#00c8ff', size:10 },
  margin:{ l:50, r:14, t:34, b:38 },
  xaxis:{ gridcolor:'rgba(0,100,180,0.12)', tickfont:{ size:9, color:'rgba(0,200,255,0.45)' } },
  yaxis:{ gridcolor:'rgba(0,100,180,0.12)', tickfont:{ size:9, color:'rgba(0,200,255,0.45)' }, tickformat:'.3s' },
  hovermode:'x unified',
  legend:{ font:{ size:9 }, bgcolor:'rgba(0,0,0,0)' },
  uirevision: 'c1'
};
const L2 = {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,5,15,0.88)',
  font:{ family:'Share Tech Mono,monospace', color:'#00ff9d', size:9 },
  margin:{ l:50, r:14, t:28, b:38 },
  xaxis:{ gridcolor:'rgba(0,120,60,0.12)', tickfont:{ size:8, color:'rgba(0,255,157,0.4)' } },
  yaxis:{ gridcolor:'rgba(0,120,60,0.12)', tickfont:{ size:8, color:'rgba(0,255,157,0.4)' }, tickformat:'.2s' },
  showlegend: false,
  uirevision: 'c2'
};

let init1 = false, init2 = false;

function updateCharts(d) {
  const t1 = [
    { type:'scatter', mode:'lines', x:d.xm, y:d.ym,
      fill:'tozeroy', fillcolor:'rgba(0,180,255,0.07)',
      line:{ color:'#00c8ff', width:2, shape:'spline', smoothing:0.5 }, name:'ISK Total',
      hovertemplate:'<b>%{y:,.0f} ISK</b><extra></extra>' },
    { type:'scatter', mode:'markers', x:d.xm, y:d.ym,
      marker:{ color:d.ye, colorscale:[['0','#003060'],['0.5','#0080ff'],['1','#00ff9d']], size:5, opacity:0.7 },
      name:'Evento', customdata:d.ye,
      hovertemplate:'<b>+%{customdata:,.0f} ISK</b><extra></extra>' }
  ];
  const lay1 = Object.assign({}, L1, {
    title:{ text:d.ct, font:{ family:'Orbitron,monospace', size:11, color:'rgba(0,200,255,0.5)' }, x:0.5 }
  });
  init1 ? Plotly.react('c1', t1, lay1, CFG) : (Plotly.newPlot('c1', t1, lay1, CFG), init1=true);


  const t2 = [
    { type:'scatter', mode:'lines', x:d.xr, y:d.yr,
      fill:'tozeroy', fillcolor:'rgba(0,255,157,0.06)',
      line:{ color:'#00ff9d', width:1.5, shape:'spline', smoothing:0.7 },
      hovertemplate:'<b>%{y:,.0f} ISK/h</b><extra></extra>' },

  ];
  const lay2 = Object.assign({}, L2, {
    title:{ text:d.rt, font:{ family:'Orbitron,monospace', size:10, color:'rgba(0,255,157,0.5)' }, x:0.5 }
  });
  init2 ? Plotly.react('c2', t2, lay2, CFG) : (Plotly.newPlot('c2', t2, lay2, CFG), init2=true);
}

window.addEventListener('message', function(e) {
  if (e.data && e.data.type === 'chartData') updateCharts(e.data.payload);
});
</script>
</body></html>
"""

def render_charts_iframe(token: int):
    """
    Sin key (compatibilidad Streamlit < 1.36).
    El HTML es una constante → Streamlit reutiliza el mismo nodo DOM → sin parpadeo.
    """
    components.html(_CHARTS_IFRAME_HTML, height=545, scrolling=False)


def send_chart_data(tracker: MultiAccountTracker, lang: str):
    """
    Envía datos actualizados al iframe via postMessage.
    Este componente es minimalista (solo JS), cambia en cada ciclo pero
    es invisible → no produce parpadeo visual.
    """
    history = tracker.get_isk_history_for_chart()
    # Filtrar por ventana temporal si está configurada (0 = toda la sesión)
    window_minutes = st.session_state.get('chart_window_minutes', 0)
    if window_minutes > 0 and history:
        cutoff_ts = datetime.now() - timedelta(minutes=window_minutes)
        history = [h for h in history if h['timestamp'] >= cutoff_ts]

    if len(history) >= 2:
        df = pd.DataFrame(history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        xm = df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist()
        ym = df['total_isk'].tolist()
        ye = df['event_isk'].tolist()
    else:
        xm, ym, ye = [], [], []

    if len(history) >= 3:
        recent = history[-120:]
        dfr = pd.DataFrame(recent)
        dfr['timestamp'] = pd.to_datetime(dfr['timestamp'])
        dfr = dfr.sort_values('timestamp').reset_index(drop=True)
        rolling = []
        for _, row in dfr.iterrows():
            cutoff = row['timestamp'] - timedelta(minutes=5)
            window = dfr[dfr['timestamp'] >= cutoff]
            w_isk = window['event_isk'].sum()
            w_secs = max((row['timestamp'] - window['timestamp'].min()).total_seconds(), 60.0)
            rolling.append((row['timestamp'].strftime('%Y-%m-%dT%H:%M:%S'), round((w_isk / w_secs) * 3600)))
        xr = [r[0] for r in rolling]
        yr = [r[1] for r in rolling]
    else:
        xr, yr = [], []

    payload = {
        'xm': xm, 'ym': ym, 'ye': ye,
        'xr': xr, 'yr': yr,
        'ct': t('chart_title', lang),
        'rt': t('chart_rolling_title', lang),
    }

    msg_js = f"""
    <script>
    (function() {{
      // Buscar el iframe de gráficos por su contenido y enviarle los datos
      const frames = window.parent.document.querySelectorAll('iframe');
      const payload = {json.dumps(payload)};
      frames.forEach(function(f) {{
        try {{
          f.contentWindow.postMessage({{ type: 'chartData', payload: payload }}, '*');
        }} catch(e) {{}}
      }});
    }})();
    </script>
    """
    # Componente invisible (height=0) que ejecuta el JS de postMessage
    components.html(msg_js, height=0, scrolling=False)


# ─── Cards de personaje ──────────────────────────────────────────────────────
#
# Arquitectura anti-parpadeo (mismo patrón que los gráficos):
#   _CHARS_STATIC_HTML  → iframe con estructura HTML fija, sin datos embebidos.
#                         Streamlit reutiliza el mismo nodo DOM entre reruns
#                         porque el HTML nunca cambia.
#   send_chars_data()   → componente height=0 invisible que envía los datos
#                         cambiantes via postMessage.
#   JS en el iframe     → actualiza solo los nodos de texto específicos
#                         (sin reconstruir el DOM), eliminando el parpadeo.

_CHARS_STATIC_HTML = """
<html><head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:transparent;font-family:'Share Tech Mono',monospace;padding:4px 2px;overflow:hidden}
  .card{background:rgba(0,20,45,.75);border:1px solid rgba(0,180,255,.22);border-radius:8px;padding:12px 16px;margin-bottom:8px;transition:border-color .2s,opacity .3s}
  .card:hover{border-color:rgba(0,180,255,.5)}
  .card.idle{border-color:rgba(255,200,0,.25);opacity:.85}
  .card.inactive{border-color:rgba(255,60,60,.25);opacity:.7}
  .ch{display:flex;align-items:center;gap:12px;margin-bottom:10px}
  .avl{flex-shrink:0;display:block;position:relative}
  .av{width:52px;height:52px;border-radius:7px;border:1px solid rgba(0,180,255,.35);object-fit:cover;display:block;transition:border-color .2s}
  .av:hover{border-color:#00c8ff}
  .avp{width:52px;height:52px;border-radius:7px;border:1px solid rgba(0,180,255,.3);background:rgba(0,30,60,.9);display:flex;align-items:center;justify-content:center;font-size:1.5rem}
  /* Semáforo: punto en esquina del avatar */
  .dot{position:absolute;bottom:2px;right:2px;width:10px;height:10px;border-radius:50%;border:1.5px solid rgba(0,0,0,.6);transition:background .4s}
  .dot.active{background:#00ff9d;box-shadow:0 0 6px #00ff9d}
  .dot.idle{background:#ffd700;box-shadow:0 0 5px #ffd700}
  .dot.inactive{background:#ff4444;box-shadow:0 0 5px #ff4444}
  .ci{display:flex;flex-direction:column;gap:3px}
  .cn{font-family:'Orbitron',monospace;color:#00c8ff;font-size:.82rem;font-weight:600;text-decoration:none;transition:color .15s}
  .cn:hover{color:#00ff9d}
  .badge{display:inline-block;font-size:.62rem;padding:1px 6px;border-radius:3px;margin-left:6px;vertical-align:middle;font-family:'Share Tech Mono',monospace}
  .badge.active{background:rgba(0,255,157,.12);color:#00ff9d;border:1px solid rgba(0,255,157,.3)}
  .badge.idle{background:rgba(255,215,0,.12);color:#ffd700;border:1px solid rgba(255,215,0,.3)}
  .badge.inactive{background:rgba(255,60,60,.12);color:#ff8888;border:1px solid rgba(255,60,60,.3)}
  .li{color:rgba(200,230,255,.4);font-size:.7rem}
  .st{display:flex;gap:20px;flex-wrap:wrap}
  .s{display:flex;flex-direction:column;gap:2px}
  .sl{color:rgba(200,230,255,.45);font-size:.7rem}
  .sv{font-size:.88rem;font-weight:bold}
  .gold{color:#ffd700}.grn{color:#00ff9d}.blu{color:#88ccff}
  .dim{color:rgba(200,230,255,.3)}
  /* Countdown del siguiente tick */
  .countdown{font-family:'Orbitron',monospace;font-size:1.1rem;font-weight:700;
              letter-spacing:2px;color:#ffd700;text-shadow:0 0 8px rgba(255,215,0,0.5)}
  .countdown.soon{color:#ff4444;text-shadow:0 0 8px rgba(255,80,80,0.6);animation:pulse 1s infinite}
  .tick-row{display:flex;align-items:center;gap:12px;margin-top:8px;padding-top:8px;
            border-top:1px solid rgba(0,180,255,0.1)}
  .tick-label{color:rgba(200,230,255,.45);font-size:.7rem}
  .tick-interval{color:rgba(200,230,255,.3);font-size:.65rem;margin-left:4px}
  .wallet-row{display:flex;align-items:center;gap:8px;margin-top:4px}
  .wallet-val{color:#00ff9d;font-size:.82rem;font-weight:bold}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
</style>
</head><body>
<div id="root"></div>
<script>
var _nodes = {};
var _initialized = false;

var STATUS_LABEL = { active: 'ACTIVO', idle: 'DETECTADO', inactive: 'INACTIVO' };

function _makeCard(c) {
  var zkill = 'https://zkillboard.com/character/' + c.id + '/';
  var portrait = 'https://images.evetech.net/characters/' + c.id + '/portrait?size=64';
  var card = document.createElement('div');
  card.className = 'card';
  card.id = 'card_' + c.id;

  var avHtml = c.isNum
    ? '<a href="' + zkill + '" target="_blank" class="avl"><img src="' + portrait + '" class="av" id="img_' + c.id + '" /><div class="dot" id="dot_' + c.id + '"></div></a>'
    : '<a href="' + zkill + '" target="_blank" class="avl"><div class="avp">&#x1F464;</div><div class="dot" id="dot_' + c.id + '"></div></a>';

  card.innerHTML = [
    '<div class="ch">',
      avHtml,
      '<div class="ci">',
        '<div style="display:flex;align-items:center;gap:4px">',
          '<a href="' + zkill + '" target="_blank" class="cn">' + c.name + '</a>',
          '<span class="badge" id="badge_' + c.id + '"></span>',
        '</div>',
        '<div class="li" id="li_' + c.id + '"></div>',
      '</div>',
    '</div>',
    '<div class="st">',
      '<div class="s"><div class="sl" id="lbl_total_' + c.id + '"></div><div class="sv gold" id="val_total_' + c.id + '"></div></div>',
      '<div class="s"><div class="sl" id="lbl_roll_' + c.id + '"></div><div class="sv grn" id="val_roll_' + c.id + '"></div></div>',
      '<div class="s"><div class="sl" id="lbl_sess_' + c.id + '"></div><div class="sv blu" id="val_sess_' + c.id + '"></div></div>',
      '<div class="s"><div class="sl">ISK/min</div><div class="sv blu" id="val_min_' + c.id + '"></div></div>',
      '<div class="s"><div class="sl" id="lbl_ev_' + c.id + '"></div><div class="sv" id="val_ev_' + c.id + '"></div></div>',
      '<div class="s"><div class="sl" id="lbl_tk_' + c.id + '"></div><div class="sv" style="color:#ffa040" id="val_tk_' + c.id + '"></div></div>',
    '</div>',
    '<div class="tick-row">',
      '<div class="tick-label">⏱ Próximo tick</div>',
      '<div class="countdown" id="cd_' + c.id + '">--:--</div>',
      '<div class="tick-interval" id="cd_int_' + c.id + '"></div>',
    '</div>',
    '<div class="wallet-row">',
      '<div class="tick-label">💰 ISK acumulado</div>',
      '<div class="wallet-val" id="wal_' + c.id + '">—</div>',
    '</div>',
  ].join('');

  var img = card.querySelector('#img_' + c.id);
  if (img) {
    img.addEventListener('error', function() {
      var ph = document.createElement('div');
      ph.className = 'avp';
      ph.innerHTML = '&#x1F464;';
      var dot = img.nextSibling;
      img.parentNode.replaceChild(ph, img);
      ph.parentNode.appendChild(dot);
    });
  }
  return card;
}

function _updateCard(c) {
  var set = function(id, txt) { var el = document.getElementById(id); if (el) el.textContent = txt; };
  var cls = function(id, cn) { var el = document.getElementById(id); if (el) { el.className = el.className.replace(/ (active|idle|inactive)/g, ''); el.className += ' ' + cn; } };
  var evClass = c.hasEvents ? (c.status === 'active' ? 'sv grn' : 'sv dim') : 'sv dim';

  // Semáforo
  cls('dot_' + c.id, c.status);
  // Badge
  var badge = document.getElementById('badge_' + c.id);
  if (badge) {
    badge.textContent = STATUS_LABEL[c.status] || c.status;
    badge.className = 'badge ' + c.status;
  }
  // Card border class
  var card = document.getElementById('card_' + c.id);
  if (card) {
    card.className = 'card';
    if (c.status !== 'active') card.className += ' ' + c.status;
  }

  var liTxt = c.hasEvents
    ? (c.lblLast + ': ' + c.lastEvent + (c.secsSinceEvent >= 0 ? ' (hace ' + c.secsSinceEvent + 's)' : ''))
    : c.lblNoEvents;
  set('li_' + c.id, liTxt);
  set('lbl_total_' + c.id,  c.lblTotal);
  set('val_total_' + c.id,  c.iskTotal);
  set('lbl_roll_' + c.id,   c.lblRoll);
  set('val_roll_' + c.id,   c.iskRoll + '/h');
  set('lbl_sess_' + c.id,   c.lblSess);
  set('val_sess_' + c.id,   c.iskSess + '/h');
  set('val_min_' + c.id,    c.iskMin + '/min');
  set('lbl_ev_' + c.id,     c.lblEv);
  set('lbl_tk_' + c.id,     c.lblTicket || '🎫 Ticket 20m');
  set('val_tk_' + c.id,     c.ticket20m || '—');
  set('wal_' + c.id,        c.sessionIsk || '—');

  // Countdown: usar secsUntilNext (calculado en Python, timezone-correcto)
  // NO usar nextTickEpoch — los logs de EVE son UTC pero Python los parsea
  // como naive, causando desfase con Date.now() del browser.
  var sus = parseInt(c.secsUntilNext);
  var tis = parseInt(c.tickIntervalSecs);
  if (!isNaN(sus) && sus > 0 && !isNaN(tis) && tis > 0) {
    var targetMs = Date.now() + sus * 1000;
    _tickTargets[c.id] = { target: targetMs, intervalMs: tis * 1000 };
    var intMins = Math.round(tis / 60);
    var intLabel = c.isEstimated ? '(~' + intMins + 'min est.)' : '(cada ' + intMins + 'min)';
    set('cd_int_' + c.id, intLabel);
  } else {
    set('cd_' + c.id, '--:--');
    set('cd_int_' + c.id, '');
    delete _tickTargets[c.id];
  }

  var evEl = document.getElementById('val_ev_' + c.id);
  if (evEl) { evEl.textContent = c.events; evEl.className = evClass; }
}

// Mapa char_id → { target: epochMs, intervalMs: number }
// target se establece como Date.now() + secsUntilNext*1000 (timezone-safe)
var _tickTargets = {};

// Timer local — actualiza el countdown cada segundo sin Python
setInterval(function() {
  var now = Date.now();
  Object.keys(_tickTargets).forEach(function(cid) {
    var td = _tickTargets[cid];
    if (!td || typeof td !== 'object') { delete _tickTargets[cid]; return; }
    var targetMs  = Number(td.target);
    var intervalMs = Number(td.intervalMs);
    // Protección anti-NaN
    if (isNaN(targetMs) || isNaN(intervalMs) || intervalMs <= 0) {
      delete _tickTargets[cid];
      var el = document.getElementById('cd_' + cid);
      if (el) el.textContent = '--:--';
      return;
    }
    var remaining = Math.max(0, Math.floor((targetMs - now) / 1000));
    var mins = Math.floor(remaining / 60);
    var secs = remaining % 60;
    var str = (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs;
    var el = document.getElementById('cd_' + cid);
    if (el) {
      el.textContent = str;
      el.className = remaining <= 60 ? 'countdown soon' : 'countdown';
    }
    // Auto-avanzar cuando expira: añadir un intervalo completo
    if (now >= targetMs) {
      td.target = targetMs + intervalMs;
      _tickTargets[cid] = td;
    }
  });
}, 1000);

function handleCharData(chars) {
  var root = document.getElementById('root');
  var incomingIds = chars.map(function(c) { return c.id; });
  chars.forEach(function(c) {
    if (!_nodes[c.id]) {
      var card = _makeCard(c);
      root.appendChild(card);
      _nodes[c.id] = card;
    }
    _updateCard(c);
  });
  Object.keys(_nodes).forEach(function(id) {
    _nodes[id].style.display = incomingIds.indexOf(id) >= 0 ? '' : 'none';
  });
}

window.addEventListener('message', function(e) {
  if (e.data && e.data.type === 'charUpdate') handleCharData(e.data.chars);
});
</script>
</body></html>
"""


def _secs_since_event(cd: dict) -> int:
    """Segundos desde el último evento (wall clock). -1 si no hay eventos."""
    if not cd.get('has_events'):
        return -1
    last = cd.get('last_processed_at')
    if last is None:
        return -1
    return max(0, int((datetime.now() - last).total_seconds()))


def send_chars_data(chars_data: list[dict], lang: str):
    """
    Envía datos de personajes al iframe estático via postMessage.
    Incluye estado semáforo (active/idle/inactive) y flag has_events.
    """
    chars_payload = []
    # chars_data ya viene ordenado por get_summary (activos primero)
    for cd in chars_data:
        cid       = cd['character']
        esi       = get_cached(cid)
        # Si no hay cache, intentar resolver (no bloquea — resolve_characters_async
        # ya está corriendo en background; esto solo lee el resultado)
        if esi is None and is_character_id(cid):
            esi = get_cached(cid)  # intentar leer de nuevo
        # Prioridad: ESI API → nombre del log (Listener:) → ID como fallback
        if esi and esi.get('resolved') and esi.get('name'):
            name = esi['name']
        elif cd['display_name'] and cd['display_name'] != cid:
            name = cd['display_name']
        else:
            name = cid
        has_events = cd.get('has_events', cd['event_count'] > 0)
        status    = cd.get('status', 'idle')
        chars_payload.append({
            'id':         cid,
            'name':       name,
            'isNum':      is_character_id(cid),
            'status':     status,
            'hasEvents':  has_events,
            'iskTotal':   format_isk(cd['total_isk'], short=True),
            'iskRoll':    format_isk(cd['isk_per_hour'], short=True),
            'iskSess':    format_isk(cd['isk_per_hour_session'], short=True),
            'iskMin':     format_isk(cd['isk_per_minute'], short=True),
            'events':     f"{cd['event_count']:,}",
            'lastEvent':  cd['last_event'].strftime('%H:%M:%S') if cd['last_event'] else '—',
            'lblLast':    t('last_income', lang),
            'lblNoEvents': 'Esperando primer bounty...' if lang == 'es' else 'Waiting for first bounty...',
            'lblTotal':   t('isk_total', lang),
            'lblRoll':    f"{t('isk_h', lang)} rolling",
            'lblSess':    f"{t('isk_h', lang)} sesion",
            'lblEv':      t('events', lang),
            'ticket20m':  format_isk(cd['isk_per_hour'] / 3, short=True),
            'lblTicket':  '🎫 Ticket 20m',
            # Countdown del próximo tick ESS
            'tickCount':    cd['tick_info']['tick_count'],
            'nextTickEpoch':    0,  # no usado — ver secsUntilNext
            'secsUntilNext':    cd['tick_info']['secs_until_next']
                                if cd['tick_info']['secs_until_next'] >= 0 else 0,
            'tickIntervalSecs': cd['tick_info']['interval_secs'] or 0,
            'isEstimated':      cd['tick_info'].get('is_estimated', False),
            'countdownStr':     cd['tick_info']['countdown_str'],
            # ISK acumulado de la sesión actual
            'sessionIsk':   format_isk(cd['session_isk'], short=True),
            'lblWallet':    '💰 ISK sesión',
        })

    msg_js = f"""<script>
(function() {{
  var chars = {json.dumps(chars_payload)};
  var frames = window.parent.document.querySelectorAll('iframe');
  frames.forEach(function(f) {{
    try {{ f.contentWindow.postMessage({{ type: 'charUpdate', chars: chars }}, '*'); }}
    catch(e) {{}}
  }});
}})();
</script>"""
    components.html(msg_js, height=0, scrolling=False)


def render_chars_section(chars_data: list[dict], lang: str):
    """
    Renderiza la sección de personajes.
    El iframe usa _CHARS_STATIC_HTML (constante) → Streamlit no lo destruye.
    Los datos llegan via postMessage desde send_chars_data().
    """
    n = len(chars_data)
    card_h = max(n * 185 + 20, 185)
    components.html(_CHARS_STATIC_HTML, height=card_h, scrolling=False)
    send_chars_data(chars_data, lang)



# ─── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar():
    lang = st.session_state.lang

    with st.sidebar:
        # ── Controles (primero para acceso rápido) ──
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button(t('btn_start', lang), use_container_width=True, key="btn_s"):
                _dm = st.session_state.get('demo_mode', False)
                start_tracker(st.session_state.log_dir, demo_mode=_dm)
                st.rerun()
        with _c2:
            if st.button(t('btn_stop', lang), use_container_width=True, key="btn_x"):
                if st.session_state.watcher: st.session_state.watcher.stop()
                if st.session_state.demo_gen: st.session_state.demo_gen.stop()
                st.session_state.initialized = False
                st.rerun()
        if st.button(t('btn_reset', lang), use_container_width=True, key="btn_r"):
            reset_session()
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
                t('new_events_only', lang), value=True, help=t('new_events_help', lang), key="skip_tog"
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
        # Botón de overlay HUD
        if _OVERLAY_AVAILABLE:
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

            # ── Indicador de sincronización ──
            discovery_done = status.get('initial_discovery_done', False)
            init_chars = status.get('initial_char_count', 0)
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


# ─── Dashboard ─────────────────────────────────────────────────────────────────

def render_dashboard():
    tracker: MultiAccountTracker = st.session_state.tracker
    lang = st.session_state.lang

    if tracker is None:
        render_welcome(lang)
        return

    now = datetime.now()
    summary = tracker.get_summary(now)

    # Resolución asíncrona de personajes
    char_ids = [cd['character'] for cd in summary['per_character']]
    ensure_chars_resolved(char_ids)

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

    # ── Gráficos: iframe estático (no parpadea) + mensajero de datos ──
    # Selector de ventana temporal — solo afecta visualización, no borra historial
    _win_opts = {'5 min': 5, '20 min': 20, '1 h': 60, '24 h': 1440, 'Todo': 0}
    _cur_win = st.session_state.get('chart_window_minutes', 0)
    _cur_idx = next((i for i, v in enumerate(_win_opts.values()) if v == _cur_win), len(_win_opts)-1)
    _sel = st.radio("📊 Vista", list(_win_opts.keys()), index=_cur_idx, horizontal=True, key="chart_win_r", label_visibility="collapsed")
    st.session_state.chart_window_minutes = _win_opts[_sel]
    token = st.session_state.chart_session_token
    render_charts_iframe(token)   # iframe estático — mismo DOM entre reruns
    send_chart_data(tracker, lang)  # JS invisible que envía datos vía postMessage

    # ── Por personaje ──
    if summary['per_character']:
        st.markdown(f"### {t('by_character', lang)}")
        render_chars_section(summary['per_character'], lang)
    elif st.session_state.initialized:
        # Mostrar solo si no acabamos de renderizar ya este mensaje en este ciclo
        # Usamos un counter en session_state para detectar el doble render
        _render_key = f"_search_msg_{st.session_state.chart_session_token}"
        if not st.session_state.get(_render_key, False):
            st.session_state[_render_key] = True
            st.info("🔍 Buscando personajes activos en los logs de EVE...")
        else:
            # Segundo render del mismo ciclo: limpiar el flag para el próximo ciclo
            st.session_state[_render_key] = False




def render_welcome(lang: str):
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
            start_tracker(st.session_state.get('log_dir', ''), demo_mode=False)
            st.rerun()


# ─── Main ──────────────────────────────────────────────────────────────────────

def render_gear_button():
    """Botón ⚙️ siempre visible para toggle del sidebar."""
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
      var sels=['[data-testid="collapsedControl"] button',
                '[data-testid="stSidebarCollapsedControl"] button',
                'button[aria-label="Open sidebar"]',
                'button[aria-label="Close sidebar"]',
                'button[aria-label="Abrir barra lateral"]',
                'button[aria-label="Cerrar barra lateral"]'];
      for(var i=0;i<sels.length;i++){var b=p.querySelector(sels[i]);if(b){b.click();return;}}
      // Fallback geométrico: buscar botón en la zona superior izquierda
      var btns=p.querySelectorAll('button');
      for(var j=0;j<btns.length;j++){
        var r=btns[j].getBoundingClientRect();
        if(r.left<80&&r.top<80&&r.width<60){btns[j].click();return;}
      }
    }
    </script>
    """, height=0, scrolling=False)


def main():
    init_session_state()
    render_gear_button()
    render_sidebar()
    render_dashboard()

    if st.session_state.initialized and st.session_state.tracker:
        # Enviar datos al overlay HUD si está activo
        if _OVERLAY_AVAILABLE and st.session_state.overlay_server:
            try:
                payload = build_overlay_payload(st.session_state.tracker)
                st.session_state.overlay_server.push(payload)
            except Exception:
                pass
        time.sleep(1.5)
        st.rerun()


if __name__ == "__main__":
    main()
