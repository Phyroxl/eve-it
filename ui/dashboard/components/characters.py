import streamlit as st
import streamlit.components.v1 as components
import json
from datetime import datetime
from utils.i18n import t
from utils.formatters import format_isk
from utils.eve_api import get_cached, is_character_id

# HTML para las cards de personaje (estático)
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

  cls('dot_' + c.id, c.status);
  var badge = document.getElementById('badge_' + c.id);
  if (badge) {
    badge.textContent = STATUS_LABEL[c.status] || c.status;
    badge.className = 'badge ' + c.status;
  }
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

var _tickTargets = {};

setInterval(function() {
  var now = Date.now();
  Object.keys(_tickTargets).forEach(function(cid) {
    var td = _tickTargets[cid];
    if (!td || typeof td !== 'object') { delete _tickTargets[cid]; return; }
    var targetMs  = Number(td.target);
    var intervalMs = Number(td.intervalMs);
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

def send_chars_data(chars_data: list[dict], lang: str):
    """Envía datos de personajes al iframe estático via postMessage."""
    chars_payload = []
    for cd in chars_data:
        cid       = cd['character']
        esi       = get_cached(cid)
        if esi is None and is_character_id(cid):
            esi = get_cached(cid)
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
            'tickCount':    cd['tick_info']['tick_count'],
            'nextTickEpoch':    0,
            'secsUntilNext':    cd['tick_info']['secs_until_next']
                                if cd['tick_info']['secs_until_next'] >= 0 else 0,
            'tickIntervalSecs': cd['tick_info']['interval_secs'] or 0,
            'isEstimated':      cd['tick_info'].get('is_estimated', False),
            'countdownStr':     cd['tick_info']['countdown_str'],
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
    """Renderiza la sección de personajes."""
    n = len(chars_data)
    card_h = max(n * 185 + 20, 185)
    components.html(_CHARS_STATIC_HTML, height=card_h, scrolling=False)
    send_chars_data(chars_data, lang)
