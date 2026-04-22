"""
ui/desktop/styles.py — Sistema de Diseño Sobrio y Profesional.
Enfoque: Legibilidad, Jerarquía y Estabilidad.
"""

MAIN_STYLE = """
/* BASE: DARK THEME PROFESSIONAL - FINAL POLISH */
QMainWindow, QWidget#CentralWidget {
    background-color: #0b0d0f;
    color: #cbd5e0;
    font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
}

/* SIDEBAR: ELEGANT & COMPACT */
QFrame#NavBar {
    background-color: #0f1216;
    border-right: 1px solid #1a1e23;
}

QLabel#LogoLabel {
    font-size: 13px;
    font-weight: 800;
    color: #3182ce;
    padding: 22px 12px;
    letter-spacing: 2.5px;
    border-bottom: 1px solid #1a1e23;
    margin-bottom: 8px;
}

QPushButton.NavButton {
    background: transparent;
    border: none;
    color: #5a6779;
    font-size: 10px;
    font-weight: 700;
    text-align: left;
    padding-left: 20px;
    height: 38px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

QPushButton.NavButton:hover {
    color: #94a3b8;
    background: rgba(255, 255, 255, 0.02);
}

QPushButton.NavButton[active="true"] {
    color: #60a5fa;
    background: linear-gradient(to right, rgba(37, 99, 235, 0.1), transparent);
    border-left: 3px solid #2563eb;
}

/* CONTENT AREA */
QFrame#ContentFrame {
    background-color: #0b0d0f;
}

QLabel#SectionTitle {
    font-size: 14px;
    font-weight: 800;
    color: #f8fafc;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    padding-bottom: 2px;
}

/* CARDS: REFINED MODULES */
QFrame#CharacterCard {
    background-color: #13171c;
    border: 1px solid #1e242c;
    border-radius: 3px;
}

QFrame#CharacterCard:hover {
    border-color: #2563eb;
    background-color: #171d24;
}

QLabel#CharName {
    font-size: 10px;
    font-weight: 800;
    color: #f1f5f9;
    letter-spacing: 0.6px;
}

QLabel#CharAvatar {
    background-color: #1a1e23;
    color: #60a5fa;
    border: 1px solid #2d3748;
    border-radius: 2px;
    font-size: 11px;
    font-weight: 800;
}

/* METRICS */
QLabel#IskValue {
    font-size: 13px;
    font-weight: 800;
    color: #fbbf24;
}

QLabel#MetricLabel {
    color: #64748b;
    font-size: 8px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* TECHNICAL BLOCKS */
QFrame#AnalyticBox {
    background-color: #0f1216;
    border: 1px solid #1a1e23;
    border-radius: 2px;
}

QLabel#AnalyticVal {
    font-size: 13px;
    font-weight: 800;
    color: #f8fafc;
    letter-spacing: 0.5px;
}

/* MODULE HEADERS: UNIFIED */
QLabel#ModuleHeader {
    color: #3b82f6;
    font-size: 9px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 2px;
    padding: 2px 0;
}

/* INPUTS & SETTINGS */
QFrame#SettingsGroup {
    background-color: #0f1216;
    border: 1px solid #1a1e23;
    border-radius: 4px;
    padding: 10px;
}

QLineEdit, QComboBox {
    background-color: #0b0d0f;
    border: 1px solid #1e242c;
    color: #94a3b8;
    padding: 6px 10px;
    border-radius: 2px;
    font-size: 10px;
}

QLineEdit:focus {
    border-color: #2563eb;
    color: #cbd5e0;
}

QCheckBox {
    color: #94a3b8;
    font-size: 10px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    background-color: #0b0d0f;
    border: 1px solid #1e242c;
    border-radius: 2px;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #3b82f6;
}

QPushButton#SaveButton {
    background-color: #2563eb;
    color: white;
    border: none;
    border-radius: 2px;
    font-weight: 800;
    font-size: 11px;
    padding: 8px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

QPushButton#SaveButton:hover {
    background-color: #3b82f6;
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
