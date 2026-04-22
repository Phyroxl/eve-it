"""
ui/desktop/styles.py — Design system for EVE iT Desktop Suite.
"""

MAIN_STYLE = """
QMainWindow {
    background-color: #030810;
    color: #ffffff;
}

QWidget#CentralWidget {
    background-color: #030810;
}

/* Sidebar / Navigation */
QFrame#NavBar {
    background-color: #02060c;
    border-right: 1px solid rgba(255, 255, 255, 0.03);
    min-width: 200px;
    max-width: 200px;
}

QLabel#LogoLabel {
    font-family: 'Orbitron';
    font-size: 20px;
    font-weight: 900;
    color: #00c8ff;
    padding: 30px 20px;
    letter-spacing: 3px;
}

QPushButton.NavButton {
    background-color: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.4);
    text-align: left;
    padding: 15px 25px;
    font-family: 'Orbitron';
    font-size: 11px;
    letter-spacing: 1px;
}

QPushButton.NavButton:hover {
    color: #ffffff;
    background-color: rgba(0, 200, 255, 0.05);
}

QPushButton.NavButton[active="true"] {
    color: #00c8ff;
    background-color: rgba(0, 200, 255, 0.08);
    border-left: 3px solid #00c8ff;
}

/* Content Area */
QFrame#ContentFrame {
    background-color: #030810;
}

QLabel#SectionTitle {
    font-family: 'Orbitron';
    font-size: 18px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 1px;
    margin-bottom: 5px;
}

/* Character Cards */
QFrame#CharacterCard {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 10px;
}

QFrame#CharacterCard:hover {
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(0, 180, 255, 0.2);
}

QLabel#CharName {
    font-family: 'Orbitron';
    font-size: 13px;
    font-weight: bold;
    color: #ffffff;
}

QLabel#CharAvatar {
    background-color: rgba(0, 180, 255, 0.1);
    color: #00c8ff;
    border-radius: 35px;
    font-family: 'Orbitron';
    font-size: 24px;
    font-weight: bold;
}

/* Character Detail View */
QFrame#DetailView {
    background-color: #030810;
}

QLabel#DetailTitle {
    font-family: 'Orbitron';
    font-size: 26px;
    font-weight: bold;
    color: #ffffff;
    letter-spacing: 1px;
}

/* Glowing Metrics */
QLabel#GlowValue {
    font-family: 'Share Tech Mono';
    font-size: 28px;
    font-weight: bold;
    color: #ffd700;
}

QLabel#GlowValueGreen {
    font-family: 'Share Tech Mono';
    font-size: 28px;
    font-weight: bold;
    color: #00ff9d;
}

/* Analytics Grid */
QFrame#AnalyticBox {
    background: rgba(255, 255, 255, 0.02);
    border: 1 solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    padding: 12px;
}

QFrame#AnalyticBox:hover {
    border-color: rgba(0, 180, 255, 0.15);
}

/* Empty States */
QLabel#EmptyStateText {
    color: rgba(255, 255, 255, 0.1);
    font-family: 'Share Tech Mono';
    font-size: 11px;
    font-style: italic;
}

/* Modular PI Placeholder */
QFrame#ModularPI {
    background: repeating-linear-gradient(45deg, rgba(0, 180, 255, 0.01), rgba(0, 180, 255, 0.01) 10px, rgba(0, 180, 255, 0.02) 10px, rgba(0, 180, 255, 0.02) 20px);
    border: 1px dashed rgba(0, 180, 255, 0.15);
    border-radius: 12px;
}

QLabel#PISubtitle {
    color: rgba(0, 180, 255, 0.3);
    font-family: 'Share Tech Mono';
    font-size: 10px;
    text-transform: uppercase;
}

/* Settings Grouping */
QFrame#SettingsGroup {
    background: rgba(255, 255, 255, 0.01);
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-left: 3px solid #00c8ff;
    border-radius: 4px;
    padding: 20px;
}

/* Common Components */
QLineEdit, QDoubleSpinBox, QComboBox {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    padding: 8px 12px;
    color: #ffffff;
    font-family: 'Share Tech Mono';
}

QPushButton#SaveButton {
    background-color: rgba(0, 255, 157, 0.1);
    border: 1px solid rgba(0, 255, 157, 0.3);
    color: #00ff9d;
    font-family: 'Orbitron';
    font-size: 11px;
    font-weight: bold;
    padding: 12px;
    border-radius: 6px;
}

QPushButton#SaveButton:hover {
    background-color: rgba(0, 255, 157, 0.2);
    border-color: #00ff9d;
}

QPushButton#BackButton {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    color: rgba(255, 255, 255, 0.4);
    font-family: 'Share Tech Mono';
    font-size: 10px;
    padding: 6px 12px;
}

QPushButton#BackButton:hover {
    color: #ffffff;
    border-color: #ffffff;
}

QCheckBox {
    color: rgba(255, 255, 255, 0.6);
    font-family: 'Share Tech Mono';
    font-size: 11px;
}
"""
