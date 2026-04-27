import streamlit as st
import streamlit.components.v1 as components

def render_gear_button():
    """Botón de configuración flotante."""
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

def render_theme():
    """CSS global y estilos para el Dashboard."""
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
