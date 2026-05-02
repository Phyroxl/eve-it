from ui.common.theme import Theme

MAIN_STYLE = Theme.get_qss() + f"""
/* DESKTOP SPECIFIC OVERRIDES */
QLabel#LogoLabel {{
    font-size: 14px;
    font-weight: 900;
    color: {Theme.ACCENT};
    padding: 25px 12px;
    letter-spacing: 3px;
    border-bottom: 1px solid {Theme.BORDER};
    margin-bottom: 10px;
}}

QPushButton.NavButton {{
    background: transparent;
    border: none;
    color: {Theme.TEXT_DIM};
    font-size: 11px;
    font-weight: 700;
    text-align: left;
    padding-left: 20px;
    height: 44px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

QPushButton.NavButton:hover {{
    color: {Theme.ACCENT};
    background: {Theme.ACCENT_LOW};
}}

QPushButton.NavButton[active="true"] {{
    color: {Theme.ACCENT};
    background: linear-gradient(to right, {Theme.ACCENT_LOW}, transparent);
    border-left: 3px solid {Theme.ACCENT};
}}

/* CARDS: PREMIUM LOOK */
QFrame#CharacterCard {{
    background-color: {Theme.BG_PANEL};
    border: 1px solid {Theme.BORDER};
    border-radius: {Theme.RADIUS};
}}

QFrame#CharacterCard:hover {{
    border-color: {Theme.ACCENT};
    background-color: {Theme.BG_PANEL_ALT};
}}

QLabel#CharName {{
    font-size: 11px;
    font-weight: 800;
    color: white;
    letter-spacing: 0.5px;
}}

QFrame#CharAvatar {{
    background-color: {Theme.BG_NAV};
    border: 1px solid {Theme.ACCENT};
    border-radius: 2px;
}}

/* METRICS */
QLabel#IskValue {{
    font-size: 14px;
    font-weight: 800;
    color: {Theme.SUCCESS};
}}

QLabel#AnalyticVal {{
    font-size: 14px;
    font-weight: 800;
    color: white;
}}

/* BUTTONS */
QPushButton#SaveButton {{
    background-color: {Theme.ACCENT};
    color: black;
    border: none;
    border-radius: 2px;
    font-weight: 800;
    font-size: 12px;
    padding: 10px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}}

QPushButton#SaveButton:hover {{
    background-color: {Theme.ACCENT_HOVER};
}}

QPushButton#BackButton {{
    background-color: transparent;
    border: 1px solid {Theme.BORDER};
    color: {Theme.TEXT_DIM};
    font-size: 11px;
    font-weight: bold;
    padding: 6px 15px;
    border-radius: 2px;
}}

QPushButton#BackButton:hover {{
    color: white;
    border-color: {Theme.ACCENT};
    background: {Theme.ACCENT_LOW};
}}
"""
