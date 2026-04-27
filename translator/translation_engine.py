"""translation_engine.py - Translation Engine"""
import logging, threading
logger = logging.getLogger('eve.translator')

class TranslationEngine:
    def __init__(self, target_lang='es', max_cache=1000):
        # Mapeo de normalización de códigos (ej. 'zh' -> 'zh-CN')
        self._lang_map = {'zh': 'zh-CN'}
        self._target_lang = self._lang_map.get(target_lang, target_lang)
        self._cache = {}
        self._lock = threading.Lock()
        self._available = False
        self._init_engine()

    @property
    def target_lang(self):
        """Devuelve el idioma destino actual (normalizado)."""
        return self._target_lang

    def _init_engine(self):
        try:
            from deep_translator import GoogleTranslator
            self._available = True
        except ImportError:
            logger.warning("deep-translator no instalado. Ejecuta: pip install deep-translator")

    @property
    def available(self): return self._available

    def set_target_lang(self, lang):
        with self._lock:
            self._target_lang = self._lang_map.get(lang, lang)
            self._cache.clear()

    def translate(self, text, source_lang='auto'):
        if not self._available: return text
        key = f"{source_lang}>{self._target_lang}:{text[:100]}"
        with self._lock:
            if key in self._cache: return self._cache[key]
        try:
            from deep_translator import GoogleTranslator
            result = GoogleTranslator(source=source_lang, target=self._target_lang).translate(text)
            with self._lock:
                if len(self._cache) >= 1000:
                    keys = list(self._cache.keys())
                    for k in keys[:500]: del self._cache[k]
                self._cache[key] = result or text
            return result or text
        except Exception as e:
            logger.debug(f"Translation error: {e}")
            return text

    def translate_async(self, text, callback, source_lang='auto'):
        def _run():
            r = self.translate(text, source_lang)
            try:
                callback(r)
            except Exception as e:
                logger.warning(f"translate_async callback error: {e}")
        threading.Thread(target=_run, daemon=True).start()
