# 🎨 User Interface (UI)
Separación de las capas de presentación de la aplicación.

## Estructura:
- `desktop/`: Interfaces construidas con PySide6/PyQt6 (ventanas principales, bandejas de sistema, widgets).
- `dashboard/`: Analíticas y configuraciones avanzadas basadas en Streamlit.
    - `components/`: Elementos reutilizables del dashboard.
    - `sections/`: Páginas o secciones principales.
    - `charts/`: Visualizaciones de datos específicas.

## Migración futura:
- Los archivos `.py` que definen ventanas de PyQt se moverán a `ui/desktop/`.
- La lógica de Streamlit se moverá a `ui/dashboard/`.
