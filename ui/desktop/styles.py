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

/* Sidebar / Navigation Area */
QFrame#NavBar {
    background-color: #060e1a;
    border-right: 1px solid rgba(0, 180, 255, 0.15);
    min-width: 200px;
}

QLabel#LogoLabel {
    font-family: 'Orbitron', sans-serif;
    font-size: 18px;
    font-weight: bold;
    color: #00c8ff;
    padding: 20px;
    margin-bottom: 20px;
}

/* Navigation Buttons */
QPushButton.NavButton {
    background-color: transparent;
    border: none;
    color: rgba(200, 230, 255, 0.6);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    text-align: left;
    padding: 12px 20px;
    border-left: 3px solid transparent;
}

QPushButton.NavButton:hover {
    background-color: rgba(0, 180, 255, 0.05);
    color: #00c8ff;
}

QPushButton.NavButton[active="true"] {
    background-color: rgba(0, 180, 255, 0.1);
    color: #00c8ff;
    border-left: 3px solid #00c8ff;
    font-weight: bold;
}

/* Content Area */
QFrame#ContentFrame {
    background-color: transparent;
}

QLabel#SectionTitle {
    font-family: 'Orbitron', sans-serif;
    font-size: 22px;
    color: #00c8ff;
    margin-bottom: 10px;
}

/* Metric Cards */
QFrame.MetricCard {
    background-color: rgba(0, 20, 45, 0.7);
    border: 1px solid rgba(0, 180, 255, 0.2);
    border-radius: 8px;
    padding: 15px;
}

QLabel.MetricLabel {
    font-family: 'Share Tech Mono', monospace;
    color: rgba(0, 200, 255, 0.5);
    font-size: 11px;
    text-transform: uppercase;
}

QLabel.MetricValue {
    font-family: 'Orbitron', monospace;
    color: #00ff9d;
    font-size: 18px;
    font-weight: bold;
}

/* Tool Access Cards */
QFrame.ToolCard {
    background-color: rgba(0, 30, 60, 0.4);
    border: 1px solid rgba(0, 180, 255, 0.1);
    border-radius: 10px;
}

QFrame.ToolCard:hover {
    border-color: rgba(0, 200, 255, 0.5);
    background-color: rgba(0, 180, 255, 0.05);
}

QLabel#ToolTitle {
    font-family: 'Orbitron', sans-serif;
    font-size: 16px;
    color: #ffffff;
}

QLabel#ToolDesc {
    font-family: 'Share Tech Mono', monospace;
    color: rgba(200, 230, 255, 0.5);
    font-size: 12px;
}
"""
