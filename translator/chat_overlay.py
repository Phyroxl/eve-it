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
    def __init__(self, msg, translation, profile, lang='es', parent=None):
        super().__init__(parent)
        self._created = time.time()
        self._msg = msg
        self._orig_text = msg.text
        self._fade_secs = profile.fade_seconds
        self._is_alert = is_alert_message(msg.text) or is_alert_message(translation)
        self._lang = lang
        self._setup_ui(msg, translation, profile)

    def _start_portrait_load(self, sender: str):
        """Resolves character_id async and dispatches to main thread via Signal."""
        import threading, weakref as _wr
        ref = _wr.ref(self)

        # Capture signal emitter IN MAIN THREAD before spawning background thread.
        # Signal.emit() is always thread-safe; QTimer.singleShot from a non-Qt
        # thread (no event loop) is NOT reliable — that was the previous bug.
        _emit_fn = None
        p = self.parent()
        for _ in range(10):
            if p is None:
                break
            if hasattr(p, '_portrait_request'):
                _emit_fn = p._portrait_request.emit
                break
            p = p.parent()

        def _resolve():
            try:
                from utils.eve_api import resolve_character_id, _normalize_sender
                sender_clean = _normalize_sender(sender)
                if not sender_clean:
                    logger.debug(f"PORTRAIT SKIP empty sender: {sender!r}")
                    return
                char_id = resolve_character_id(sender_clean)
                if not char_id:
                    logger.debug(f"PORTRAIT NO_ID sender={sender_clean!r}")
                    return
                logger.debug(f"PORTRAIT GOT_ID sender={sender_clean!r} char_id={char_id}")
                if _emit_fn is not None:
                    _emit_fn(ref, char_id)
                else:
                    logger.debug(f"PORTRAIT no overlay signal — skipped char_id={char_id}")
            except Exception as exc:
                logger.debug(f"PORTRAIT resolve error: {exc}")

        threading.Thread(target=_resolve, daemon=True, name=f'portrait_{sender[:8]}').start()

    def _setup_ui(self, msg, translation, profile):
        outer = W.QHBoxLayout(self)
        outer.setContentsMargins(5, 2, 5, 2)
        outer.setSpacing(6)

        self._portrait_lbl = None
        if getattr(profile, 'show_portraits', True):
            self._portrait_lbl = W.QLabel()
            self._portrait_lbl.setFixedSize(32, 32)
            self._portrait_lbl.setText(msg.sender[:1].upper())
            self._portrait_lbl.setAlignment(C.Qt.AlignCenter)
            self._portrait_lbl.setStyleSheet(
                "QLabel{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                "stop:0 #1e293b,stop:1 #0f172a);"
                "border:1px solid #334155;"
                "color:#64748b;font-size:11px;font-weight:bold;}"
            )
            outer.addWidget(self._portrait_lbl, 0, C.Qt.AlignTop)
            self._start_portrait_load(msg.sender)

        content_w = W.QWidget()
        lay = W.QVBoxLayout(content_w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self._content_lay = lay
        
        ch_name = t(msg.channel, self._lang) if msg.channel.startswith('ch_') else msg.channel
        hdr_html = f"[{ch_name}] <a href='https://zkillboard.com/search/{msg.sender}/' style='color:#FFA500; text-decoration:none;'>{msg.sender}</a> {msg.timestamp[-8:]}"
        
        self.lbl_hdr = W.QLabel(hdr_html)
        self.lbl_hdr.setWordWrap(True)
        self.lbl_hdr.setOpenExternalLinks(True)
        self.lbl_hdr.setTextInteractionFlags(C.Qt.TextBrowserInteraction)
        lay.addWidget(self.lbl_hdr)
        self.lbl_orig = None
        if profile.show_original:
            self.lbl_orig = W.QLabel(msg.text)
            self.lbl_orig.setWordWrap(True)
            self.lbl_orig.setTextInteractionFlags(C.Qt.TextSelectableByMouse)
            self.lbl_orig.setCursor(C.Qt.IBeamCursor)
            lay.addWidget(self.lbl_orig)
        self.lbl_tl = None
        if profile.show_translation and translation and translation != msg.text:
            tl_h = W.QHBoxLayout()
            tl_h.setContentsMargins(0, 0, 0, 0)
            tl_h.setSpacing(4)
            
            self.lbl_tl = W.QLabel(f"\u27a4 {translation}")
            self.lbl_tl.setWordWrap(True)
            self.lbl_tl.setTextInteractionFlags(C.Qt.TextSelectableByMouse)
            self.lbl_tl.setCursor(C.Qt.IBeamCursor)
            tl_h.addWidget(self.lbl_tl, 1)
            
            self.btn_copy = W.QPushButton("\u2398") # Icono de copiar
            self.btn_copy.setFixedSize(14, 14)
            self.btn_copy.setCursor(C.Qt.PointingHandCursor)
            self.btn_copy.setToolTip("Copiar traducción")
            self.btn_copy.setStyleSheet("QPushButton{background:transparent;border:none;color:rgba(0,180,255,0.4);font-size:10px;}QPushButton:hover{color:#00c8ff;}")
            self.btn_copy.clicked.connect(lambda: G.QGuiApplication.clipboard().setText(translation))
            tl_h.addWidget(self.btn_copy)
            
            lay.addLayout(tl_h)

        outer.addWidget(content_w, 1)
        self.update_style(profile)

    def update_translation(self, translation, profile):
        if translation and translation != self._msg.text:
            if not self.lbl_tl:
                tl_h = W.QHBoxLayout()
                tl_h.setContentsMargins(0, 0, 0, 0)
                tl_h.setSpacing(4)
                
                self.lbl_tl = W.QLabel()
                self.lbl_tl.setWordWrap(True)
                self.lbl_tl.setTextInteractionFlags(C.Qt.TextSelectableByMouse)
                self.lbl_tl.setCursor(C.Qt.IBeamCursor)
                tl_h.addWidget(self.lbl_tl, 1)
                
                self.btn_copy = W.QPushButton("\u2398")
                self.btn_copy.setFixedSize(14, 14)
                self.btn_copy.setCursor(C.Qt.PointingHandCursor)
                self.btn_copy.setStyleSheet("QPushButton{background:transparent;border:none;color:rgba(0,180,255,0.4);font-size:10px;}QPushButton:hover{color:#00c8ff;}")
                self.btn_copy.clicked.connect(lambda: G.QGuiApplication.clipboard().setText(self.lbl_tl.text().replace("➤ ", "")))
                tl_h.addWidget(self.btn_copy)
                
                getattr(self, '_content_lay', self.layout()).addLayout(tl_h)
            
            self.lbl_tl.setText(f"\u27a4 {translation}")
            self.lbl_tl.show()
            if hasattr(self, 'btn_copy'): self.btn_copy.show()
            self.update_style(profile)

    def update_style(self, profile):
        col = profile.alert_color if self._is_alert else profile.normal_color
        fw = 'bold' if self._is_alert else 'normal'
        self.lbl_hdr.setStyleSheet(f"color:{profile.system_color};font-size:10px;font-weight:bold;background:transparent;border:none;selection-background-color: rgba(0, 180, 255, 0.4);")
        if self.lbl_orig:
            self.lbl_orig.setStyleSheet(f"color:{profile.original_color};font-size:{profile.font_size-1}px;background:transparent;border:none;selection-background-color: rgba(0, 180, 255, 0.4);")
        if self.lbl_tl:
            self.lbl_tl.setStyleSheet(f"color:{col};font-size:{profile.font_size}px;font-weight:{fw};background:transparent;border:none;selection-background-color: rgba(0, 180, 255, 0.4);")
        
        # Estética limpia: SIN bordes ni fondos de caja
        self.setStyleSheet("QFrame{background:transparent;border:none;margin:0;padding:2px;}")

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
    _new_message = C.Signal(object, object)      # (msg, translation)
    _translation_ready = C.Signal(object, str)   # (msg, translated_text)
    _portrait_request = C.Signal(object, int)    # (bubble_weakref, char_id) — cross-thread safe

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
        self._history = [] # Historial de traducciones salientes
        self._is_compact = False
        self._drag_pos = None
        self._watcher = None
        
        self.setWindowOpacity(1.0)
        self.setGeometry(config.overlay_x, config.overlay_y, config.overlay_w, config.overlay_h)
        self.setMinimumSize(235, 150)
        self._setup_ui()
        self._migrate_channels()

        if self._ctrl:
            self._ctrl.state.subscribe(self._on_state_change)
        self._new_message.connect(self._on_new_message_ui)
        self._translation_ready.connect(self._on_translation_ready_ui)
        self._portrait_request.connect(self._on_portrait_request)
        self._user_hidden = False
        self._auto_hidden = False
        self._fg_hide_count = 0
        self._eve_fg_timer = C.QTimer(self)
        self._eve_fg_timer.timeout.connect(self._check_eve_foreground)
        self._eve_fg_timer.start(75)  # 75 ms — matches replicator speed
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
        
        # Variable para controlar si el usuario está al final del scroll
        self._is_at_bottom = True
        tb = W.QWidget()
        tb.setFixedHeight(26)
        tb.setStyleSheet("background:#000000;border-bottom:1px solid rgba(0,180,255,0.3);")
        tbl = W.QHBoxLayout(tb)
        tbl.setContentsMargins(8, 0, 6, 0)
        ico = W.QLabel("\U0001f4ac")
        ico.setStyleSheet("color:#00c8ff;font-size:11px;background:transparent;")
        ttl = W.QLabel("EVE Chat Translator")
        ttl.setStyleSheet("color:rgba(0,200,255,0.8);font-size:10px;background:transparent;")
        
        # Estilo canónico idéntico a la ventana principal (main_suite_window._TitleBar)
        BTN_MIN_STYLE = """
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 3px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 700;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #1e293b;
                color: #e2e8f0;
            }
        """
        BTN_CLS_STYLE = """
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 3px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 700;
                padding: 0;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.2);
                border-color: #ef4444;
                color: #ef4444;
            }
        """
        
        # Paleta
        self._btn_paint = W.QPushButton("\U0001f3a8")
        self._btn_paint.setFixedSize(20, 20)
        self._btn_paint.setStyleSheet(BTN_MIN_STYLE)
        self._btn_paint.setToolTip(t('style_bg_overlay', self._lang))
        self._btn_paint.clicked.connect(self._on_style_menu)
        
        # Idioma
        self._btn_lang = W.QPushButton()
        self._btn_lang.setFixedSize(26, 20)
        self._btn_lang.setStyleSheet(BTN_MIN_STYLE)
        self._btn_lang.setToolTip(t('gui_dlg_lang_title', self._lang))
        flag_path = os.path.join(ASSETS_DIR, f"flag_{self._profile.target_lang}.png")
        self._btn_lang.setIcon(G.QIcon(flag_path))
        self._btn_lang.setIconSize(C.QSize(18, 12))
        self._btn_lang.clicked.connect(self._on_lang_select)

        # Minimizar / Compacto
        self._btn_min = W.QPushButton("\u2212")
        self._btn_min.setFixedSize(20, 20)
        self._btn_min.setStyleSheet(BTN_MIN_STYLE)
        self._btn_min.clicked.connect(self.toggle_compact)
        self._btn_min.setToolTip("Modo Compacto")
        
        # Cerrar
        btn_cls = W.QPushButton("\u00d7")
        btn_cls.setFixedSize(20, 20)
        btn_cls.setStyleSheet(BTN_CLS_STYLE)
        btn_cls.clicked.connect(lambda: (setattr(self, '_user_hidden', True), self.hide()))
        
        # Añadir al layout de la barra (Título IZQUIERDA, Botones DERECHA)
        tbl.addWidget(ico)
        tbl.addWidget(ttl)
        tbl.addStretch()
        tbl.addWidget(self._btn_paint)
        tbl.addWidget(self._btn_lang)
        tbl.addWidget(self._btn_min)
        tbl.addWidget(btn_cls)
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
        self._ml.setSpacing(10) # Más espacio entre bloques de chat
        self._ml.addStretch()
        self._scroll.setWidget(self._mc)
        
        # Detectar cuando el usuario mueve el scroll manualmente
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_manual)
        
        main.addWidget(self._scroll)
        self.setStyleSheet("ChatOverlay{background:#000000;border:1px solid rgba(0,180,255,0.3);}")
        
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
        m.setStyleSheet("QMenu{background:#0d1117;border:1px solid rgba(0,180,255,0.4);color:#00c8ff;font-size:10px;padding:4px;}QMenu::item{padding:5px 16px;}QMenu::item:selected{background:rgba(0,180,255,0.2);}QMenu::indicator:checked{background:#00c8ff;border:1px solid #00c8ff;border-radius:2px;}QMenu::indicator:unchecked{background:transparent;border:1px solid #334155;border-radius:2px;}")
        m.addAction("\U0001f3a8 " + t('style_bg_overlay', self._lang)).triggered.connect(lambda: self._pick_color('bg_color'))
        m.addAction("\U0001f464 " + t('style_msg_bg', self._lang)).triggered.connect(lambda: self._pick_color('system_color'))
        m.addAction("\U0001f4ac " + t('style_msg_text', self._lang)).triggered.connect(lambda: self._pick_color('original_color'))
        m.addAction("\U0001f310 " + t('style_msg_text', self._lang)).triggered.connect(lambda: self._pick_color('normal_color'))
        m.addSeparator()
        act_portraits = m.addAction("\U0001f5bc Mostrar retratos de personajes")
        act_portraits.setCheckable(True)
        act_portraits.setChecked(getattr(self._profile, 'show_portraits', True))
        act_portraits.triggered.connect(self._toggle_portraits)
        m.exec(G.QCursor.pos())

    def _toggle_portraits(self, checked: bool):
        self._profile.show_portraits = checked
        self._config.save_profile(self._profile)
        self._config.save()
        # Toggle visibility of portrait labels in existing message bubbles.
        # When unchecked the QLabel is hidden and the layout collapses the space.
        for bubble in self._bubbles:
            lbl = getattr(bubble, '_portrait_lbl', None)
            if lbl is not None:
                lbl.setVisible(checked)

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
        self.setStyleSheet(f"ChatOverlay{{background:{self._profile.bg_color};border:1px solid rgba(0,180,255,0.4);}}")
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
        for attr in ('_eve_fg_timer', '_fade_timer'):
            t = getattr(self, attr, None)
            if t is not None:
                try: t.stop()
                except Exception: pass
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

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
            
            # Guardar en historial
            if result not in self._history:
                self._history.insert(0, result)
                if len(self._history) > 10: self._history.pop()
                
            self._input_chat.setPlaceholderText("✅ Copiado — pega en EVE con Ctrl+V")
            C.QTimer.singleShot(3000, lambda: self._input_chat.setPlaceholderText(self._composer_placeholder()) if self._input_chat.text() == "" else None)
        self._input_chat.setEnabled(True)
        self._input_chat.clearFocus()

    @C.Slot(object, str)
    def _on_new_message_ui(self, msg, translation):
        try:
            # Comprobar si estábamos al final antes de añadir
            vbar = self._scroll.verticalScrollBar()
            was_at_bottom = vbar.value() >= vbar.maximum() - 20
            
            bubble = MessageBubble(msg, translation, self._profile, self._lang, self._mc)
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
            if was_at_bottom or len(self._bubbles) < 5:
                C.QTimer.singleShot(50, lambda: vbar.setValue(vbar.maximum()))
        except Exception as e:
            logger.debug(f"on_new_message_ui: {e}")

    @C.Slot(object, str)
    def _on_translation_ready_ui(self, msg, translation):
        """Actualiza la burbuja y hace scroll si estábamos al final."""
        if msg.msg_id in self._bubble_map:
            vbar = self._scroll.verticalScrollBar()
            was_at_bottom = self._is_at_bottom or vbar.value() >= vbar.maximum() - 20
            
            bubble = self._bubble_map[msg.msg_id]
            bubble.update_translation(translation, self._profile)
            
            if was_at_bottom:
                C.QTimer.singleShot(50, lambda: vbar.setValue(vbar.maximum()))

    def _on_scroll_manual(self, value):
        """Detecta si el usuario ha subido el scroll para no forzar el final."""
        vbar = self._scroll.verticalScrollBar()
        self._is_at_bottom = (value >= vbar.maximum() - 20)

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


    def _animate_minimize(self):
        """Anima la ventana deslizándose hacia el dock antes de ocultarla."""
        try:
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup
            from PySide6.QtWidgets import QApplication

            self._saved_geo = self.geometry()
            self._saved_opacity = self.windowOpacity()
            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    end_x = tg.x() + tg.width() // 2 - 60
                    end_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                end_x = sg.x() + sg.width() // 2 - 60
                end_y = sg.y() + sg.height() - 50
            end_geo = QRect(end_x, end_y, 120, 30)

            group = QParallelAnimationGroup(self)

            anim_geo = QPropertyAnimation(self, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(self._saved_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.InCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.InCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(self, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(self._saved_opacity)
            anim_op.setEndValue(0.0)
            group.addAnimation(anim_op)

            def _on_finished():
                self.setWindowOpacity(self._saved_opacity)
                self.setGeometry(self._saved_geo)
                self.hide()

            group.finished.connect(_on_finished)
            group.start()
            self._anim_group = group
        except Exception:
            self.hide()

    def _animate_restore(self):
        """Anima la ventana desde el dock hacia su posición original."""
        try:
            if not hasattr(self, '_saved_geo'): return
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup
            from PySide6.QtWidgets import QApplication

            try:
                from controller.control_window import _control_window_ref
                if _control_window_ref and _control_window_ref._win:
                    tg = _control_window_ref._win.geometry()
                    start_x = tg.x() + tg.width() // 2 - 60
                    start_y = tg.y() + tg.height() - 30
                else: raise Exception()
            except:
                screen = QApplication.primaryScreen()
                sg = screen.geometry()
                start_x = sg.x() + sg.width() // 2 - 60
                start_y = sg.y() + sg.height() - 50
            
            start_geo = QRect(start_x, start_y, 120, 30)
            end_geo = self._saved_geo

            self.setGeometry(start_geo)
            self.setWindowOpacity(0.0)

            group = QParallelAnimationGroup(self)

            anim_geo = QPropertyAnimation(self, b'geometry')
            anim_geo.setDuration(250)
            anim_geo.setStartValue(start_geo)
            anim_geo.setEndValue(end_geo)
            anim_geo.setEasingCurve(QEasingCurve.Type.OutCubic if hasattr(QEasingCurve, 'Type') else QEasingCurve.OutCubic)
            group.addAnimation(anim_geo)

            anim_op = QPropertyAnimation(self, b'windowOpacity')
            anim_op.setDuration(250)
            anim_op.setStartValue(0.0)
            anim_op.setEndValue(self._saved_opacity if hasattr(self, '_saved_opacity') else 1.0)
            group.addAnimation(anim_op)

            group.start()
            self._anim_group = group
        except Exception:
            pass

    def _check_eve_foreground(self):
        """Auto-hide when the user switches to an external (non-EVE, non-app) window.

        Uses should_show_overlays() from win32_capture which checks by PID, so
        ALL Salva Suite Qt windows (replicas, HUD, Visual Clon, menus) are
        correctly classified as 'own' without relying on fragile title matching.
        Runs at 75 ms (same as replicator _monitor_focus). Debounce 2 ticks =
        ~150 ms to absorb single-tick OS transitions without introducing flicker.
        """
        try:
            import sys as _sys
            if _sys.platform != 'win32':
                return
            from overlay.win32_capture import should_show_overlays, get_foreground_hwnd_cached, find_eve_windows_cached
            import ctypes as _ct
            hwnd = get_foreground_hwnd_cached()
            if not hwnd:
                # No foreground window reported → transient state, skip
                return
            # Module-level cached find_eve_windows (shared with replicas and HUD)
            eve_hwnds = {w['hwnd'] for w in find_eve_windows_cached()}
            keep = should_show_overlays(hwnd, eve_hwnds)
            if keep:
                self._fg_hide_count = 0
                if self._auto_hidden and not self._user_hidden:
                    self._auto_hidden = False
                    logger.debug("OVERLAY VISIBILITY SHOW reason=returned_to_eve_or_app")
                    self.show()
            else:
                self._fg_hide_count += 1
                if self._fg_hide_count >= 2 and self.isVisible() and not self._user_hidden:
                    self._auto_hidden = True
                    buf = _ct.create_unicode_buffer(256)
                    _ct.windll.user32.GetWindowTextW(hwnd, buf, 256)
                    logger.debug(f"OVERLAY VISIBILITY HIDE reason=external_window title={buf.value!r}")
                    self.hide()
        except Exception as _exc:
            logger.debug(f"Chat FG check error: {_exc}")

    def showEvent(self, event):
        super().showEvent(event)
        try:
            from ui.common.window_shape import force_square_corners
            force_square_corners(int(self.winId()))
        except Exception:
            pass

    @C.Slot(object, int)
    def _on_portrait_request(self, bubble_ref, char_id):
        """Runs in main thread — loads portrait via EveIconService and updates bubble."""
        try:
            from core.eve_icon_service import EveIconService

            def _on_portrait(pixmap):
                sl = bubble_ref()
                if sl is None or not hasattr(sl, '_portrait_lbl') or sl._portrait_lbl is None:
                    return
                try:
                    if pixmap.isNull():
                        logger.debug(f"PORTRAIT PIXMAP NULL char_id={char_id}")
                        return
                    scaled = pixmap.scaled(32, 32, C.Qt.KeepAspectRatio, C.Qt.SmoothTransformation)
                    sl._portrait_lbl.setPixmap(scaled)
                    sl._portrait_lbl.setText("")
                    sl._portrait_lbl.setStyleSheet(
                        "QLabel{border:1px solid #334155;background:transparent;}"
                    )
                    logger.debug(f"PORTRAIT SET OK char_id={char_id}")
                except Exception as exc:
                    logger.debug(f"PORTRAIT set pixmap error: {exc}")

            EveIconService.instance().get_portrait(char_id, 64, _on_portrait)
        except Exception as exc:
            logger.debug(f"PORTRAIT on_portrait_request error: {exc}")

    def toggle_visibility(self):
        self.hide() if self.isVisible() else self.show()

    def toggle_compact(self):
        """Alterna entre modo normal y modo compacto (sin barra ni composer)."""
        self._is_compact = not self._is_compact
        if hasattr(self, '_composer_lay'):
            for i in range(self._composer_lay.count()):
                w = self._composer_lay.itemAt(i).widget()
                if w: w.setVisible(not self._is_compact)
        
        # En modo compacto, el fondo es más transparente
        if self._is_compact:
            self.setStyleSheet(f"ChatOverlay{{background:rgba(0,0,0,0.6);border:1px solid rgba(0,180,255,0.2);}}")
        else:
            self._apply_theme()
            
    def _show_history_menu(self):
        """Muestra el historial de traducciones salientes."""
        if not self._history: return
        m = W.QMenu(self)
        m.setStyleSheet("QMenu{background:#0d1117;border:1px solid rgba(0,180,255,0.4);color:#00c8ff;font-size:10px;padding:4px;}QMenu::item{padding:5px 16px;}QMenu::item:selected{background:rgba(0,180,255,0.2);}")
        for h in self._history:
            a = m.addAction(f"📋 {h[:40]}...")
            a.triggered.connect(lambda checked, text=h: G.QGuiApplication.clipboard().setText(text))
        m.exec(G.QCursor.pos())

    def set_profile(self, profile):
        self._profile = profile
        self._engine.set_target_lang(profile.target_lang)
        self.setWindowOpacity(profile.opacity)

    def _save_pos(self):
        self._config.overlay_x = self.x(); self._config.overlay_y = self.y(); self._config.save()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._grip.move(self.width()-16, self.height()-16)
        self._resizer_marker.move(self.width()-12, self.height()-12)
        self._config.overlay_w = self.width(); self._config.overlay_h = self.height()

    def closeEvent(self, e):
        try:
            from PySide6.QtCore import QSettings
            QSettings("EVE_iT", "ChatOverlay").setValue("geometry", self.saveGeometry())
        except: pass
        super().closeEvent(e)
