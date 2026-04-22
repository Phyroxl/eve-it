from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QFrame, QLabel, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QSizeGrip, QScrollArea, QGridLayout,
    QLineEdit, QCheckBox, QDoubleSpinBox, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QTimer, QSettings
from PySide6.QtGui import QColor, QIcon, QFont, QLinearGradient

from ui.desktop.styles import MAIN_STYLE
from utils.formatters import format_isk

class MainSuiteWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.tray_manager = None
        self.setWindowTitle("EVE iT — Suite Control Panel")
        self.resize(1100, 750)
        
        # UI References for updating
        self.val_total_isk = None
        self.val_isk_h = None
        self.val_accounts = None
        self.accounts_layout = None
        self.account_cards = {} # {char_name: card_widget}
        
        # Settings UI Refs
        self.edit_log_dir = None
        self.check_skip_logs = None
        self.spin_ess_retention = None
        self.combo_lang = None
        
        self.setup_ui()
        self.apply_styles()
        self.load_settings()
        self.restore_geometry()
        
        # Timer for real-time updates (Metrics & Accounts)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh_data)
        self.update_timer.start(1500)
        
        # Timer for the clock (Header)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        
    def update_clock(self):
        """Actualiza el reloj de sesión cada segundo para que se sienta vivo."""
        if not self.controller or not self.controller._tracker:
            return
        try:
            from datetime import datetime
            now = datetime.now()
            summary = self.controller._tracker.get_summary(now)
            from utils.formatters import format_duration
            self.session_info.setText(f"SESIÓN: {format_duration(summary.get('session_duration'))}")
        except: pass

    def setup_ui(self):
        # Central Widget
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)
        
        # Main Horizontal Layout
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Navigation Bar (Left Sidebar)
        self.nav_bar = QFrame()
        self.nav_bar.setObjectName("NavBar")
        self.nav_layout = QVBoxLayout(self.nav_bar)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(0)
        
        # Logo Area
        self.logo_label = QLabel("EVE iT")
        self.logo_label.setObjectName("LogoLabel")
        self.nav_layout.addWidget(self.logo_label)
        
        # Navigation Buttons
        self.btn_dashboard = self.create_nav_button("📊 RESUMEN", True)
        self.btn_hud = self.create_nav_button("🕹️ HUD OVERLAY")
        self.btn_translator = self.create_nav_button("🌐 TRADUCTOR")
        self.btn_replicator = self.create_nav_button("🪟 REPLICADOR")
        
        self.nav_layout.addWidget(self.btn_dashboard)
        self.nav_layout.addWidget(self.btn_hud)
        self.nav_layout.addWidget(self.btn_translator)
        self.nav_layout.addWidget(self.btn_replicator)
        
        self.nav_layout.addStretch()
        
        # Settings button at bottom
        self.btn_settings = self.create_nav_button("⚙️ AJUSTES")
        self.nav_layout.addWidget(self.btn_settings)
        
        # 2. Content Area (Right Side)
        self.content_frame = QFrame()
        self.content_frame.setObjectName("ContentFrame")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(25, 25, 25, 25)
        self.content_layout.setSpacing(20)
        
        # Top Header
        header_layout = QHBoxLayout()
        self.section_title = QLabel("PANEL DE CONTROL")
        self.section_title.setObjectName("SectionTitle")
        header_layout.addWidget(self.section_title)
        
        header_layout.addSpacing(30)
        
        # Status Badge
        self.status_badge = QLabel("DETENIDO")
        self.status_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 68, 68, 0.1);
                color: #ff4444;
                border: 1px solid rgba(255, 68, 68, 0.3);
                border-radius: 10px;
                padding: 2px 12px;
                font-family: 'Share Tech Mono';
                font-size: 10px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self.status_badge)
        
        header_layout.addStretch()
        
        # Session Controls
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setSpacing(8)
        
        self.btn_start = self.create_control_button("▶ INICIAR", "#00ff9d")
        self.btn_stop = self.create_control_button("⏹ PARAR", "#ff4444")
        self.btn_reset = self.create_control_button("🔄 RESET", "#ffffff")
        
        self.controls_layout.addWidget(self.btn_start)
        self.controls_layout.addWidget(self.btn_stop)
        self.controls_layout.addWidget(self.btn_reset)
        
        header_layout.addLayout(self.controls_layout)
        
        header_layout.addSpacing(20)
        
        # Session info
        self.session_info = QLabel("SESIÓN: --:--:--")
        self.session_info.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(200, 230, 255, 0.4); font-size: 12px;")
        header_layout.addWidget(self.session_info)
        
        self.content_layout.addLayout(header_layout)
        
        # Stacked Widget for pages
        self.stack = QStackedWidget()
        self.content_layout.addWidget(self.stack)
        
        # Pages
        self.page_dashboard = self.create_dashboard_page()
        self.page_settings = self.create_settings_page()
        self.stack.addWidget(self.page_dashboard)
        self.stack.addWidget(self.page_settings)
        
        # Add NavBar and Content to Main Layout
        self.main_layout.addWidget(self.nav_bar)
        self.main_layout.addWidget(self.content_frame, 1)

        # Connect Signals
        self.btn_dashboard.clicked.connect(self._on_nav_dashboard)
        self.btn_settings.clicked.connect(self._on_nav_settings)
        self.btn_hud.clicked.connect(self._on_hud_clicked)
        self.btn_translator.clicked.connect(self._on_translator_clicked)
        self.btn_replicator.clicked.connect(self._on_replicator_clicked)
        
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_reset.clicked.connect(self._on_reset_clicked)

    def closeEvent(self, event):
        """Guardar posición y ocultar en lugar de cerrar."""
        try:
            settings = QSettings("EVE_iT", "Suite")
            settings.setValue("geometry", self.saveGeometry())
        except: pass
        event.ignore()
        self.hide()

    def restore_geometry(self):
        try:
            settings = QSettings("EVE_iT", "Suite")
            saved_geo = settings.value("geometry")
            if saved_geo:
                self.restoreGeometry(saved_geo)
        except: pass

    def _on_nav_dashboard(self):
        self.stack.setCurrentIndex(0)
        self.section_title.setText("PANEL DE CONTROL")
        self._update_nav_active(self.btn_dashboard)

    def _on_nav_settings(self):
        self.stack.setCurrentIndex(1)
        self.section_title.setText("AJUSTES")
        self._update_nav_active(self.btn_settings)

    def _update_nav_active(self, active_btn):
        for btn in [self.btn_dashboard, self.btn_hud, self.btn_translator, self.btn_replicator, self.btn_settings]:
            btn.setProperty("active", "true" if btn == active_btn else "false")
            btn.setStyle(btn.style()) # Trigger restyle

    def create_control_button(self, text, color):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(90, 28)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                color: {color};
                font-family: 'Share Tech Mono';
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
                border-color: {color};
            }}
            QPushButton:disabled {{
                color: rgba(255,255,255,0.1);
                border-color: transparent;
                background-color: transparent;
            }}
        """)
        return btn

    def refresh_data(self):
        """Actualiza las métricas y la lista de cuentas con datos reales."""
        if not self.controller:
            return
            
        try:
            from datetime import datetime
            now = datetime.now()
            
            # Sync Controls State
            is_running = self.controller.state.tracker_running
            self.btn_start.setEnabled(not is_running)
            self.btn_stop.setEnabled(is_running)
            
            if is_running:
                self.status_badge.setText("EN EJECUCIÓN")
                self.status_badge.setStyleSheet("""
                    background-color: rgba(0, 255, 157, 0.1);
                    color: #00ff9d;
                    border: 1px solid rgba(0, 255, 157, 0.3);
                    border-radius: 10px; padding: 2px 12px;
                    font-family: 'Share Tech Mono'; font-size: 10px; font-weight: bold;
                """)
            else:
                self.status_badge.setText("DETENIDO")
                self.status_badge.setStyleSheet("""
                    background-color: rgba(255, 68, 68, 0.1);
                    color: #ff4444;
                    border: 1px solid rgba(255, 68, 68, 0.3);
                    border-radius: 10px; padding: 2px 12px;
                    font-family: 'Share Tech Mono'; font-size: 10px; font-weight: bold;
                """)

            if not self.controller._tracker:
                # Si no hay tracker, poner métricas a cero pero seguir actualizando controles
                if self.val_total_isk: self.val_total_isk.setText("0.00 ISK")
                if self.val_isk_h: self.val_isk_h.setText("0.00 ISK/h")
                if self.val_accounts: self.val_accounts.setText("0 ACTIVAS")
                self.session_info.setText("SESIÓN: --:--:--")
                self.update_accounts_view([])
                return

            summary = self.controller._tracker.get_summary(now)
            
            # 1. Update Global Metrics
            if self.val_total_isk:
                self.val_total_isk.setText(format_isk(summary.get('total_isk', 0), short=True))
            if self.val_isk_h:
                self.val_isk_h.setText(format_isk(summary.get('isk_per_hour_rolling', 0), short=True) + "/h")
            if self.val_accounts:
                count = summary.get('character_count', 0)
                self.val_accounts.setText(f"{count} ACTIVAS")
            
            # 2. Update Account List
            self.update_accounts_view(summary.get('per_character', []))
                
        except Exception as e:
            import traceback
            # print(f"Error actualizando métricas en Suite: {e}")

    def _on_start_clicked(self):
        if self.controller:
            settings = QSettings("EVE_iT", "Suite")
            log_dir = settings.value("log_dir", "")
            skip_logs = settings.value("skip_logs", "true") == "true"
            ess = float(settings.value("ess_retention", 1.0))
            
            self.controller.start_tracker(
                log_dir=log_dir,
                skip_existing=skip_logs,
                ess_retention=ess
            )

    def _on_stop_clicked(self):
        if self.controller:
            self.controller.stop_tracker()

    def _on_reset_clicked(self):
        if self.controller:
            self.controller.reset_tracker()

    def update_accounts_view(self, accounts):
        """Crea o actualiza las tarjetas de cuenta."""
        if not self.accounts_layout:
            return

        active_names = [a.get('display_name', a.get('character')) for a in accounts]
        
        # Remove cards for accounts that are no longer active
        for name in list(self.account_cards.keys()):
            if name not in active_names:
                card = self.account_cards.pop(name)
                self.accounts_layout.removeWidget(card)
                card.deleteLater()

        # Update or create cards
        for i, acc in enumerate(accounts):
            name = acc.get('display_name', acc.get('character'))
            if name not in self.account_cards:
                card = self.create_account_card(acc)
                self.account_cards[name] = card
                # Add to grid: 3 columns
                row = i // 3
                col = i % 3
                self.accounts_layout.addWidget(card, row, col)
            else:
                self.update_account_card(self.account_cards[name], acc)

    def create_account_card(self, acc):
        card = QFrame()
        card.setObjectName("AccountCard")
        card.setStyleSheet("""
            QFrame#AccountCard {
                background-color: rgba(6, 14, 26, 0.6);
                border: 1px solid rgba(0, 180, 255, 0.1);
                border-radius: 6px;
                padding: 10px;
            }
            QFrame#AccountCard:hover {
                border-color: rgba(0, 180, 255, 0.3);
            }
        """)
        card.setMinimumWidth(250)
        
        l = QVBoxLayout(card)
        l.setSpacing(4)
        
        # Header: Name + Status
        h = QHBoxLayout()
        name_lbl = QLabel(acc.get('display_name', acc.get('character')))
        name_lbl.setObjectName("AccName")
        name_lbl.setStyleSheet("font-family: 'Orbitron'; font-size: 13px; color: #ffffff; font-weight: bold;")
        
        status_dot = QLabel("●")
        status_dot.setObjectName("AccStatus")
        status_dot.setStyleSheet("font-size: 14px; color: #00ff9d;")
        
        h.addWidget(name_lbl)
        h.addStretch()
        h.addWidget(status_dot)
        l.addLayout(h)
        
        # ISK Stats
        stats = QHBoxLayout()
        
        total_l = QVBoxLayout()
        t_lbl = QLabel("TOTAL")
        t_lbl.setStyleSheet("font-size: 9px; color: rgba(200,230,255,0.4);")
        t_val = QLabel(format_isk(acc.get('total_isk', 0), short=True))
        t_val.setObjectName("AccTotal")
        t_val.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 12px; color: #ffd700; font-weight: bold;")
        total_l.addWidget(t_lbl)
        total_l.addWidget(t_val)
        
        roll_l = QVBoxLayout()
        r_lbl = QLabel("ROLLING")
        r_lbl.setStyleSheet("font-size: 9px; color: rgba(200,230,255,0.4);")
        r_val = QLabel(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        r_val.setObjectName("AccRoll")
        r_val.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 12px; color: #00ff9d;")
        roll_l.addWidget(r_lbl)
        roll_l.addWidget(r_val)
        
        stats.addLayout(total_l)
        stats.addLayout(roll_l)
        l.addLayout(stats)
        
        # Last Activity
        last_act = QLabel("ÚLTIMO: ---")
        last_act.setObjectName("AccLast")
        last_act.setStyleSheet("font-size: 10px; color: rgba(0, 180, 255, 0.4); margin-top: 4px;")
        l.addWidget(last_act)
        
        return card

    def update_account_card(self, card, acc):
        # Update values
        total_val = card.findChild(QLabel, "AccTotal")
        if total_val: total_val.setText(format_isk(acc.get('total_isk', 0), short=True))
        
        roll_val = card.findChild(QLabel, "AccRoll")
        if roll_val: roll_val.setText(format_isk(acc.get('isk_per_hour', 0), short=True) + "/h")
        
        last_val = card.findChild(QLabel, "AccLast")
        if last_val:
            le = acc.get('last_event')
            if le:
                from datetime import datetime
                diff = (datetime.now() - le).total_seconds()
                if diff < 60:
                    time_str = f"HACE {int(diff)}s"
                elif diff < 3600:
                    time_str = f"HACE {int(diff/60)}m"
                else:
                    time_str = le.strftime('%H:%M:%S')
            else:
                time_str = "---"
            last_val.setText(f"ACTIVIDAD: {time_str}")
            
        status_dot = card.findChild(QLabel, "AccStatus")
        if status_dot:
            status = acc.get('status', 'idle')
            color = "#00ff9d" if status == 'active' else "#ffd700" if status == 'idle' else "#ff4444"
            status_dot.setStyleSheet(f"font-size: 14px; color: {color};")

    def set_tray_manager(self, tm):
        self.tray_manager = tm

    def _on_hud_clicked(self):
        if self.tray_manager:
            self.tray_manager._on_overlay()
            
    def _on_translator_clicked(self):
        if self.controller:
            # Lanzar el traductor real
            self.controller.start_translator()

    def _on_replicator_clicked(self):
        if self.tray_manager:
            self.tray_manager._on_replicator()

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(25)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container_lay = QVBoxLayout(container)
        container_lay.setContentsMargins(0, 0, 0, 0)
        container_lay.setSpacing(30)
        
        # Section 1
        g1, l1 = self.create_settings_group("TRACKER DE LOGS", "Configuración del motor de lectura.")
        l1.addWidget(QLabel("DIRECTORIO DE LOGS", styleSheet="font-family: 'Share Tech Mono'; color: #00c8ff; font-size: 10px; margin-top: 10px;"))
        ph = QHBoxLayout(); self.edit_log_dir = QLineEdit(); self.edit_log_dir.setPlaceholderText("Detección automática...")
        bb = QPushButton("EXAMINAR"); bb.clicked.connect(self._on_browse_logs); ph.addWidget(self.edit_log_dir); ph.addWidget(bb); l1.addLayout(ph)
        self.check_skip_logs = QCheckBox("Ignorar logs antiguos"); l1.addWidget(self.check_skip_logs)
        l1.addWidget(QLabel("RETENCIÓN ESS", styleSheet="font-family: 'Share Tech Mono'; color: #00c8ff; font-size: 10px;"))
        self.spin_ess_retention = QDoubleSpinBox(); self.spin_ess_retention.setRange(0, 1); self.spin_ess_retention.setValue(1); l1.addWidget(self.spin_ess_retention)
        c_l.addWidget(g1)
        
        # Section 2
        g2, l2 = self.create_settings_group("GENERAL", "Preferencias globales.")
        self.combo_lang = QComboBox(); self.combo_lang.addItems(["es", "en", "de", "fr", "ru", "zh"]); l2.addWidget(self.combo_lang); c_l.addWidget(g2)
        
        container_lay.addStretch()
        
        # Save Button
        btn_save = QPushButton("GUARDAR Y APLICAR CAMBIOS", objectName="SaveButton")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self.save_settings)
        container_lay.addWidget(btn_save)
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        return page

    def create_settings_group(self, title, subtitle):
        g = QFrame(); g.setStyleSheet("background: rgba(0, 20, 45, 0.3); border: 1px solid rgba(0, 180, 255, 0.1); border-radius: 8px; padding: 20px;")
        l = QVBoxLayout(g); t = QLabel(title); t.setStyleSheet("font-family: 'Orbitron'; font-size: 14px; color: #00c8ff; font-weight: bold; border: none;")
        s = QLabel(subtitle); s.setStyleSheet("font-family: 'Share Tech Mono'; font-size: 10px; color: rgba(200,230,255,0.4); border: none; margin-bottom: 10px;")
        l.addWidget(t); l.addWidget(s); return g, l

    def _on_browse_logs(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Seleccionar Directorio de Logs de EVE")
        if dir_path:
            self.edit_log_dir.setText(dir_path)

    def load_settings(self):
        settings = QSettings("EVE_iT", "Suite")
        self.edit_log_dir.setText(settings.value("log_dir", ""))
        self.check_skip_logs.setChecked(settings.value("skip_logs", "true") == "true")
        self.spin_ess_retention.setValue(float(settings.value("ess_retention", 1.0)))
        
        lang_idx = ["es", "en", "de", "fr", "ru", "zh"].index(settings.value("language", "es"))
        self.combo_lang.setCurrentIndex(lang_idx)

    def save_settings(self):
        settings = QSettings("EVE_iT", "Suite")
        log_dir = self.edit_log_dir.text()
        skip_logs = self.check_skip_logs.isChecked()
        ess = self.spin_ess_retention.value()
        
        langs = ["es", "en", "de", "fr", "ru", "zh"]
        lang = langs[self.combo_lang.currentIndex()]
        
        settings.setValue("log_dir", log_dir)
        settings.setValue("skip_logs", "true" if skip_logs else "false")
        settings.setValue("ess_retention", ess)
        settings.setValue("language", lang)
        
        # Apply language
        if self.controller:
            self.controller.state.update(language=lang)
            
        # Restart tracker if running
        if self.controller and self.controller.state.tracker_running:
            self.controller.start_tracker(
                log_dir=log_dir,
                skip_existing=skip_logs,
                ess_retention=ess
            )
            
        # UI Feedback
        self.section_title.setText("AJUSTES GUARDADOS")
        QTimer.singleShot(2000, lambda: self.section_title.setText("AJUSTES"))

    def create_nav_button(self, text, active=False):
        btn = QPushButton(text)
        btn.setProperty("class", "NavButton")
        btn.setProperty("active", str(active).lower())
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(50)
        return btn
        
    def create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        
        # 1. Top Metrics Row
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(15)
        
        card_isk = self.create_metric_card("ISK TOTAL", "0.00 ISK", "#00c8ff")
        self.val_total_isk = card_isk.findChild(QLabel, "MetricValue")
        
        card_h = self.create_metric_card("ISK / HORA", "0.00 ISK/h", "#00ff9d")
        self.val_isk_h = card_h.findChild(QLabel, "MetricValue")
        
        card_acc = self.create_metric_card("CUENTAS", "0 ACTIVAS", "#ffffff")
        self.val_accounts = card_acc.findChild(QLabel, "MetricValue")
        
        metrics_layout.addWidget(card_isk)
        metrics_layout.addWidget(card_h)
        metrics_layout.addWidget(card_acc)
        
        layout.addLayout(metrics_layout)
        
        # 2. Accounts Section (Scrollable)
        acc_title = QLabel("CUENTAS ACTIVAS")
        acc_title.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(255,255,255,0.4); font-size: 12px; letter-spacing: 2px;")
        layout.addWidget(acc_title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self.accounts_layout = QGridLayout(scroll_content)
        self.accounts_layout.setContentsMargins(0, 0, 0, 0)
        self.accounts_layout.setSpacing(10)
        
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1) # This takes most space
        
        # 3. Tools Footer Section (Compact)
        tools_label = QLabel("ACCESO RÁPIDO")
        tools_label.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(255,255,255,0.2); font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(tools_label)
        
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(10)
        
        self.card_hud = self.create_tool_card_compact("HUD", "🕹️")
        self.card_hud.mousePressEvent = lambda e: self._on_hud_clicked()
        
        self.card_trans = self.create_tool_card_compact("TRADUCTOR", "🌐")
        self.card_trans.mousePressEvent = lambda e: self._on_translator_clicked()
        
        self.card_repl = self.create_tool_card_compact("REPLICADOR", "🪟")
        self.card_repl.mousePressEvent = lambda e: self._on_replicator_clicked()
        
        tools_layout.addWidget(self.card_hud)
        tools_layout.addWidget(self.card_trans)
        tools_layout.addWidget(self.card_repl)
        tools_layout.addStretch()
        
        layout.addLayout(tools_layout)
        
        # Status Footer
        footer = QLabel("EVE iT ENGINE OK | SYSTEM: WINDOWS | SYNC: LIVE")
        footer.setStyleSheet("font-family: 'Share Tech Mono'; color: rgba(0, 200, 255, 0.2); font-size: 9px; margin-top: 5px;")
        layout.addWidget(footer)
        
        return page

    def create_tool_card_compact(self, title, icon):
        card = QFrame()
        card.setObjectName("ToolCard")
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(160, 50)
        card.setStyleSheet("""
            QFrame#ToolCard {
                background-color: rgba(0, 180, 255, 0.05);
                border: 1px solid rgba(0, 180, 255, 0.1);
                border-radius: 4px;
            }
            QFrame#ToolCard:hover {
                background-color: rgba(0, 180, 255, 0.15);
                border-color: rgba(0, 180, 255, 0.4);
            }
        """)
        
        l = QHBoxLayout(card)
        l.setContentsMargins(10, 0, 10, 0)
        
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 16px;")
        
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-family: 'Orbitron'; font-size: 11px; color: #ffffff;")
        
        l.addWidget(icon_lbl)
        l.addWidget(title_lbl)
        l.addStretch()
        
        return card
        
    def create_metric_card(self, label, value, color):
        card = QFrame()
        card.setProperty("class", "MetricCard")
        l = QVBoxLayout(card)
        
        lbl = QLabel(label)
        lbl.setProperty("class", "MetricLabel")
        
        val = QLabel(value)
        val.setObjectName("MetricValue") # Usar objectName para búsqueda
        val.setProperty("class", "MetricValue")
        val.setStyleSheet(f"color: {color};")
        
        l.addWidget(lbl)
        l.addWidget(val)
        return card
        
    def apply_styles(self):
        self.setStyleSheet(MAIN_STYLE)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainSuiteWindow()
    window.show()
    sys.exit(app.exec())
