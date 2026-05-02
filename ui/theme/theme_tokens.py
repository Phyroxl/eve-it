"""
ui/theme/theme_tokens.py — Centralized theme token definitions and metadata.
"""

DEFAULT_TOKENS = {
    # WINDOW / PANELS
    "BG_WINDOW": "#05070a",
    "NAV_BG": "#0b1016",
    "NAV_BORDER": "#1e293b",
    
    # TABS
    "TAB_ACTIVE_BG": "#10161d",
    "TAB_ACTIVE_TEXT": "#00c8ff",
    "TAB_INACTIVE_TEXT": "#64748b",
    "TAB_HOVER_BG": "#0f172a",
    "TAB_INDICATOR": "#00c8ff",
    
    # SIDEBAR / TACTICAL
    "SIDEBAR_BG": "#070a0e",
    "SIDEBAR_BORDER": "#1e293b",
    "SIDEBAR_HEADER_BG": "#0b1016",
    "SIDEBAR_HEADER_TEXT": "#64748b",
    
    # FILTERS
    "FILTER_CARD_BG": "#0b1016",
    "FILTER_CARD_BORDER": "#1e293b",
    "FILTER_CARD_HOVER": "#00c8ff",
    "FILTER_LABEL": "#475569",
    
    # INPUTS
    "INPUT_BG": "#0b1016",
    "INPUT_BORDER": "#1e293b",
    "INPUT_TEXT": "#e2e8f0",
    "INPUT_FOCUS": "#00c8ff",
    
    # CHECKBOX
    "CHECKBOX_BG": "#0b1016",
    "CHECKBOX_BORDER": "#334155",
    "CHECKBOX_CHECKED_BG": "#00c8ff",
    "CHECKBOX_TEXT": "#94a3b8",
    
    # CARDS / KPI
    "CARD_BG": "#0b1016",
    "CARD_BORDER": "#1e293b",
    "CARD_BORDER_HOVER": "#00c8ff",
    "CARD_TITLE": "#64748b",
    "CARD_VALUE": "#f8fafc",
    
    # DETAIL PANEL
    "DETAIL_PANEL_BG": "#070a0e",
    "DETAIL_PANEL_BORDER": "#1e293b",
    "DETAIL_ITEM_NAME_TEXT": "#00c8ff",
    "DETAIL_ICON_FRAME_BG": "#0b1016",
    "DETAIL_ICON_FRAME_BORDER": "#1e293b",
    
    # TABLES
    "TABLE_BG": "#070a0e",
    "TABLE_HEADER_BG": "#0b1016",
    "TABLE_HEADER_TEXT": "#64748b",
    "TABLE_HEADER_BORDER": "#1e293b",
    "TABLE_ROW_ALT_BG": "#090d12",
    "TABLE_GRID_LINE": "#151d27",
    "TABLE_CELL_TEXT": "#cbd5e1",
    "TABLE_ROW_SELECTED_BG": "#0f172a",
    "TABLE_ROW_SELECTED_TEXT": "#00c8ff",
    
    # BUTTONS
    "BTN_PRIMARY_BG": "#0b1016",
    "BTN_PRIMARY_TEXT": "#00c8ff",
    "BTN_PRIMARY_BORDER": "#1e293b",
    "BTN_PRIMARY_HOVER_BG": "#10161d",
    
    "BTN_SECONDARY_BG": "#0b1016",
    "BTN_SECONDARY_TEXT": "#94a3b8",
    "BTN_SECONDARY_BORDER": "#1e293b",
    "BTN_SECONDARY_HOVER_BG": "#10161d",
    
    "BTN_DANGER_BG": "#1e1010",
    "BTN_DANGER_TEXT": "#f87171",
    
    # SEMANTIC COLORS
    "ACCENT": "#00c8ff",
    "ACCENT_SECONDARY": "#00ffb3",
    "ACCENT_SOFT": "rgba(0, 200, 255, 0.2)",
    "SUCCESS": "#10b981",
    "DANGER": "#ef4444",
    "WARNING": "#f59e0b",
    "TEXT_MAIN": "#e2e8f0",
    "TEXT_DIM": "#64748b",
    
    # SCROLLBARS
    "SCROLL_TRACK": "#070a0e",
    "SCROLL_HANDLE": "#1e293b",
    "SCROLL_HANDLE_HOVER": "#334155",
    
    # TABLE SEMANTIC COLORS
    "TABLE_SCORE_HIGH": "#00ffb3",
    "TABLE_SCORE_MEDIUM": "#f59e0b",
    "TABLE_SCORE_LOW": "#ef4444",
    "TABLE_PROFIT_POSITIVE": "#10b981",
    "TABLE_PROFIT_NEGATIVE": "#ef4444",
    "TABLE_PROFIT_NEUTRAL": "#94a3b8",
    "TABLE_MARGIN_POSITIVE": "#10b981",
    "TABLE_MARGIN_WARNING": "#f59e0b",
    "TABLE_MARGIN_NEGATIVE": "#ef4444",
    "TABLE_TAGS_TEXT": "#00c8ff",
    
    # SELECTION ALIASES (to avoid fallbacks)
    "TABLE_SELECTION_BG": "#0f172a",
    "TABLE_SELECTION_TEXT": "#00c8ff",
    
    # MISC
    "MODE_LABEL_TEXT": "#64748b",
    "CHARACTER_BADGE_BG": "#0b1016",
    "CHARACTER_BADGE_TEXT": "#00c8ff",
    "CHARACTER_BADGE_BORDER": "#1e293b",
}

