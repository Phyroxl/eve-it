"""
chat_sender.py — Módulo asíncrono de traducción para el compositor del EVE Chat Translator.

Responsabilidades:
  - TranslationWorker(QThread): traduce el texto en background sin bloquear la UI.
  - El resultado se devuelve via signal al overlay, que lo copia al portapapeles.
  - El usuario pega manualmente con Ctrl+V en el chat de EVE que tenga activo.

No hay inyección de ventanas ni simulación de teclado: diseño simple y robusto.
"""
import logging
from PySide6 import QtCore as C

logger = logging.getLogger('eve.translator.sender')


class TranslationWorker(C.QThread):
    """
    Ejecuta la traducción en un hilo secundario para no bloquear la UI.

    Señales:
      finished_signal(success: bool, message: str)
        - success=True,  message = texto traducido listo para pegar
        - success=False, message = descripción del error para mostrar al usuario
    """
    finished_signal = C.Signal(bool, str)

    def __init__(self, text: str, engine, target_lang: str, parent=None):
        super().__init__(parent)
        self._text        = text
        self._engine      = engine
        self._target_lang = target_lang

    def run(self):
        try:
            translated = self._engine.translate(self._text, source_lang='auto')
            if not translated or not translated.strip():
                self.finished_signal.emit(False, "⚠️ Traducción vacía")
                return
            self.finished_signal.emit(True, translated.strip())
        except Exception as e:
            logger.debug(f"TranslationWorker error: {e}")
            self.finished_signal.emit(False, f"❌ {str(e)[:50]}")
