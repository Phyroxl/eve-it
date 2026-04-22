"""
ui/desktop/styles.py — Sistema de Diseño Sobrio y Profesional.
Enfoque: Legibilidad, Jerarquía y Estabilidad.
"""

MAIN_STYLE = """
/* BASE: DARK THEME PROFESSIONAL - COMPACT & POLISHED */
QMainWindow, QWidget#CentralWidget {
    background-color: #0d0f12;
    color: #cbd5e0;
    font-family: 'Segoe UI', 'Inter', sans-serif;
}

/* SIDEBAR: TECHNICAL & INTEGRATED */
QFrame#NavBar {
    background-color: #12151a;
    border-right: 1px solid #1e242c;
}

QLabel#LogoLabel {
    font-size: 14px;
    font-weight: 800;
    color: #3182ce;
    padding: 20px 12px;
    letter-spacing: 2px;
    border-bottom: 1px solid #1e242c;
    margin-bottom: 10px;
}

QPushButton.NavButton {
    background: transparent;
    border: none;
    color: #4a5568;
    font-size: 10px;
    font-weight: 700;
    text-align: left;
    padding-left: 20px;
    height: 36px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QPushButton.NavButton:hover {
    color: #a0aec0;
    background: rgba(255, 255, 255, 0.02);
}

QPushButton.NavButton[active="true"] {
    color: #63b3ed;
    background: linear-gradient(to right, rgba(49, 130, 206, 0.1), transparent);
    border-left: 3px solid #3182ce;
}

/* CONTENT AREA */
QFrame#ContentFrame {
    background-color: #0d0f12;
}

QLabel#SectionTitle {
    font-size: 15px;
    font-weight: 800;
    color: #edf2f7;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding-bottom: 4px;
}

/* CARDS: MODULAR & TECHNICAL */
QFrame#CharacterCard {
    background-color: #161a20;
    border: 1px solid #232931;
    border-radius: 4px;
}

QFrame#CharacterCard:hover {
    border-color: #3182ce;
    background-color: #1c222b;
}

QLabel#CharName {
    font-size: 11px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.5px;
}

QLabel#CharAvatar {
    background-color: #1e242c;
    color: #63b3ed;
    border: 1px solid #2d3748;
    border-radius: 2px;
    font-size: 12px;
    font-weight: 800;
}

/* METRICS */
QLabel#IskValue {
    font-size: 14px;
    font-weight: 800;
    color: #ecc94b;
}

QLabel#MetricLabel {
    color: #4a5568;
    font-size: 8px;
    font-weight: 800;
    text-transform: uppercase;
}

/* ANALYTIC BLOCKS */
QFrame#AnalyticBox {
    background-color: #12151a;
    border: 1px solid #1e242c;
    border-radius: 3px;
}

QLabel#AnalyticVal {
    font-size: 14px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.5px;
}

/* MODULE HEADERS */
QLabel#ModuleHeader {
    color: #2b6cb0;
    font-size: 9px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}

/* INPUTS */
QLineEdit, QComboBox {
    background-color: #0d0f12;
    border: 1px solid #2d3748;
    color: #a0aec0;
    padding: 4px 8px;
    border-radius: 2px;
    font-size: 10px;
}

QLineEdit:focus {
    border-color: #3182ce;
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
