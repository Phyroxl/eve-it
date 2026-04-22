"""
ui/desktop/styles.py — Sistema de Diseño Sobrio y Profesional.
Enfoque: Legibilidad, Jerarquía y Estabilidad.
"""

MAIN_STYLE = """
/* BASE: DARK THEME PROFESSIONAL */
QMainWindow, QWidget#CentralWidget {
    background-color: #0f1115;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif;
}

/* SIDEBAR: CLEAN & NAVIGATION-FOCUSED */
QFrame#NavBar {
    background-color: #161a1f;
    border-right: 1px solid #2d3748;
}

QLabel#LogoLabel {
    font-size: 18px;
    font-weight: 700;
    color: #3182ce;
    padding: 24px 20px;
    background: transparent;
}

QPushButton.NavButton {
    background: transparent;
    border: none;
    color: #a0aec0;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
    padding-left: 20px;
    height: 44px;
}

QPushButton.NavButton:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #edf2f7;
}

QPushButton.NavButton[active="true"] {
    background: rgba(49, 130, 206, 0.1);
    color: #63b3ed;
    border-right: 3px solid #3182ce;
}

/* CONTENT AREA */
QFrame#ContentFrame {
    background-color: #0f1115;
}

QLabel#SectionTitle {
    font-size: 20px;
    font-weight: 600;
    color: #f7fafc;
    padding-bottom: 10px;
    margin-bottom: 20px;
}

/* CHARACTER CARDS: CLEAN & PROPORTIONAL */
QFrame#CharacterCard {
    background-color: #1a202c;
    border: 1px solid #2d3748;
    border-radius: 8px;
}

QFrame#CharacterCard:hover {
    border-color: #4a5568;
    background-color: #232a37;
}

QLabel#CharName {
    font-size: 14px;
    font-weight: 600;
    color: #f7fafc;
}

QLabel#CharAvatar {
    background-color: #2d3748;
    color: #63b3ed;
    border-radius: 4px;
    font-size: 16px;
    font-weight: 600;
}

/* METRICS & VALUES */
QLabel#IskValue {
    font-size: 15px;
    font-weight: 600;
    color: #ecc94b;
}

QLabel#MetricLabel {
    color: #718096;
    font-size: 11px;
    font-weight: 500;
}

/* ANALYTIC BOXES */
QFrame#AnalyticBox {
    background-color: #1a202c;
    border: 1px solid #2d3748;
    border-radius: 6px;
    padding: 12px;
}

QLabel#AnalyticVal {
    font-size: 18px;
    font-weight: 600;
    color: #ffffff;
}

/* SETTINGS & INPUTS */
QFrame#SettingsGroup {
    background-color: #161a1f;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 20px;
}

QLineEdit, QDoubleSpinBox, QComboBox {
    background-color: #0f1115;
    border: 1px solid #4a5568;
    color: #e2e8f0;
    padding: 8px;
    border-radius: 4px;
    font-size: 13px;
}

QLineEdit:focus, QComboBox:focus {
    border-color: #3182ce;
}

QPushButton#SaveButton {
    background-color: #3182ce;
    border: none;
    color: white;
    font-size: 14px;
    font-weight: 600;
    height: 40px;
    border-radius: 4px;
}

QPushButton#SaveButton:hover {
    background-color: #2b6cb0;
}

QPushButton#BackButton {
    background-color: transparent;
    border: 1px solid #4a5568;
    color: #a0aec0;
    font-size: 12px;
    padding: 6px 12px;
    border-radius: 4px;
}

QPushButton#BackButton:hover {
    color: #ffffff;
    border-color: #cbd5e0;
}

/* SCROLLBARS */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #2d3748;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #4a5568;
}
"""
