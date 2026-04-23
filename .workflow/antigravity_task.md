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


---

# Task: Fix Freeze Bug - Replica congela al reducir tamaño del overlay

## STATUS: PENDING

## CAUSA RAÍZ IDENTIFICADA
La validación multi-punto en `win32_capture.py` opera sobre el bitmap ya escalado a `out_w x out_h`. Cuando el overlay es pequeño, StretchBlt comprime una región oscura de EVE a resolución baja → los 5 puntos de validación devuelven 0 (negro) → `captured = False` → no se emite frame → stale detector se activa → auto-recovery re-resuelve el HWND (que ya era válido) → no resuelve nada. El síntoma es: replica congelada en overlay pequeño, se descongela al hacer zoom in.

## CAMBIOS REQUERIDOS

### FILE 1: overlay/win32_capture.py
En `capture_window_region`, bloque RUTA 1 (zona ~línea 227-240):
- Añadir guard de tamaño antes de la validación de píxeles
- - Si `out_w < 80` o `out_h < 80`: saltar validación, forzar `captured = True`
  - - Mantener validación 5 puntos solo cuando `out_w >= 80` y `out_h >= 80`
   
    - ### FILE 2: overlay/replication_overlay.py
    - En método `_on_stale` (~línea 400), cuando `is_stale == True`:
    - - Añadir re-sync de output_size con dimensiones actuales del overlay:
      -   `if hasattr(self, '_capture'): self._capture.set_output_size(self.width(), self.height())`
     
      -   ## CHECKS
      -   - [ ] Replica no congela al reducir tamaño del overlay
          - [ ] - [ ] Stale detection sigue funcionando para capturas genuinamente rotas
          - [ ] - [ ] Sin cambios en otras réplicas ni en lógica global de captura
          - [ ] - [ ] Validación multi-punto activa para tamaños normales (>= 80px)
       
          - [ ] ## NOTES
          - [ ] No refactorizar. Cambios mínimos y quirúrgicos.
