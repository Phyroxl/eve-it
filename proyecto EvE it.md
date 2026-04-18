# 🚀 Proyecto EVE iT - Documentación de Desarrollo (v2.1)

## 🧭 Visión General
EVE iT es una suite "Todo en uno" profesional para EVE Online. Opera de forma discreta desde la bandeja del sistema y utiliza `PyQt6` para interfaces inmersivas y `Streamlit` para analíticas. El proyecto ha evolucionado hacia una estética "High-Tech" y una robustez de grado operativo.

---

## 🏗️ Innovaciones Recientes y Estado del Arte

### 1. 🛠️ Profesionalización y Ciclo de Vida
- **Lanzador Invisible (`EVE-iT.vbs`)**: Implementado arranque mediante VBScript para eliminar el parpadeo de ventanas CMD. La app inicia directamente en la bandeja del sistema.
- **Shutdown Total (Aggressive)**: El `AppController` utiliza `psutil` para rastrear y terminar por la fuerza cualquier proceso hijo (como el servidor de Streamlit) al cerrar la aplicación, garantizando que no queden procesos "zombis".

### 2. 🗣️ Traductor de Chat Inteligente (Mejorado)
- **Carga de Historial Activa**: Al cambiar de canal, el sistema realiza un **rebobinado de logs (2 horas)**, traduciendo y mostrando instantáneamente la actividad previa del canal seleccionado.
- **Gestión Dinámica de Canales**:
    - **Fijos**: Local, Flota, Corp y Alianza siempre están disponibles.
    - **Privados**: Se detectan automáticamente y se eliminan del menú tras **60 minutos** de inactividad para mantener la limpieza.
- **UX de Precisión**: Se ha añadido un indicador visual rojo (`◢`) en la esquina inferior derecha para redimensionar el chat de forma intuitiva.

### 3. 🧬 Replicador de Ventanas 2.0
- Sistema de "espejos" para multiboxing con un `Replicator Wizard` que permite seleccionar regiones exactas de la pantalla de forma visual y proyectarlas en ventanas maestras.

### 4. 🎨 Estética "Neo-EVE"
- **Panel de Control**: Botones principales rediseñados con estilo de panel táctico, iconos técnicos (`📡`, `👁️`, `🧬`) y gradientes de neón (Cian, Verde Plasma y Púrpura Warp).
- **Internacionalización**: Soporte nativo y reactivo en tiempo real para múltiples idiomas, con el **Español** como idioma preferente de la interfaz.

---

## 🛠️ Especificaciones Técnicas para IAs
- **Entorno**: Python 3.10+ en entorno virtual (`venv`).
- **Seguridad**: La app opera exclusivamente mediante lectura de logs y duplicación de pantalla (GDI/Desktop Duplication), cumpliendo los TOS de EVE Online al no interactuar con la memoria del juego.
- **Persistencia**: Las configuraciones se guardan en `translator_config.json` y el estado de la ventana en el registro/config local.

*Este documento es la memoria viva del proyecto. Cualquier cambio en la arquitectura o interfaz debe ser reflejado aquí para mantener la coherencia en el desarrollo asistido por IA.*
