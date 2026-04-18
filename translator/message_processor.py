"""message_processor.py - Message Processor"""
import re
from typing import Optional

NOISE_RE = re.compile(r'^[o]+$|^[\-=_]{3,}$', re.IGNORECASE)
SPAM_SENDERS = {'EVE System', 'EVE Notification', 'Sistema EVE'}

def clean_text(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'http\S+', '[link]', text)
    return text.strip()

def is_noise(msg):
    if msg.sender in SPAM_SENDERS: return True
    if NOISE_RE.match(msg.text.strip()): return True
    if len(msg.text.strip()) < 2: return True
    return False

def detect_language(text):
    if re.search(r'[\u4e00-\u9fff]', text): return 'auto'
    if re.search(r'[\u0400-\u04ff]', text): return 'ru'
    if any(w in text.lower() for w in ['le ','la ','les ','une ','des ','vous ']): return 'fr'
    if any(w in text.lower() for w in ['der ','die ','das ','und ','ist ','ich ']): return 'de'
    if any(w in text.lower() for w in [' el ',' la ',' los ',' que ',' con ']): return 'es'
    return 'auto'

def process(msg):
    if is_noise(msg): return None
    msg.text = clean_text(msg.text)
    if not msg.text: return None
    return msg
