"""
ui/desktop/styles.py — Sistema de Diseño Táctico (ADN HUD Unificado).
"""

MAIN_STYLE = """
/* BASE TÁCTICA */
QMainWindow, QWidget#CentralWidget, QFrame#ContentFrame, QFrame#DetailView {
    background-color: #000000;
    color: #e0f0ff;
}

/* SIDEBAR / CONTROL PANEL */
QFrame#NavBar {
    background-color: #050505;
    border-right: 1px solid rgba(0, 180, 255, 0.15);
}

QLabel#LogoLabel {
    font-family: 'Orbitron';
    font-size: 22px;
    font-weight: 900;
    color: #00c8ff;
    padding: 35px 25px;
    letter-spacing: 4px;
}

/* BOTONES DE NAVEGACIÓN (ESTILO HUD) */
QPushButton.NavButton {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: rgba(0, 180, 255, 0.4);
    font-family: 'Share Tech Mono';
    font-size: 11px;
    text-align: left;
    padding-left: 25px;
    height: 50px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

QPushButton.NavButton:hover {
    background: rgba(0, 180, 255, 0.05);
    color: #00c8ff;
}

QPushButton.NavButton[active="true"] {
    background: rgba(0, 180, 255, 0.1);
    color: #00c8ff;
    border-left: 3px solid #00c8ff;
    font-weight: bold;
}

/* TÍTULOS DE SECCIÓN */
QLabel#SectionTitle {
    font-family: 'Orbitron';
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
    letter-spacing: 2px;
    text-transform: uppercase;
}

/* TARJETAS DE PERSONAJE / HERRAMIENTAS (DISEÑO INDUSTRIAL) */
QFrame#CharacterCard {
    background: #0a0a0a;
    border: 1px solid rgba(0, 180, 255, 0.2);
    border-radius: 2px;
}

QFrame#CharacterCard:hover {
    background: #0d0d0d;
    border-color: #00c8ff;
}

QLabel#CharName {
    font-family: 'Share Tech Mono';
    font-size: 14px;
    font-weight: bold;
    color: #00c8ff;
}

QLabel#CharAvatar {
    background-color: #111111;
    color: #ffd700;
    border: 1px solid rgba(255, 215, 0, 0.3);
    border-radius: 0px;
    font-family: 'Orbitron';
    font-size: 24px;
}

/* MÉTRICAS GLOW (ESTILO HUD) */
QLabel#GlowValue {
    font-family: 'Orbitron';
    font-size: 24px;
    font-weight: bold;
    color: #ffd700;
}

QLabel#GlowValueGreen {
    font-family: 'Orbitron';
    font-size: 24px;
    font-weight: bold;
    color: #00ff9d;
}

/* CAJAS ANALÍTICAS */
QFrame#AnalyticBox {
    background: #080808;
    border: 1px solid rgba(0, 180, 255, 0.1);
    border-radius: 0px;
}

QLabel#AnalyticVal {
    font-family: 'Share Tech Mono';
    font-size: 18px;
    color: #ffffff;
}

/* SETTINGS & COMPONENTES */
QFrame#SettingsGroup {
    background: #050505;
    border: 1px solid rgba(0, 180, 255, 0.1);
    border-left: 4px solid #00c8ff;
    padding: 15px;
}

QLineEdit, QDoubleSpinBox, QComboBox {
    background-color: #0a0a0a;
    border: 1px solid rgba(0, 180, 255, 0.2);
    color: #00c8ff;
    font-family: 'Share Tech Mono';
    padding: 6px;
}

QPushButton#SaveButton {
    background: rgba(0, 200, 255, 0.1);
    border: 1px solid #00c8ff;
    color: #00c8ff;
    font-family: 'Orbitron';
    font-weight: bold;
    height: 40px;
    text-transform: uppercase;
}

QPushButton#SaveButton:hover {
    background: rgba(0, 200, 255, 0.2);
}

QPushButton#BackButton {
    background: transparent;
    border: 1px solid rgba(0, 180, 255, 0.3);
    color: #00c8ff;
    font-family: 'Share Tech Mono';
    font-size: 10px;
}

QScrollArea {
    border: none;
    background: transparent;
}
"""