TOKEN_METADATA = {
    # WINDOW / PANELS
    "BG_WINDOW": ("Fondo Principal", "VENTANA GENERAL"),
    "NAV_BG": ("Fondo Barra Navegación", "BARRA SUPERIOR Y PESTAÑAS"),
    "NAV_BORDER": ("Borde Barra Navegación", "BARRA SUPERIOR Y PESTAÑAS"),
    
    # TABS
    "TAB_ACTIVE_BG": ("Fondo Pestaña Activa", "BARRA SUPERIOR Y PESTAÑAS"),
    "TAB_ACTIVE_TEXT": ("Texto Pestaña Activa", "BARRA SUPERIOR Y PESTAÑAS"),
    "TAB_INACTIVE_TEXT": ("Texto Pestaña Inactiva", "BARRA SUPERIOR Y PESTAÑAS"),
    "TAB_HOVER_BG": ("Fondo Pestaña Hover", "BARRA SUPERIOR Y PESTAÑAS"),
    "TAB_INDICATOR": ("Indicador Pestaña", "BARRA SUPERIOR Y PESTAÑAS"),
    
    # SIDEBAR
    "SIDEBAR_BG": ("Fondo Lateral Táctico", "CONFIGURACIÓN TÁCTICA"),
    "SIDEBAR_BORDER": ("Borde Lateral Táctico", "CONFIGURACIÓN TÁCTICA"),
    "SIDEBAR_HEADER_BG": ("Cabecera Lateral", "CONFIGURACIÓN TÁCTICA"),
    "SIDEBAR_HEADER_TEXT": ("Texto Cabecera Lateral", "CONFIGURACIÓN TÁCTICA"),
    
    # FILTERS
    "FILTER_CARD_BG": ("Fondo Tarjeta Filtro", "CONFIGURACIÓN TÁCTICA"),
    "FILTER_CARD_BORDER": ("Borde Tarjeta Filtro", "CONFIGURACIÓN TÁCTICA"),
    "FILTER_CARD_HOVER": ("Borde Filtro Hover", "CONFIGURACIÓN TÁCTICA"),
    "FILTER_LABEL": ("Etiqueta de Filtro", "CONFIGURACIÓN TÁCTICA"),
    
    # INPUTS
    "INPUT_BG": ("Fondo Input/Spinbox", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    "INPUT_BORDER": ("Borde Input", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    "INPUT_TEXT": ("Texto Input", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    "INPUT_FOCUS": ("Borde Focus", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    
    # CHECKBOX
    "CHECKBOX_BG": ("Fondo Checkbox", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    "CHECKBOX_BORDER": ("Borde Checkbox", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    "CHECKBOX_CHECKED_BG": ("Checkbox Marcado", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    "CHECKBOX_TEXT": ("Texto Checkbox", "INPUTS / COMBOBOX / SPINBOX / CHECKBOX"),
    
    # CARDS
    "CARD_BG": ("Fondo Tarjeta Resumen", "CARDS / RESUMEN SUPERIOR"),
    "CARD_BORDER": ("Borde Tarjeta Resumen", "CARDS / RESUMEN SUPERIOR"),
    "CARD_BORDER_HOVER": ("Borde Tarjeta Hover", "CARDS / RESUMEN SUPERIOR"),
    "CARD_TITLE": ("Título de Métrica", "CARDS / RESUMEN SUPERIOR"),
    "CARD_VALUE": ("Valor de Métrica", "CARDS / RESUMEN SUPERIOR"),
    
    # DETAIL
    "DETAIL_PANEL_BG": ("Fondo Panel Detalle", "DETALLE INFERIOR DEL ITEM"),
    "DETAIL_PANEL_BORDER": ("Borde Panel Detalle", "DETALLE INFERIOR DEL ITEM"),
    "DETAIL_ITEM_NAME_TEXT": ("Nombre Item Detalle", "DETALLE INFERIOR DEL ITEM"),
    "DETAIL_ICON_FRAME_BG": ("Fondo Marco Icono", "DETALLE INFERIOR DEL ITEM"),
    "DETAIL_ICON_FRAME_BORDER": ("Borde Marco Icono", "DETALLE INFERIOR DEL ITEM"),
    
    # TABLES
    "TABLE_BG": ("Fondo de Tabla", "TABLA PRINCIPAL"),
    "TABLE_HEADER_BG": ("Fondo Cabecera Tabla", "TABLA PRINCIPAL"),
    "TABLE_HEADER_TEXT": ("Texto Cabecera Tabla", "TABLA PRINCIPAL"),
    "TABLE_HEADER_BORDER": ("Borde Cabecera Tabla", "TABLA PRINCIPAL"),
    "TABLE_ROW_ALT_BG": ("Fila Alterna", "TABLA PRINCIPAL"),
    "TABLE_GRID_LINE": ("Líneas de Rejilla", "TABLA PRINCIPAL"),
    "TABLE_CELL_TEXT": ("Texto Celda Estándar", "TABLA PRINCIPAL"),
    "TABLE_ROW_SELECTED_BG": ("Fondo Fila Seleccionada", "TABLA PRINCIPAL"),
    "TABLE_ROW_SELECTED_TEXT": ("Texto Seleccionado", "TABLA PRINCIPAL"),
    
    # BUTTONS
    "BTN_PRIMARY_BG": ("Fondo Botón Primario", "BOTONES"),
    "BTN_PRIMARY_TEXT": ("Texto Botón Primario", "BOTONES"),
    "BTN_PRIMARY_BORDER": ("Borde Botón Primario", "BOTONES"),
    "BTN_PRIMARY_HOVER_BG": ("Hover Botón Primario", "BOTONES"),
    
    "BTN_SECONDARY_BG": ("Fondo Botón Secundario", "BOTONES"),
    "BTN_SECONDARY_TEXT": ("Texto Botón Secundario", "BOTONES"),
    "BTN_SECONDARY_BORDER": ("Borde Botón Secundario", "BOTONES"),
    "BTN_SECONDARY_HOVER_BG": ("Hover Botón Secundario", "BOTONES"),
    
    "BTN_DANGER_BG": ("Fondo Botón Peligro", "BOTONES"),
    "BTN_DANGER_TEXT": ("Texto Botón Peligro", "BOTONES"),
    
    # SEMANTIC
    "ACCENT": ("Color Acento Principal", "AVANZADO"),
    "ACCENT_SECONDARY": ("Color Acento Secundario", "AVANZADO"),
    "SUCCESS": ("Color Éxito", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "DANGER": ("Color Peligro", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "WARNING": ("Color Advertencia", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "TEXT_MAIN": ("Texto Principal", "AVANZADO"),
    "TEXT_DIM": ("Texto Dim / Muted", "AVANZADO"),
    
    # SCROLLBARS
    "SCROLL_TRACK": ("Carril de Scroll", "SCROLLBARS Y SELECCIÓN"),
    "SCROLL_HANDLE": ("Barra de Scroll", "SCROLLBARS Y SELECCIÓN"),
    "SCROLL_HANDLE_HOVER": ("Scroll Hover", "SCROLLBARS Y SELECCIÓN"),
    
    # TABLE SEMANTIC
    "TABLE_SCORE_HIGH": ("Score Alto (Tabla)", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "TABLE_SCORE_MEDIUM": ("Score Medio (Tabla)", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "TABLE_SCORE_LOW": ("Score Bajo (Tabla)", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "TABLE_PROFIT_POSITIVE": ("Profit Positivo (Tabla)", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "TABLE_PROFIT_NEGATIVE": ("Profit Negativo (Tabla)", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
    "TABLE_TAGS_TEXT": ("Tags / Etiquetas", "ESTADOS / TAGS / TEXTO SEMÁNTICO"),
}
