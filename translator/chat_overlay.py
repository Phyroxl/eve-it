import sys, time, logging, os
from pathlib import Path

# Garantizar que el directorio raíz del proyecto esté en sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Ahora importamos las dependencias locales
from typing import Optional
from PySide6 import QtWidgets as W
from PySide6 import QtCore as C
from PySide6 import QtGui as G
from utils.i18n import t

# Importaciones del paquete translator (necesitan que sys.path esté ajustado)
from translator.chat_reader import ChatMessage, ChatWatcher
from translator.message_processor import process, detect_language
from translator.translation_engine import TranslationEngine
from translator.eve_context import is_alert_message, apply_eve_context
from translator.translator_config import TranslatorConfig, TranslatorProfile

logger = logging.getLogger('eve.translator')
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')


class MessageBubble(W.QFrame):
    def __init__(self, msg, translation, profile, parent=None):
        super().__init__(parent)
        self._created = time.time()
        self._msg = msg
        self._orig_text = msg.text
        self._fade_secs = profile.fade_seconds
        self._is_alert = is_alert_message(msg.text) or is_alert_message(translation)
        self._setup_ui(msg, translation, profile)

    def _setup_ui(self, msg, translation, profile):
        lay = W.QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(2)
        col = profile.alert_color if self._is_alert else profile.normal_color
        self.lbl_hdr = W.QLabel(f"[{msg.channel}] {msg.sender}  {msg.timestamp[-8:]}")
        lay.addWidget(self.lbl_hdr)
        self.lbl_orig = None
        if profile.show_original:
            self.lbl_orig = W.QLabel(msg.text)
            self.lbl_orig.setWordWrap(True)
            lay.addWidget(self.lbl_orig)
        self.lbl_tl = None
        if profile.show_translation and translation and translation != msg.text:
            self.lbl_tl = W.QLabel(f"\u27a4 {translation}")
            self.lbl_tl.setWordWrap(True)
            lay.addWidget(self.lbl_tl)
        self.update_style(profile)

    def update_translation(self, translation, profile):
        if translation and translation != self._msg.text:
            if not self.lbl_tl:
                self.lbl_tl = W.QLabel()
                self.lbl_tl.setWordWrap(True)
                self.layout().addWidget(self.lbl_tl)
            self.lbl_tl.setText(f"\u27a4 {translation}")
            self.lbl_tl.show()
            self.update_style(profile)

    def update_style(self, profile):
        col = profile.alert_color if self._is_alert else profile.normal_color
        fw = 'bold' if self._is_alert else 'normal'
        self.lbl_hdr.setStyleSheet(f"color:{profile.system_color};font-size:9px;background:transparent;")
        if self.lbl_orig:
            self.lbl_orig.setStyleSheet(f"color:{profile.original_color};font-size:{profile.font_size-1}px;background:transparent;")
        if self.lbl_tl:
            self.lbl_tl.setStyleSheet(f"color:{col};font-size:{profile.font_size}px;font-weight:{fw};background:transparent;")
        border = 'rgba(0,180,255,0.25)'
        bg = profile.bg_color
        self.setStyleSheet(f"QFrame{{background:{bg};border:1px solid {border};border-radius:5px;margin:1px;}}")

    def retranslate(self, engine, detect_lang_fn, profile):
        try:
            src = detect_lang_fn(self._orig_text)
            tgt = profile.target_lang
            new_tl = self._orig_text if src == tgt else engine.translate(self._orig_text, source_lang=src)
            if profile.translation_mode == 'gamer':
                from translator.eve_context import apply_eve_context
                new_tl = apply_eve_context(new_tl, profile.target_lang)
            col = profile.alert_color if self._is_alert else profile.normal_color
            fw = "bold" if self._is_alert else "normal"
            for child in self.findChildren(W.QLabel):
                if child.text().startswith("➤ "):
                    child.setText(f"➤ {new_tl}")
                    child.setStyleSheet(f"color:{col};font-size:{profile.font_size}px;font-weight:{fw};background:transparent;")
                    break
        except Exception as e:
            pass

    def opacity_ratio(self):
        return 1.0  # Permanente



    def is_expired(self):
        return False  # Permanente


