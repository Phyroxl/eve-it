import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QPushButton, QFrame, QLabel
from PySide6.QtCore import Qt
from ui.market_command.simple_view import MarketSimpleView
from ui.market_command.performance_view import MarketPerformanceView
from ui.market_command.my_orders_view import MarketMyOrdersView
from ui.market_command.contracts_view import MarketContractsView
from ui.common.theme import Theme

_log = logging.getLogger('eve.market_command')

# [MARKET COMMAND] Advanced Mode Enabled: False
# [MARKET COMMAND] Tabs: Simple, Performance, My Orders, Contracts

class MarketCommandMain(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._views = {0: None, 1: None, 2: None, 3: None}
        self._view_classes = {
            0: MarketSimpleView,
            1: MarketPerformanceView,
            2: MarketMyOrdersView,
            3: MarketContractsView,
        }
        self._view_names = {
            0: "Modo Simple",
            1: "Performance",
            2: "Mis Pedidos",
            3: "Contratos",
        }

        self.setObjectName("MarketCommandRoot")
        self.setup_ui()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self.try_auto_restore)

    def setup_ui(self):
        try:
            self.setStyleSheet(Theme.get_qss())
        except Exception as e:
            _log.exception(f"[THEME] Failed to apply Market Command theme: {e}")
            self.setStyleSheet("")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 1. Navigation Header
        self.nav_frame = QFrame()
        self.nav_frame.setObjectName("NavBar")
        self.nav_frame.setFixedHeight(45)
        nav_layout = QHBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(20, 0, 20, 0)
        nav_layout.setSpacing(10)

        self.btn_simple = self.create_tab_button("MODO SIMPLE", True)
        self.btn_performance = self.create_tab_button("PERFORMANCE")
        self.btn_my_orders = self.create_tab_button("MIS PEDIDOS")
        self.btn_contracts = self.create_tab_button("CONTRATOS")

        self.btn_simple.clicked.connect(lambda: self.switch_view(0))
        self.btn_performance.clicked.connect(lambda: self.switch_view(1))
        self.btn_my_orders.clicked.connect(lambda: self.switch_view(2))
        self.btn_contracts.clicked.connect(lambda: self.switch_view(3))

        nav_layout.addWidget(self.btn_simple)
        nav_layout.addWidget(self.btn_performance)
        nav_layout.addWidget(self.btn_my_orders)
        nav_layout.addWidget(self.btn_contracts)
        nav_layout.addStretch()

        # SSO Section
        self.btn_sso = QPushButton("VINCULAR PERSONAJE")
        self.btn_sso.setCursor(Qt.PointingHandCursor)
        self.btn_sso.setObjectName("SecondaryButton")
        from core.auth_manager import AuthManager
        self.btn_sso.clicked.connect(AuthManager.instance().login)
        AuthManager.instance().authenticated.connect(self.on_auth_success)

        nav_layout.addWidget(self.btn_sso)

        # Status Label inside Nav
        self.lbl_mode = QLabel("ANÁLISIS OPERATIVO")
        self.lbl_mode.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800; letter-spacing: 1px;")
        nav_layout.addWidget(self.lbl_mode)

        self.layout.addWidget(self.nav_frame)

        # 2. Stacked Widget con Lazy Loading
        self.stack = QStackedWidget()

        for i in range(4):
            placeholder = QWidget()
            placeholder.setLayout(QVBoxLayout())
            placeholder.layout().addWidget(QLabel(f"Cargando {self._view_names[i]}...", alignment=Qt.AlignCenter))
            self.stack.addWidget(placeholder)

        self._ensure_view_loaded(0)
        # After insert/remove the stack may drift; force index 0
        self.stack.setCurrentIndex(0)

        self.layout.addWidget(self.stack)

    def on_auth_success(self, char_name, tokens):
        self.btn_sso.setText(f"● {char_name.upper()}")
        self.btn_sso.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.1);
                color: #10b981;
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 4px;
                font-size: 8px;
                font-weight: 800;
                padding: 4px 10px;
            }
        """)

    def create_tab_button(self, text, active=False):
        btn = QPushButton(text)
        btn.setObjectName("TabButton")
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(45)
        self.update_btn_style(btn, active)
        return btn

    def update_btn_style(self, btn, active):
        btn.setProperty("active", "true" if active else "false")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _ensure_view_loaded(self, index):
        if self._views[index] is not None:
            return self._views[index]

        import time
        start_t = time.perf_counter()

        cls = self._view_classes[index]
        name = self._view_names[index]

        try:
            if cls == MarketPerformanceView:
                view = MarketPerformanceView(defer_initial_refresh=True)
            else:
                view = cls()
        except Exception as e:
            _log.error(f"Error cargando vista {name}: {e}", exc_info=True)
            view = QWidget()
            err_layout = QVBoxLayout(view)
            err_lbl = QLabel(f"❌ Error al cargar {name}\n\n{str(e)}")
            err_lbl.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 800;")
            err_lbl.setAlignment(Qt.AlignCenter)
            err_layout.addWidget(err_lbl)

            retry_btn = QPushButton("REINTENTAR CARGA")
            retry_btn.setFixedWidth(200)
            retry_btn.setStyleSheet("background: #1e293b; color: #f1f5f9; padding: 10px; border-radius: 4px;")
            retry_btn.clicked.connect(lambda: self.switch_view(index))
            err_layout.addWidget(retry_btn, 0, Qt.AlignCenter)

            placeholder = self.stack.widget(index)
            self.stack.removeWidget(placeholder)
            self.stack.insertWidget(index, view)
            placeholder.deleteLater()
            return view

        self._views[index] = view

        placeholder = self.stack.widget(index)
        self.stack.removeWidget(placeholder)
        self.stack.insertWidget(index, view)
        placeholder.deleteLater()

        end_t = time.perf_counter()
        ms = (end_t - start_t) * 1000
        print(f"[UI PERF] Loaded view {name} (index {index}) in {ms:.2f} ms")

        return view

    def switch_view(self, index):
        import time
        start_t = time.perf_counter()

        view = self._ensure_view_loaded(index)
        self.stack.setCurrentIndex(index)

        from PySide6.QtCore import QTimer
        if hasattr(view, 'activate_view'):
            t_act_start = time.perf_counter()
            QTimer.singleShot(0, view.activate_view)
            t_act_end = time.perf_counter()
            _log.info(f"[UI PERF] activate_view scheduled for {self._view_names[index]} in {(t_act_end - t_act_start)*1000:.4f} ms")

        end_t = time.perf_counter()
        ms = (end_t - start_t) * 1000
        _log.info(f"[UI PERF] Switched to index {index} ({self._view_names[index]}) in {ms:.2f} ms")

        self.btn_simple.setChecked(index == 0)
        self.btn_performance.setChecked(index == 1)
        self.btn_my_orders.setChecked(index == 2)
        self.btn_contracts.setChecked(index == 3)
        self.update_btn_style(self.btn_simple, index == 0)
        self.update_btn_style(self.btn_performance, index == 1)
        self.update_btn_style(self.btn_my_orders, index == 2)
        self.update_btn_style(self.btn_contracts, index == 3)

        mode_labels = {
            0: "ANÁLISIS OPERATIVO",
            1: "RENDIMIENTO REAL",
            2: "POSICIONES ABIERTAS",
            3: "ARBITRAJE DE CONTRATOS",
        }
        self.lbl_mode.setText(mode_labels.get(index, ""))

        end_t = time.perf_counter()
        ms = (end_t - start_t) * 1000
        if ms > 5:
            print(f"[UI PERF] Switched to index {index} in {ms:.2f} ms")

    def try_auto_restore(self):
        from core.auth_manager import AuthManager
        auth = AuthManager.instance()
        if auth.current_token:
            self.on_auth_success(auth.char_name, {})
        else:
            res = auth.try_restore_session()
            if res == "ok":
                self.on_auth_success(auth.char_name, {})
