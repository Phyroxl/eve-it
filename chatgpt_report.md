# Informe Técnico: Estabilización del Replicador EVE iT (Bug Phyrox Perez)

## 1. Problema Diagnosticado
Se observaba un congelamiento sistemático de la réplica del personaje "Phyrox Perez" en regiones específicas de la pantalla. El problema se agravaba al hacer zoom out y en ocasiones mostraba la propia interfaz de la Suite dentro de la réplica.

## 2. Causas Raíz Identificadas
*   **Validación de Frame Frágil**: El sistema comprobaba un solo píxel central. Si era negro (común en EVE), descartaba el frame, provocando congelamiento visual.
*   **Rounding Error (Bordes)**: Al hacer zoom, el cálculo de coordenadas generaba decimales que excedían el límite de la ventana por <1 píxel, lo que hacía que la API de Windows (`StretchBlt`) rechazara la captura por completo.
*   **Fugas de Composición (CAPTUREBLT)**: El uso de banderas de captura de escritorio permitía que el dashboard de EVE iT se filtrara en las réplicas, creando un bucle visual estático.
*   **Degradación del Hilo de Captura**: Múltiples bloques de código mal indentados y limpiezas de memoria GDI mal ubicadas causaban crashes silenciosos en el hilo de fondo.

## 3. Soluciones Implementadas

### A. Motor de Captura V6 (Reescritura Estructural)
*   **Clamping de Precisión**: Se implementó un recorte estricto a nivel de píxel que garantiza que el área de captura nunca exceda las dimensiones reales del cliente EVE, eliminando el bug del zoom.
*   **Validación Multi-Punto**: Ahora se verifican 5 puntos tácticos (centro y esquinas) para confirmar la vitalidad del frame antes de descartarlo.
*   **Ruta de Fallback Limpia**: Se optimizó la transición entre BitBlt (alta velocidad) y PrintWindow (ventanas ocultas) eliminando dependencias de memoria compartida que causaban crashes.

### B. Modo Sigilo (Tactical Cloaking)
*   **SetWindowDisplayAffinity**: Se aplicó la tecnología `WDA_EXCLUDEFROMCAPTURE` a las ventanas de EVE iT. Esto las hace invisibles para el motor de captura de Windows, permitiendo que las réplicas "miren a través" del dashboard sin capturarlo.

### C. Sistema de Vitalidad (Heartbeat)
*   **Detección de Stale Frames**: El overlay ahora detecta si no recibe imágenes nuevas durante 2 segundos y muestra una advertencia táctica (⚠️ CONGELADO) en lugar de una imagen estática engañosa.
*   **Auto-Recovery**: El hilo de captura intenta re-sincronizar el handle de la ventana automáticamente si detecta una pérdida de señal prolongada.

## 4. Archivos Modificados
*   `overlay/win32_capture.py`: Reescritura de `capture_window_region`, añadido `set_window_stealth`.
*   `overlay/replication_overlay.py`: Implementado monitor de vitalidad y visuales de error.
*   `main.py`: Activación del Modo Sigilo en el arranque.

## 5. Estado Actual
**ESTABLE**. El sistema captura correctamente a Phyrox Perez en cualquier región y nivel de zoom. Las réplicas son ahora inmunes a la presencia de la propia Suite encima de ellas.
