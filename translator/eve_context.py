"""eve_context.py - EVE Context Engine"""
EVE_GLOSSARIES = {
    'es': {
        'gate':'gate (puerta estelar)','align':'alinear (preparar warp)',
        'tackle':'tackle (interceptar)','scram':'scramble (bloquear warp)',
        'cyno':'cynosural field','warp':'warp','jump':'salto',
        'dock':'atracar','undock':'desatracar','cloak':'invisibilidad',
        'neut':'neutralizador','point':'warp disruptor','bubble':'burbuja interdiction',
        'camp':'emboscada en gate','gank':'ataque rapido','blob':'flota masiva',
        'kite':'combate a distancia','brawl':'combate cuerpo a cuerpo',
        'overheat':'sobrecalentar','rep':'reparar','logi':'logistica',
        'dps':'dano por segundo','tank':'resistencia','isk':'ISK (moneda EVE)',
        'null':'nullsec','low':'lowsec','high':'highsec','intel':'inteligencia',
        'blue':'aliado','red':'enemigo','neutral':'neutral','fc':'fleet commander',
        'primary':'objetivo principal','secondary':'objetivo secundario',
        'anchor':'seguir al ancla','broadcast':'senal de ayuda','ratting':'matar NPCs',
    },
    'en': {
        # En inglés no solemos necesitar explicaciones extras, pero podemos añadir resaltado futuro
    },
    'zh': {
        'gate':'星门 (Gate)','align':'对准 (Align)','tackle':'捕捉 (Tackle)',
        'scram':'扰频 (Scram)','cyno':'诱导 (Cyno)','warp':'跃迁 (Warp)',
        'jump':'跳跃 (Jump)','dock':'停靠 (Dock)','undock':'出站 (Undock)',
        'cloak':'隐身 (Cloak)','neut':'毁电 (Neut)','point':'扰频 (Point)',
        'bubble':'拦截泡 (Bubble)','isk':'星币 (ISK)','null':'0.0 (Nullsec)',
        'low':'低安 (Lowsec)','high':'高安 (Highsec)','intel':'情报 (Intel)',
        'blue':'蓝方 (Blue)','red':'红方 (Red)','ratting':'刷怪 (Ratting)',
    }
}
ALERT_KEYWORDS = {'hostile','neutral','red','tackle','scram','point','bubble',
    'cyno','kill','jump','warp','primary','fc','broadcast','help','emergency',
    'spike','camp','enemigo','ayuda','emergencia'}

def apply_eve_context(text, target_lang='es'):
    glossary = EVE_GLOSSARIES.get(target_lang, {})
    if not glossary: return text
    words = text.split()
    return ' '.join(glossary.get(w.strip('.,!?;:()[]"').lower(), w) for w in words)

def is_alert_message(text):
    return False

def get_glossary(lang='es'): return dict(EVE_GLOSSARIES.get(lang, {}))
def update_glossary(key, value, lang='es'):
    if lang not in EVE_GLOSSARIES: EVE_GLOSSARIES[lang] = {}
    EVE_GLOSSARIES[lang][key.lower()] = value