class ChatOverlay(W.QWidget):
    _new_message = C.Signal(object, object) # msg, translation
    _translation_ready = C.Signal(object, str) # msg, translated_text

    def __init__(self, config, parent=None, controller=None):
        super().__init__(parent, C.Qt.WindowStaysOnTopHint | C.Qt.FramelessWindowHint | C.Qt.Tool)
        self._ctrl = controller
        self._config = config
        self._lang = controller.state.language if controller else 'es'
        self._profile = config.get_profile()
        self._engine = TranslationEngine(self._profile.target_lang)
        self._send_lang = self._profile.target_lang  # idioma destino del compositor
        self._send_channel = None  # canal EVE destino seleccionado
        self._bubbles = []
        self._bubble_map = {}
        self._msg_cache = {} 
        self._drag_pos = None
        self._watcher = None
        
        self.setWindowOpacity(1.0)
        self.setGeometry(config.overlay_x, config.overlay_y, config.overlay_w, config.overlay_h)
        self.setMinimumSize(280, 120)
        self._setup_ui()
        self._migrate_channels()

        if self._ctrl:
            self._ctrl.state.subscribe(self._on_state_change)
        self._new_message.connect(self._on_new_message_ui)
        self._translation_ready.connect(self._on_translation_ready_ui)
        self._fade_timer = C.QTimer(self)
        self._fade_timer.timeout.connect(self._update_fade)
        self._fade_timer.start(500)
        try:
            from PySide6.QtGui import QShortcut, QKeySequence
            QShortcut(QKeySequence(self._profile.hotkey_toggle), self).activated.connect(self.toggle_visibility)
        except Exception: pass

    def _migrate_channels(self):
        """Convierte nombres antiguos de canales (Local, Fleet...) a IDs canónicas (ch_local...)."""
        if not hasattr(self._profile, 'active_channels'): return
        mapping = {
            'local': 'ch_local',
            'fleet': 'ch_fleet', 'flota': 'ch_fleet', 'escuadrón': 'ch_fleet',
            'corp': 'ch_corp', 'corp.': 'ch_corp', 'corporación': 'ch_corp',
            'alliance': 'ch_alliance', 'alianza': 'ch_alliance'
        }
        new_channels = []
        changed = False
        for ch in self._profile.active_channels:
            low = ch.lower().strip()
            if low in mapping:
                new_channels.append(mapping[low])
                changed = True
            else:
                new_channels.append(ch)
        
        if changed:
            self._profile.active_channels = list(set(new_channels))
        
        # [NUEVO] Forzar un solo canal si hay múltiples (Limpieza de config antigua)
        if len(self._profile.active_channels) > 1:
            # Si Local está entre ellos, priorizar Local
            if 'ch_local' in self._profile.active_channels:
                self._profile.active_channels = ['ch_local']
            else:
                self._profile.active_channels = [self._profile.active_channels[0]]
            changed = True

        if changed:
            self._config.save_profile(self._profile)
            self._config.save()
            logger.info("Migración y limpieza de canales: Configuración normalizada a un solo canal activo.")

    def _setup_ui(self):
        main = W.QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        tb = W.QWidget()
        tb.setFixedHeight(26)
        tb.setStyleSheet("background:#000000;border-bottom:1px solid rgba(0,180,255,0.3);border-radius:5px 5px 0 0;")
        tbl = W.QHBoxLayout(tb)
        tbl.setContentsMargins(8, 0, 6, 0)
        ico = W.QLabel("\U0001f4ac")
        ico.setStyleSheet("color:#00c8ff;font-size:11px;background:transparent;")
        ttl = W.QLabel("EVE Chat Translator")
        ttl.setStyleSheet("color:rgba(0,200,255,0.8);font-size:10px;background:transparent;")
        
        # Botones de control
        btn_ctrl_style = "QPushButton{background:rgba(0,180,255,0.1);border:none;border-radius:3px;color:rgba(200,230,255,0.5);font-size:11px;}QPushButton:hover{background:rgba(0,180,255,0.25);color:#00c8ff;}"
        
        # Compactar (ahora con icono de cuadro pequeño)
        self._btn_compact = W.QPushButton("\u25ab")
        self._btn_compact.setFixedSize(20, 20)
        self._btn_compact.setStyleSheet(btn_ctrl_style)
        self._btn_compact.setToolTip("Modo Compacto")
        self._btn_compact.clicked.connect(self._toggle_compact)
        
        # Minimizar (Real)
        self._btn_min = W.QPushButton("\u2014")
        self._btn_min.setFixedSize(20, 20)
        self._btn_min.setStyleSheet(btn_ctrl_style)
        self._btn_min.clicked.connect(self.showMinimized)
        
        # Cerrar
        btn_cls = W.QPushButton("\u00d7")
        btn_cls.setFixedSize(20, 20)
        btn_cls.setStyleSheet("QPushButton{background:transparent;border:none;color:rgba(200,230,255,0.4);font-size:16px;}QPushButton:hover{color:#ff4444;}")
        btn_cls.clicked.connect(self.hide)
        
        tbl.addWidget(ico); tbl.addWidget(ttl); tbl.addStretch()
        tbl.addWidget(self._btn_compact)
        tbl.addWidget(self._btn_min)
        tbl.addWidget(btn_cls)
        btn_style = "QPushButton{background:rgba(0,180,255,0.12);border:1px solid rgba(0,180,255,0.3);border-radius:3px;font-size:11px;padding:0;}QPushButton:hover{background:rgba(0,180,255,0.25);}"
        self._btn_paint = W.QPushButton("\U0001f3a8")
        self._btn_paint.setFixedSize(22, 18)
        self._btn_paint.setStyleSheet(btn_style)
        self._btn_paint.setToolTip(t('style_bg_overlay', self._lang))
        self._btn_paint.clicked.connect(self._on_style_menu)
        self._btn_lang = W.QPushButton()
        self._btn_lang.setFixedSize(26, 18)
        self._btn_lang.setStyleSheet(btn_style)
        self._btn_lang.setToolTip(t('gui_dlg_lang_title', self._lang))
        flag_path = os.path.join(ASSETS_DIR, f"flag_{self._profile.target_lang}.png")
        self._btn_lang.setIcon(G.QIcon(flag_path))
        self._btn_lang.setIconSize(C.QSize(20, 14))
        self._btn_lang.clicked.connect(self._on_lang_select)
        tbl.addWidget(self._btn_paint)
        tbl.addWidget(self._btn_lang)
        tbl.addWidget(self._btn_compact); tbl.addWidget(btn_cls)
        tb.mousePressEvent = lambda e: setattr(self, '_drag_pos', e.globalPosition().toPoint() - self.frameGeometry().topLeft()) if e.button()==C.Qt.LeftButton else None
        tb.mouseMoveEvent = lambda e: self.move(e.globalPosition().toPoint() - self._drag_pos) if self._drag_pos and e.buttons()==C.Qt.LeftButton else None
        tb.mouseReleaseEvent = lambda e: (setattr(self,'_drag_pos',None), self._save_pos())
        main.addWidget(tb)
        self._scroll = W.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}QScrollBar:vertical{width:4px;}QScrollBar::handle:vertical{background:rgba(0,180,255,0.4);border-radius:2px;}")
        self._mc = W.QWidget()
        self._mc.setStyleSheet("background:transparent;")
        self._ml = W.QVBoxLayout(self._mc)
        self._ml.setContentsMargins(4,4,4,4)
        self._ml.setSpacing(3)
        self._ml.addStretch()
        self._scroll.setWidget(self._mc)
        main.addWidget(self._scroll)
        self.setStyleSheet("ChatOverlay{background:#000000;border:1px solid rgba(0,180,255,0.3);border-radius:5px;}")
        
        # Composer Integrado: [Canal] [Input] [Bandera]
        self._composer_lay = W.QHBoxLayout()
        self._composer_lay.setContentsMargins(6, 4, 6, 4)
        self._composer_lay.setSpacing(4)

        # Botón canal (izquierda)
        btn_ch_style = "QPushButton{background:rgba(0,180,255,0.12);border:1px solid rgba(0,180,255,0.3);border-radius:4px;color:#00c8ff;font-size:10px;padding:0 4px;}QPushButton:hover{background:rgba(0,180,255,0.28);}"
        self._btn_channel = W.QPushButton("📡")
        self._btn_channel.setFixedSize(28, 24)
        self._btn_channel.setStyleSheet(btn_ch_style)
        self._btn_channel.setToolTip("Seleccionar canal destino")
        self._btn_channel.clicked.connect(self._on_channel_select)
        self._composer_lay.addWidget(self._btn_channel)

        # Input (centro)
        self._input_chat = W.QLineEdit()
        self._input_chat.setPlaceholderText(self._composer_placeholder())
        self._input_chat.setStyleSheet("background:rgba(13,22,38,0.8);border:1px solid rgba(0,180,255,0.3);border-radius:4px;color:#00c8ff;padding:4px;font-size:11px;")
        self._input_chat.returnPressed.connect(self._on_chat_send)
        self._composer_lay.addWidget(self._input_chat)

        # Botón bandera idioma (derecha)
        self._btn_send_lang = W.QPushButton()
        self._btn_send_lang.setFixedSize(28, 24)
        self._btn_send_lang.setStyleSheet("QPushButton{background:rgba(0,180,255,0.12);border:1px solid rgba(0,180,255,0.3);border-radius:4px;padding:0;}QPushButton:hover{background:rgba(0,180,255,0.28);}")
        send_flag = os.path.join(ASSETS_DIR, f"flag_{self._send_lang}.png")
        self._btn_send_lang.setIcon(G.QIcon(send_flag))
        self._btn_send_lang.setIconSize(C.QSize(20, 14))
        self._btn_send_lang.setToolTip("Idioma de salida")
        self._btn_send_lang.clicked.connect(self._on_send_lang_select)
        self._composer_lay.addWidget(self._btn_send_lang)

        main.addLayout(self._composer_lay)
        
        self._grip = W.QSizeGrip(self)
        self._grip.setStyleSheet("background:transparent;")
        
        # [NUEVO] Indicador visual de redimensionado (Flecha Roja)
        self._resizer_marker = W.QLabel(self)
        self._resizer_marker.setText("◢") # Triángulo de esquina
        self._resizer_marker.setStyleSheet("color: rgba(255, 50, 50, 0.8); font-size: 16px; background: transparent;")
        self._resizer_marker.setFixedSize(16, 16)
        self._resizer_marker.setAttribute(C.Qt.WA_TransparentForMouseEvents)
        self._resizer_marker.raise_()

    def _composer_placeholder(self) -> str:
        """Genera el placeholder mostrando idioma destino (y canal si está fijado)."""
        lang_names = {
            'es': 'Español', 'en': 'English', 'zh': '简体中文',
            'ru': 'Русский', 'fr': 'Français', 'de': 'Deutsch',
            'pt': 'Português', 'it': 'Italiano'
        }
        lang_name = lang_names.get(self._send_lang, self._send_lang.upper())
        base = t('chat_ph_text', self._lang)  # e.g. "✎ Escribe y pulsa Enter para traducir a"
        if self._send_channel:
            return f"{base} [{lang_name}] → #{self._send_channel}..."
        return f"{base} [{lang_name}]..."

    def _on_state_change(self, state):
        if state.language != self._lang:
            self._lang = state.language
            self._btn_paint.setToolTip(t('style_bg_overlay', self._lang))
            self._btn_lang.setToolTip(t('gui_dlg_lang_title', self._lang))
            if hasattr(self, '_input_chat') and self._input_chat.isEnabled():
                self._input_chat.setPlaceholderText(self._composer_placeholder())
            # Actualizar bandera si es necesario (opcional)

    def _on_style_menu(self):
        m = W.QMenu(self)
        m.setStyleSheet("QMenu{background:#0d1117;border:1px solid rgba(0,180,255,0.4);color:#00c8ff;font-size:10px;padding:4px;}QMenu::item{padding:5px 16px;}QMenu::item:selected{background:rgba(0,180,255,0.2);}")
        m.addAction("🎨 " + t('style_bg_overlay', self._lang)).triggered.connect(lambda: self._pick_color('bg_color'))
        m.addAction("👤 " + t('style_msg_bg', self._lang)).triggered.connect(lambda: self._pick_color('system_color'))
        m.addAction("💬 " + t('style_msg_text', self._lang)).triggered.connect(lambda: self._pick_color('original_color'))
        m.addAction("🌐 " + t('style_msg_text', self._lang)).triggered.connect(lambda: self._pick_color('normal_color'))
        m.exec(G.QCursor.pos())

    def _pick_color(self, attr_name):
        initial = G.QColor(getattr(self._profile, attr_name))
        color = W.QColorDialog.getColor(initial, self, t('style_picker_title', self._lang))
        if color.isValid():
            hex_color = color.name()
            setattr(self._profile, attr_name, hex_color)
            self._config.save_profile(self._profile)
            self._config.save()
            self._apply_theme()

    def _apply_theme(self):
        # Forzar opacidad y color de fondo del overlay
        self.setWindowOpacity(1.0)
        self.setStyleSheet(f"ChatOverlay{{background:{self._profile.bg_color};border:1px solid rgba(0,180,255,0.4);border-radius:5px;}}")
        self.style().unpolish(self)
        self.style().polish(self)
        
        # Actualizar todas las burbujas existentes
        for b in self._bubbles:
            try:
                b.update_style(self._profile)
                b.update()
            except Exception: pass
        self.update()

    def _on_lang_select(self):
        langs = [
            (os.path.join(ASSETS_DIR, "flag_zh.png"), "简体中文",   "zh"),
            (os.path.join(ASSETS_DIR, "flag_es.png"), "Español",   "es"),
            (os.path.join(ASSETS_DIR, "flag_en.png"), "English",    "en"),
            (os.path.join(ASSETS_DIR, "flag_fr.png"), "Français",   "fr"),
            (os.path.join(ASSETS_DIR, "flag_de.png"), "Deutsch",    "de"),
            (os.path.join(ASSETS_DIR, "flag_ru.png"), "Русский",    "ru"),
            (os.path.join(ASSETS_DIR, "flag_pt.png"), "Português",  "pt"),
            (os.path.join(ASSETS_DIR, "flag_it.png"), "Italiano",   "it"),
        ]
        menu = W.QMenu(self)
        menu.setStyleSheet("QMenu{background:#0d1117;border:1px solid rgba(0,180,255,0.4);color:#00c8ff;font-size:11px;padding:4px;}QMenu::item{padding:5px 16px;}QMenu::item:selected{background:rgba(0,180,255,0.2);}")
        for icon_path, name, code in langs:
            a = menu.addAction(name)
            a.setIcon(G.QIcon(icon_path))
            a.setData(code)
        pos = self._btn_lang.mapToGlobal(self._btn_lang.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen:
            code = chosen.data()
            icon_path = next(p for p, n, c in langs if c == code)
            self._btn_lang.setIcon(G.QIcon(icon_path))
            self._btn_lang.setIconSize(C.QSize(20, 14))
            self._profile.target_lang = code
            from translator.translation_engine import TranslationEngine
            self._engine = TranslationEngine(code)
            for bubble in self._bubbles:
                try:
                    bubble.retranslate(self._engine, detect_language, self._profile)
                except Exception:
                    pass

    def _on_channel_select(self):
        """Cambia qué canal del chat de EVE monitoriza y traduce el overlay."""
        menu = W.QMenu(self)
        menu.setStyleSheet("QMenu{background:#0d1117;border:1px solid rgba(0,180,255,0.4);color:#00c8ff;font-size:11px;padding:4px;}QMenu::item{padding:5px 16px;}QMenu::item:selected{background:rgba(0,180,255,0.2);}")

        # Usar get_all_channels() que escanea TODOS los archivos (incluye privados y normaliza Fleet)
        all_channels = []
        if self._watcher:
            all_channels = self._watcher.get_all_channels()

        # Si el watcher aún no tiene logs, ofrecer mínimos predeterminados
        if not all_channels:
            all_channels = ['Local', 'Corp.', 'Alianza', 'Fleet']

        active = getattr(self._watcher, '_active_channels', set()) if self._watcher else set()
        for ch in all_channels:
            # ch aquí es la ID canónica (ch_local, ch_fleet...) o el nombre crudo para privados
            display_name = t(ch, self._lang) if ch.startswith('ch_') else ch
            marker = "• " if ch in active else "   "
            a = menu.addAction(f"{marker}🗨️  {display_name}")
            a.setData(ch)

        pos = self._btn_channel.mapToGlobal(self._btn_channel.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen and chosen.data():
            ch = chosen.data()
            if self._watcher:
                self._watcher.set_active_channel(ch)
            if hasattr(self._profile, 'active_channels'):
                self._profile.active_channels = [ch]
            self._btn_channel.setToolTip(f"🗨️ {ch}")
            # Limpiar burbujas del canal anterior
            for b in list(self._bubbles):
                self._ml.removeWidget(b)
                b.deleteLater()
            self._bubbles.clear()

    def _on_send_lang_select(self):
        """Menú de selección de idioma destino para mensajes salientes del compositor."""
        langs = [
            (os.path.join(ASSETS_DIR, "flag_zh.png"), "简体中文", "zh"),
            (os.path.join(ASSETS_DIR, "flag_es.png"), "Español",  "es"),
            (os.path.join(ASSETS_DIR, "flag_en.png"), "English",   "en"),
            (os.path.join(ASSETS_DIR, "flag_fr.png"), "Français",  "fr"),
            (os.path.join(ASSETS_DIR, "flag_de.png"), "Deutsch",   "de"),
            (os.path.join(ASSETS_DIR, "flag_ru.png"), "Русский",   "ru"),
            (os.path.join(ASSETS_DIR, "flag_pt.png"), "Português", "pt"),
            (os.path.join(ASSETS_DIR, "flag_it.png"), "Italiano",  "it"),
        ]
        menu = W.QMenu(self)
        menu.setStyleSheet("QMenu{background:#0d1117;border:1px solid rgba(0,180,255,0.4);color:#00c8ff;font-size:11px;padding:4px;}QMenu::item{padding:5px 16px;}QMenu::item:selected{background:rgba(0,180,255,0.2);}")
        for icon_path, name, code in langs:
            a = menu.addAction(name)
            a.setIcon(G.QIcon(icon_path))
            a.setData(code)
        pos = self._btn_send_lang.mapToGlobal(self._btn_send_lang.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen:
            code = chosen.data()
            self._send_lang = code
            icon_path = next(p for p, n, c in langs if c == code)
            self._btn_send_lang.setIcon(G.QIcon(icon_path))
            self._btn_send_lang.setIconSize(C.QSize(20, 14))
            # Crear un engine de salida dedicado con el nuevo idioma destino
            self._send_engine = TranslationEngine(code)

    def start(self):
        if self._watcher: return
        self._watcher = ChatWatcher(callback=self._on_chat_message, active_channels=set(self._profile.active_channels))
        self._watcher.start()

    def stop(self):
        if self._watcher: self._watcher.stop(); self._watcher = None

    def _on_chat_message(self, msg):
        try:
            now = time.time()
            # Limpiar caché antiguo (más de 10 segundos)
            self._msg_cache = {k: v for k, v in self._msg_cache.items() if now - v < 10.0}
            
            # Crear huella digital del mensaje (Emisor + Texto)
            fingerprint = (msg.sender, msg.text.strip())
            if fingerprint in self._msg_cache:
                return # IGNORAR DUPLICADO
            
            self._msg_cache[fingerprint] = now
            
            processed = process(msg)
            if not processed: return
            
            # Normalizar canal recibido para el check de filtro
            # (El watcher ya debería enviar ch_local, pero aseguramos robustez)
            ch_id = msg.channel.lower().strip()
            active_list = [c.lower().strip() for c in (self._profile.active_channels or [])]
            
            # EMISIÓN INSTANTÁNEA: Mostrar el original de inmediato
            self._new_message.emit(msg, None)
            
            # TRADUCCIÓN EN SEGUNDO PLANO
            def _async_done(result):
                if self._profile.translation_mode == 'gamer':
                    result = apply_eve_context(result, self._profile.target_lang)
                self._translation_ready.emit(msg, result)
            
            src = detect_language(msg.text)
            if src == self._profile.target_lang:
                _async_done(msg.text)
            else:
                self._engine.translate_async(msg.text, _async_done, source_lang=src)
        except Exception as e:
            logger.debug(f"on_chat_message: {e}")

    def _on_chat_send(self):
        text = self._input_chat.text().strip()
        if not text: return

        self._input_chat.setEnabled(False)
        self._input_chat.setText("")
        self._input_chat.setPlaceholderText(t('chat_ph_translating', self._lang))

        from translator.chat_sender import TranslationWorker
        # Determinar idioma de salida: el elegido en el botón de bandera del compositor
        send_lang = getattr(self, '_send_lang', self._profile.target_lang)

        # Mapeo de normalización (debe coincidir con TranslationEngine)
        target_needed = {'zh': 'zh-CN'}.get(send_lang, send_lang)

        # Validar que el engine coincide con send_lang (usando la propiedad target_lang)
        send_engine = getattr(self, '_send_engine', None)
        current_target = getattr(send_engine, 'target_lang', None)

        if send_engine is None or current_target != target_needed:
            logger.debug(f"Creando nuevo TranslationEngine para salida: {send_lang} (target: {target_needed})")
            self._send_engine = TranslationEngine(send_lang)
            send_engine = self._send_engine

        self._worker = TranslationWorker(text, send_engine, send_lang, self)
        self._worker.finished_signal.connect(self._on_worker_finished)
        self._worker.start()

    @C.Slot(bool, str)
    def _on_worker_finished(self, success, result):
        if not success:
            self._input_chat.setPlaceholderText(result)
            C.QTimer.singleShot(3000, lambda: self._input_chat.setPlaceholderText(self._composer_placeholder()) if self._input_chat.text() == "" else None)
        else:
            # Éxito: copiar al portapapeles para que el usuario pegue con Ctrl+V
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(result)
            self._input_chat.setPlaceholderText("✅ Copiado — pega en EVE con Ctrl+V")
            C.QTimer.singleShot(3000, lambda: self._input_chat.setPlaceholderText(self._composer_placeholder()) if self._input_chat.text() == "" else None)
        self._input_chat.setEnabled(True)
        self._input_chat.clearFocus()

    @C.Slot(object, str)
    def _on_new_message_ui(self, msg, translation):
        try:
            bubble = MessageBubble(msg, translation, self._profile, self._mc)
            self._ml.insertWidget(self._ml.count()-1, bubble)
            self._bubbles.append(bubble)
            
            # Registrar burbuja para actualización posterior
            self._bubble_map[msg.msg_id] = bubble
            
            while len(self._bubbles) > self._profile.max_messages:
                old = self._bubbles.pop(0)
                if old._msg.msg_id in self._bubble_map:
                    del self._bubble_map[old._msg.msg_id]
                self._ml.removeWidget(old)
                old.deleteLater()
            C.QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum()))
        except Exception as e:
            logger.debug(f"on_new_message_ui: {e}")

    @C.Slot(object, str)
    def _on_translation_ready_ui(self, msg, translation):
        """Actualiza la burbuja cuando la traducción está disponible."""
        if msg.msg_id in self._bubble_map:
            bubble = self._bubble_map[msg.msg_id]
            bubble.update_translation(translation, self._profile)

    def _update_fade(self):
        for b in list(self._bubbles):
            if b.is_expired():
                self._bubbles.remove(b)
                self._ml.removeWidget(b)
                b.deleteLater()
            else:
                op = b.opacity_ratio()
                eff = b.graphicsEffect() or W.QGraphicsOpacityEffect(b)
                b.setGraphicsEffect(eff)
                eff.setOpacity(op)

    def _toggle_compact(self):
        self._profile.compact_mode = not self._profile.compact_mode
        if self._profile.compact_mode:
            self._scroll.hide(); self.setFixedHeight(26); self._btn_compact.setText("+")
        else:
            self._scroll.show(); self.setMinimumHeight(120); self.resize(self.width(), max(self.height(),300)); self._btn_compact.setText("\u2212")

    def toggle_visibility(self):
        self.hide() if self.isVisible() else self.show()

    def set_profile(self, profile):
        self._profile = profile
        self._engine.set_target_lang(profile.target_lang)
        self.setWindowOpacity(profile.opacity)

    def _save_pos(self):
        self._config.overlay_x = self.x(); self._config.overlay_y = self.y(); self._config.save()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._grip.move(self.width()-16, self.height()-16)
        self._resizer_marker.move(self.width()-14, self.height()-14)
        self._config.overlay_w = self.width(); self._config.overlay_h = self.height()
