"""
ui/desktop/styles.py — Sistema de Diseño "Tactical Deep-Space".
Unificación total con la atmósfera de EVE Online.
"""

MAIN_STYLE = """
/* BASE: DEEP SPACE ATMOSPHERE */
QMainWindow, QWidget#CentralWidget {
    background-color: #010205; /* Deeper black */
    color: #b0c4de;
}

/* SIDEBAR: INTEGRATED COMMAND BRIDGE */
QFrame#NavBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #05080f, stop:1 #080b14);
    border-right: 1px solid rgba(0, 200, 255, 0.1);
}

QLabel#LogoLabel {
    font-family: 'Orbitron';
    font-size: 20px;
    font-weight: 900;
    color: #00c8ff;
    padding: 30px 20px;
    letter-spacing: 5px;
    background: transparent;
    /* Glow effect */
    text-shadow: 0 0 10px rgba(0, 200, 255, 0.5);
}

QPushButton.NavButton {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: rgba(0, 180, 255, 0.3);
    font-family: 'Share Tech Mono';
    font-size: 10px;
    text-align: left;
    padding-left: 20px;
    height: 52px;
    text-transform: uppercase;
    letter-spacing: 2px;
    transition: all 0.2s ease;
}

QPushButton.NavButton:hover {
    background: rgba(0, 200, 255, 0.03);
    color: #00c8ff;
}

QPushButton.NavButton[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(0, 200, 255, 0.1), stop:1 transparent);
    color: #ffffff;
    border-left: 3px solid #00c8ff;
}

/* CONTENT AREA: TACTICAL TERMINAL */
QFrame#ContentFrame {
    background-color: #010205;
}

QLabel#SectionTitle {
    font-family: 'Orbitron';
    font-size: 14px;
    font-weight: bold;
    color: #00c8ff;
    letter-spacing: 4px;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(0, 200, 255, 0.1);
    padding-bottom: 8px;
    margin-bottom: 10px;
}

/* CHARACTER MODULES: INDUSTRIAL TELEMETRY */
QFrame#CharacterCard {
    background: rgba(13, 18, 29, 0.6); /* Glassmorphism */
    border: 1px solid rgba(0, 200, 255, 0.1);
    border-radius: 4px;
}

QFrame#CharacterCard:hover {
    background: rgba(20, 28, 45, 0.8);
    border-color: rgba(0, 200, 255, 0.5);
}

QLabel#CharName {
    font-family: 'Orbitron';
    font-size: 13px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 1px;
}

QLabel#CharAvatar {
    background-color: #05080f;
    color: #ffd700;
    border: 1px solid rgba(255, 215, 0, 0.15);
    font-family: 'Orbitron';
    font-size: 20px;
    font-weight: bold;
    border-radius: 2px;
}

/* METRICS: AMBER & NEON GLOW */
QLabel#GlowValue {
    font-family: 'Share Tech Mono';
    font-size: 24px;
    font-weight: bold;
    color: #ffd700;
}

QLabel#GlowValueGreen {
    font-family: 'Share Tech Mono';
    font-size: 24px;
    font-weight: bold;
    color: #00ff9d;
}

/* ANALYTIC BOXES: CONSOLE BLOCKS */
QFrame#AnalyticBox {
    background: rgba(5, 8, 15, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.02);
    border-top: 2px solid rgba(0, 180, 255, 0.15);
}

QLabel#AnalyticVal {
    font-family: 'Share Tech Mono';
    font-size: 16px;
    color: #ffffff;
}

/* SETTINGS: SYSTEM OVERRIDE */
QFrame#SettingsGroup {
    background: rgba(5, 8, 15, 0.4);
    border: 1px solid rgba(0, 180, 255, 0.05);
    border-left: 3px solid #00c8ff;
    padding: 15px;
}

QLineEdit, QDoubleSpinBox, QComboBox {
    background-color: rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(0, 180, 255, 0.1);
    color: #00c8ff;
    font-family: 'Share Tech Mono';
    padding: 6px;
    border-radius: 2px;
}

QComboBox::drop-down { border: none; }

QPushButton#SaveButton {
    background: rgba(0, 200, 255, 0.05);
    border: 1px solid rgba(0, 200, 255, 0.4);
    color: #00c8ff;
    font-family: 'Orbitron';
    font-weight: bold;
    letter-spacing: 2px;
    height: 44px;
    border-radius: 2px;
}

QPushButton#SaveButton:hover {
    background: rgba(0, 200, 255, 0.15);
    border-color: #00c8ff;
    color: #ffffff;
}

QPushButton#BackButton {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.3);
    font-family: 'Share Tech Mono';
    font-size: 9px;
    padding: 6px 18px;
}

QPushButton#BackButton:hover {
    border-color: #00c8ff;
    color: #00c8ff;
}

/* SCROLLBARS: MINIMALIST TECH */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(0, 200, 255, 0.1);
    min-height: 30px;
    border-radius: 2px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(0, 200, 255, 0.3);
}

"""
