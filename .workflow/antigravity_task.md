# Task: Diagnóstico y Corrección de Congelamiento de Región (Phyrox Perez)

## STATUS: COMPLETED
## COMPLETED PHASE: Phase 3 - Robust Capture & Honest State

## SUMMARY
Se ha resuelto el bug de congelamiento selectivo que afectaba a regiones específicas de captura (caso "Phyrox Perez"). 

**Causa Raíz:**
La validación del frame capturado era "frágil": comprobaba un solo píxel en el centro de la región. Si ese píxel era 0 (negro), el sistema descartaba el frame por error y activaba la ruta de PrintWindow (muy pesada) o simplemente no emitía el frame. En EVE Online, es muy común que el centro de una región sea espacio profundo o un elemento de UI oscuro, lo que provocaba falsos negativos de captura y "congelaba" la imagen al no emitir actualizaciones.

**Soluciones Implementadas:**
1.  **Validación Multi-Punto (Tactical Grid):** Ahora se comprueban 5 puntos (centro + 4 cuadrantes). El frame solo se considera inválido si es 100% negro y falla el BitBlt.
2.  **Monitor de Vitalidad (Stale Detection):** Se ha añadido un detector de "frames estancados". Si una réplica no recibe frames nuevos durante 2 segundos, el overlay muestra un estado de advertencia táctica (⚠️ CONGELADO / SEÑAL PERDIDA).
3.  **Protocolo de Auto-Recuperación:** Al detectar un congelamiento, el hilo de captura intenta re-resolver el handle de la ventana automáticamente para recuperar la señal.

## FILES_CHANGED
- `overlay/win32_capture.py`: Actualizada lógica de validación de captura (Ruta 1).
- `overlay/replication_overlay.py`: Implementado `stale_detected`, señales de vitalidad y feedback visual de estado honesto.

## CHECKS
- [x] Captura de zonas negras/oscuras ya no provoca congelamiento.
- [x] El overlay muestra feedback visual claro si la señal se pierde.
- [x] Recuperación automática de handles stale.
- [x] Rendimiento optimizado al evitar fallbacks innecesarios a PrintWindow.

## NOTES
El sistema es ahora "honesto": si por alguna razón externa la captura falla, el usuario lo sabrá inmediatamente mediante el indicador de "Señal Perdida" en lugar de ver un frame estático engañoso.
