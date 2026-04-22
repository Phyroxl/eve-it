"""
ui/desktop/styles.py — Sistema de Diseño "Tactical Deep-Space".
Unificación total con la atmósfera de EVE Online.
"""

MAIN_STYLE = """
/* BASE: DEEP SPACE ATMOSPHERE */
QMainWindow, QWidget#CentralWidget {
    background-color: #020408;
    color: #b0c4de;
}

/* SIDEBAR: INTEGRATED COMMAND BRIDGE */
QFrame#NavBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #05080f, stop:1 #080b14);
    border-right: 1px solid rgba(0, 200, 255, 0.15);
}

QLabel#LogoLabel {
    font-family: 'Orbitron';
    font-size: 20px;
    font-weight: 900;
    color: #00c8ff;
    padding: 30px 20px;
    letter-spacing: 5px;
    background: transparent;
}

QPushButton.NavButton {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: rgba(0, 180, 255, 0.4);
    font-family: 'Share Tech Mono';
    font-size: 10px;
    text-align: left;
    padding-left: 20px;
    height: 48px;
    text-transform: uppercase;
    letter-spacing: 2px;
}

QPushButton.NavButton:hover {
    background: rgba(0, 200, 255, 0.05);
    color: #00c8ff;
}

QPushButton.NavButton[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(0, 200, 255, 0.12), stop:1 transparent);
    color: #ffffff;
    border-left: 3px solid #00c8ff;
}

/* CONTENT AREA: TACTICAL TERMINAL */
QFrame#ContentFrame {
    background-color: #020408;
}

QLabel#SectionTitle {
    font-family: 'Orbitron';
    font-size: 15px;
    font-weight: bold;
    color: #00c8ff;
    letter-spacing: 3px;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(0, 200, 255, 0.1);
    padding-bottom: 5px;
}

/* CHARACTER MODULES: INDUSTRIAL TELEMETRY */
QFrame#CharacterCard {
    background: #080b14;
    border: 1px solid rgba(0, 200, 255, 0.1);
    border-radius: 2px;
}

QFrame#CharacterCard:hover {
    background: #0d121d;
    border-color: rgba(0, 200, 255, 0.6);
}

QLabel#CharName {
    font-family: 'Orbitron';
    font-size: 13px;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: 1px;
}

QLabel#CharAvatar {
    background-color: #05080f;
    color: #ffd700;
    border: 1px solid rgba(255, 215, 0, 0.2);
    font-family: 'Orbitron';
    font-size: 22px;
    font-weight: bold;
}

/* METRICS: AMBER & NEON */
QLabel#GlowValue {
    font-family: 'Share Tech Mono';
    font-size: 26px;
    font-weight: bold;
    color: #ffd700;
}

QLabel#GlowValueGreen {
    font-family: 'Share Tech Mono';
    font-size: 26px;
    font-weight: bold;
    color: #00ff9d;
}

/* ANALYTIC BOXES: CONSOLE BLOCKS */
QFrame#AnalyticBox {
    background: #05080f;
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-top: 2px solid rgba(0, 180, 255, 0.2);
}

QLabel#AnalyticVal {
    font-family: 'Share Tech Mono';
    font-size: 17px;
    color: #ffffff;
}

/* SETTINGS: SYSTEM OVERRIDE */
QFrame#SettingsGroup {
    background: #05080f;
    border: 1px solid rgba(0, 180, 255, 0.05);
    border-left: 4px solid #00c8ff;
    padding: 15px;
}

QLineEdit, QDoubleSpinBox, QComboBox {
    background-color: #020408;
    border: 1px solid rgba(0, 180, 255, 0.2);
    color: #00c8ff;
    font-family: 'Share Tech Mono';
    padding: 5px;
}

QComboBox::drop-down { border: none; }

QPushButton#SaveButton {
    background: rgba(0, 200, 255, 0.08);
    border: 1px solid #00c8ff;
    color: #00c8ff;
    font-family: 'Orbitron';
    font-weight: bold;
    letter-spacing: 2px;
    height: 42px;
}

QPushButton#SaveButton:hover {
    background: #00c8ff;
    color: #000000;
}

QPushButton#BackButton {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.4);
    font-family: 'Share Tech Mono';
    font-size: 9px;
    padding: 5px 15px;
}

QPushButton#BackButton:hover {
    border-color: #00c8ff;
    color: #00c8ff;
}

/* SCROLLBARS: MINIMALIST TECH */
QScrollBar:vertical {
    border: none;
    background: #020408;
    width: 6px;
}
QScrollBar::handle:vertical {
    background: rgba(0, 200, 255, 0.15);
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #00c8ff;
}
"""
