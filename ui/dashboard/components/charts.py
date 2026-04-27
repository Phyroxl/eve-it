import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
from datetime import datetime, timedelta
from utils.i18n import t

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


def send_chart_data(tracker, lang: str):
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
