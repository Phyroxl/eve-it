# Replicator Polish Task

## 1) Hotkey Group Names
**Problema:** El selector de grupos de hotkeys no mostraba los nombres personalizados (ej. "Basic"), dificultando la identificación de los grupos.
**Causa:** El combo se inicializaba con textos estáticos y no se actualizaba tras guardar el nombre.
**Solución:** Se implementó `_reload_group_combo()` que utiliza `itemData` para los IDs y formatea las etiquetas como "Grupo ID — Nombre". Se dispara el refresco automáticamente al guardar. Se añadió logging para verificar la persistencia.

## 2) Active Border Initial Detection
**Problema:** Al lanzar los overlays, el cliente EVE en primer plano no mostraba el borde activo hasta que se interactuaba con él.
**Causa:** La detección dependía de eventos de foco posteriores al arranque.
**Solución:** Se añadió `_init_active_check` en `ReplicationOverlay.__init__` (vía un timer de 100ms) que consulta inmediatamente `get_foreground_hwnd()` y activa el estado visual si coincide con la réplica.

## 3) Compact Settings Dialog
**Problema:** Ventana de ajustes con exceso de espacio vacío lateral.
**Causa:** `setMinimumWidth` elevado (440px) y labels demasiado anchos (160px).
**Solución:** Reducción de ancho mínimo a 340px y ajuste de `_row` labels a 130px. Esto elimina el espacio muerto y compacta la interfaz.

## 4) Border Shape Clipping
**Problema:** La imagen capturada sobresalía de los bordes redondeados o con formas especiales.
**Causa:** Falta de máscara de recorte (clipping) en el renderizado del pixmap.
**Solución:** Implementación de `QPainterPath` con `setClipPath` en `paintEvent`. El contenido se recorta dinámicamente según la forma (`rounded`, `pill`, `glow`), asegurando que la imagen nunca se salga del marco visual.

## 5) Toggle Marco Gris (show_gray_frame)
**Problema:** Al desmarcar "Mostrar borde gris" en Ajustes > Borde, el rectángulo gris exterior seguía visible en formas pill/rounded.
**Causa:** `show_gray_frame` no estaba en `BORDER_COPY_KEYS`, por lo que "Aplicar borde a todas" no lo propagaba; y la señal `toggled` del checkbox solo llamaba `update()` sin forzar repintado inmediato con `repaint()`. El paintEvent ya condicionaba correctamente el `drawRect(alpha=40)` pero el flag no llegaba actualizado en todos los casos.
**Solución:**
- `overlay/replicator_config.py`: añadido `'show_gray_frame'` a `BORDER_COPY_KEYS` para que "aplicar a todas" lo propague.
- `overlay/replicator_settings_dialog.py`: checkbox `toggled` ahora llama `_set + update() + repaint()` para forzar repintado sincrónico inmediato.
- `replication_overlay.py`: sin cambios — `paintEvent` ya tenía la lógica correcta.

## 6) Sync Manual Resize to All Replicas
**Problema:** Al redimensionar una réplica manualmente arrastrando sus bordes, el nuevo W/H no se propagaba a las demás réplicas aunque "Aplicar a todas las réplicas" estuviera marcado. Solo los cambios vía spinbox se propagaban.
**Causa:** `_on_overlay_geometry_changed` actualizaba los spinboxes con `blockSignals(True)`, impidiendo que `valueChanged` disparara `_on_layout_change`. El manual drag resize nunca llegaba al dispatcher.
**Solución:**
- `__init__`: añadidos `self._resize_from_spinbox = False` y `self._layout_change_broadcaster = None`.
- `_tab_layout`: tras definir `_on_layout_change`, se guarda `self._layout_change_broadcaster = _on_layout_change`.
- `_on_w_changed`/`_on_h_changed`: envuelven `self._ov.resize()` con `self._resize_from_spinbox = True/False` para distinguir la fuente.
- `_on_overlay_geometry_changed`: captura `prev_w`/`prev_h` antes del blockSignals; tras desbloquearlo, si `not self._resize_from_spinbox` y cambió w o h, llama al broadcaster — propagando el resize manual a todas las réplicas peer.

**Casos validados:**
1. Spinbox W/H → propaga sin doble-sync (guard `_resize_from_spinbox`).
2. Border-drag W → propaga a peers si checkbox ON.
3. Border-drag H → propaga a peers si checkbox ON.
4. Border-drag X/Y → no propaga (broadcaster filtra 'x'/'y').
5. Checkbox OFF → broadcaster devuelve inmediatamente, no propaga.

## 7) Reset Position global + Diamond shape + Label Text X/Y

### 7a — Resetear posición en todas las réplicas
**Problema:** El botón "Resetear posición" solo afectaba a la réplica activa aunque "Aplicar a todas las réplicas" estuviera ON.
**Solución:** Extraída la función `_reset_one_position(ov)` reutilizable. El handler `_reset_position()` ahora itera `_OVERLAY_REGISTRY` cuando `chk_lp_all.isChecked()`. Si está OFF, comportamiento original intacto.
**Archivo:** `overlay/replicator_settings_dialog.py`

### 7b — Nueva forma de borde "Diamante"
**Problema:** No existía forma diamond en el replicador.
**Solución:** Añadido 'diamond' al pipeline completo:
- `_tab_border()`: añadido a `_shapes` list y combo UI.
- `paintEvent()`: shape check actualizado a include 'diamond'; inner clip, border draw y debug layer también.
- `_build_visual_shape_path()`: path moveTo/lineTo con 4 vértices (top/right/bottom/left).
- `_get_shape_path()`: mismo path para borde y clip interno.
- `_apply_window_shape_mask()`: QBitmap path con diamond polygon.
- `_apply_native_window_region()`: `CreatePolygonRgn` con 4 POINT structs (ALTERNATE fill).
**Archivos:** `overlay/replication_overlay.py`, `overlay/replicator_settings_dialog.py`

### 7c — Label Text X/Y offset
**Problema:** No había forma de desplazar manualmente el texto de la etiqueta.
**Solución:** Añadidos campos `label_text_x`/`label_text_y` (default 0) a `OVERLAY_DEFAULTS`, `LABEL_COPY_KEYS` y `FULL_PROFILE_KEYS` en config. Dos spinboxes (rango ±2000) en `_tab_label()`. En `paintEvent()`, `lx` y `ly` reciben el offset tras el cálculo de posición base — X=0/Y=0 idéntico a antes.
**Archivos:** `overlay/replicator_config.py`, `overlay/replicator_settings_dialog.py`, `overlay/replication_overlay.py`

## 8) Reset 150x150 global + Asistente visual fixes + Borde región blanco

### 8a — Reset posición + tamaño 150x150
**Problema:** "Resetear posición" no cambiaba el tamaño, solo la posición.
**Solución:** `_reset_one_position(ov)` ahora usa `ov.setGeometry(new_x, new_y, 150, 150)` con constantes `_RESET_W=150`/`_RESET_H=150`. La posición centrada se calcula con 150px. `_reset_position()` envuelve todo en `self._resize_from_spinbox = True/False` para suprimir el broadcaster durante el reset y evitar cascadas. Con "aplicar a todas" ON resetea todas las réplicas a 150×150.
**Archivo:** `overlay/replicator_settings_dialog.py`

### 8b — Ajustes visuales del Asistente del Replicador
**Cambios en `controller/replicator_wizard.py`:**
- "ASISTENTE": color `#405060` → `#ffffff`
- Botón cerrar: estilo igualado al traductor (`border:1px solid rgba(255,50,50,0.4); border-radius:3px; background rgba 0.15 → 0.35 hover`)
- "LANZAR RÉPLICAS": verde explícito (`rgba(0,180,60,...)`), eliminado `objectName("close")`
- `lbl_res` (resolución): color `rgba(0,200,255,0.4)` → `#00c8ff` (igual que título)

**Cambios en `utils/i18n.py`:**
- `repl_p1_title` español (es): `'Ventanas EvE Detectadas'` → `'Ventanas detectadas'`
- `repl_p1_title` español (es_LA): `'Ventanales EVE Detectadas'` → `'Ventanas detectadas'`

### 8c — Borde blanco en Seleccionar Región
**Problema:** El borde de selección se veía en cyan-verde (0,255,200) que podía confundirse con oscuro.
**Solución:** En `overlay/region_selector.py` (`paintEvent`): colores (0,255,200) → (255,255,255) para el borde de selección, asas de esquinas y fill interior del área seleccionada.
**Archivo:** `overlay/region_selector.py`

## Pruebas Realizadas
- `python -m py_compile`: Validado en todos los módulos afectados.
- `pytest`: 63 tests de replicador pasados.
- Verificación de clipping visual con formas `pill` y `rounded`.
- Verificación de detección inmediata de borde activo al lanzar la suite.

## 9) Seleccionar pantalla en Asistente + botón HUD

### 9a — Nueva opción "Seleccionar pantalla"
**Qué:** Combo `scr_combo` en el bloque de configuración del asistente. Detecta todas las pantallas conectadas con `QApplication.screens()` e indica resolución, posición y si es principal.
**Cómo:** `_populate_screens()` y `_get_selected_screen()` añadidos a `ReplicatorWizard`. `_on_visual_select()` llama `select_region(..., screen=selected_screen)`.
**region_selector.py:** `select_region()` acepta `screen=None`; cuando se provee, lo pasa a `RegionSelectorWidget` (que lo usa en `_setup_window` para `setGeometry(screen.geometry())`). El screenshot se captura con `screen.grabWindow(0, x, y, w, h)` para obtener solo esa pantalla.
**Coordenadas multi-monitor:** el widget se posiciona sobre la geometría virtual correcta (`screen.geometry()`) incluyendo coordenadas negativas (monitores a la izquierda). El `_ref_rect` fallback usa la geometría de la pantalla seleccionada.
**Archivos:** `controller/replicator_wizard.py`, `overlay/region_selector.py`

### 9b — Botón de cierre HUD azul oscuro
**Qué:** Botón cerrar y nuevo botón minimizar con estilo HUD oscuro (`#0B1B33` / `#294466` / `#DDEBFF`). Sin rojo, bordes redondeados, tamaño compacto 20×18.
**Archivo:** `controller/replicator_wizard.py`

## 10) REVERTIDO — Performance Mode experiments eliminados (commit 80bb315)

**Qué:** Los commits 8220c10 y 39ab960 (Ultra Fast Cycle Mode + selector UI de rendimiento) fueron completamente revertidos.
**Motivo:** La implementación rompió el Replicador en uso real con macros AHK Sleep 50ms.
**Archivos restaurados a 9007ab6:**
- `overlay/replicator_config.py` — sin `PERFORMANCE_MODE_CONFIGS` ni `get_perf_cfg`
- `overlay/win32_capture.py` — sin `focus_eve_window_ultra` ni `focus_eve_window_ultra_verified`
- `overlay/replicator_hotkeys.py` — sin `_cycle_group_ultra`, `_hotkey_ultra_events`, `_dump_ultra_summary`
- `controller/replicator_wizard.py` — sin combo "Modo de rendimiento"
- `tests/test_replicator_perf_mode.py` — eliminado (`git rm`)

**Fix preservado:** `get_overlay_cfg` acepta `'diamond'` como forma válida (feature de 98ec9ec, regresión introducida en 9007ab6 y re-aplicada manualmente tras el revert).

## Pruebas Realizadas
- `python -m py_compile`: Validado en todos los módulos afectados.
- `pytest tests/test_replicator*.py`: **68 tests pasados**.
- Verificación de clipping visual con formas `pill` y `rounded`.
- Verificación de detección inmediata de borde activo al lanzar la suite.

**Archivos Tocados:**
- `overlay/replication_overlay.py`
- `overlay/replicator_settings_dialog.py`
- `overlay/replicator_config.py`
- `overlay/win32_capture.py`
- `overlay/replicator_hotkeys.py`
- `controller/replicator_wizard.py`
- `overlay/region_selector.py`
- `utils/i18n.py`
- `.workflow/antigravity_task.md`

## 11) Diagnostico en vivo de Hotkeys del Replicador

**Problema:** Macros con Sleep 50ms / Sleep 20ms no activan módulos en algunas cuentas. Se necesita diagnóstico certero antes de modificar lógica.
**Solución:** Instrumentación de diagnóstico sin cambiar la lógica de ciclo. Solo activa overhead cuando el usuario lo habilita.

### Cambios en `overlay/replicator_hotkeys.py`:
- `from collections import deque`, `import queue` añadidos a imports.
- Estado global: `_hotkey_diagnostics_enabled`, `_hotkey_diagnostics_callback`, `_hotkey_diagnostics_events` (deque maxlen=1000).
- API pública: `set_hotkey_diagnostics_enabled(enabled, callback)`, `clear_hotkey_diagnostics()`, `get_hotkey_diagnostics_events()`.
- `_diag_event(type, **data)`: early return cuando disabled, sin overhead.
- `_cycle` (global) instrumentado con: `cycle_enter`, `cycle_skipped`, `foreground_snapshot`, `current_index_resolved`, `target_selected`, `focus_result`, `cycle_done`.
- `_cycle_group` instrumentado con: `cycle_group_enter`, `cycle_group_skipped`, `foreground_snapshot`, `current_index_resolved` (incluye `mismatch` detection), `target_selected`, `focus_result`, `cycle_group_done`.
- Variables de tracking: `_diag_resolver`, `_diag_fg_hwnd`, `_diag_fg_title`, `_diag_fg_match_idx`. Detecta mismatch cuando el foreground apunta a un cliente diferente al que el resolver usó.

### Cambios en `overlay/replicator_settings_dialog.py`:
- `QPlainTextEdit`, `Signal` añadidos a imports (PySide6/PyQt6 compat).
- `_hotkey_diag_signal = Signal(dict)` al nivel de clase.
- `closeEvent` limpia diagnóstico si estaba activo al cerrar el diálogo.
- Sección "DIAGNOSTICO EN VIVO" al final de la pestaña Hotkeys con:
  - `QPlainTextEdit` read-only (120-200px) para log en vivo.
  - Thread safety: `queue.Queue` + `QTimer` (60ms poll) para marshal de eventos desde el hilo de hotkeys al hilo UI.
  - Botones: Iniciar/Detener diagnóstico (toggle), Capturar estado, Limpiar, Copiar, Guardar.
  - "Capturar estado" muestra foreground hwnd/title, last_client, last_group_index, grupos con hwnd_cache y overlays activos.
  - Guardado en `logs/hotkey_live_diag_YYYYMMDD_HHMMSS.log`.

### Cómo usar:
1. Abrir Ajustes de cualquier réplica → pestaña Hotkeys.
2. Pulsar "Iniciar diagnostico".
3. Pulsar "Capturar estado" para ver snapshot inicial.
4. Ejecutar macro (F14/F15 con Sleep 50/20ms).
5. Ver líneas en tiempo real. Buscar `[MISMATCH]` en líneas RESOLVE.
6. Pulsar "Copiar" para analizar el log completo.

### Formato de líneas:
- `ENTER grp=1 dir=next last='EVE - Char4' last_idx=3 cooldown=0.0ms`
- `SKIP reason=cooldown delta=7.2ms min=10ms`
- `FG hwnd=123456 title='EVE - Char2' match_idx=1`
- `RESOLVE idx=3 title='EVE - Char4' resolver=last_cycle_client_id [MISMATCH fg_idx=1 fg='EVE - Char2']`
- `TARGET 3 -> 4 title='EVE - Char5' hwnd=789012 cache=True`
- `FOCUS ok=True title='EVE - Char5' total=0.8ms`
- `DONE ok=True 3 -> 4 total=1.2ms resolver=last_cycle_client_id`

### Tests añadidos:
- `tests/test_replicator_hotkey_diagnostics.py`: 11 tests (disabled noop, callback called, exception safe, clear, ring buffer limit, snapshot independiente).

**Archivos Modificados:** `overlay/replicator_hotkeys.py`, `overlay/replicator_settings_dialog.py`
**Tests:** 103 passed (replicator + hotkey suite)

## 12) FIX — Replicator window focus reliability (focus_eve_window_reliable)

**Commit 90bc585** — Primera implementación. Introdujo `focus_eve_window_reliable` con estrategias fast → raise_sync → attach_thread.

**Problema detectado en 90bc585:** Las estrategias `raise_sync` (SetWindowPos síncrono) y `attach_thread` (SetFocus/SetActiveWindow) usan SendMessage cross-process que puede bloquear 200-900 ms esperando la cola de mensajes de EVE. Ejemplos reales:
```
FOCUS ok=True title='EVE — Arien Inkura' total=982.9ms
FOCUS ok=True title='EVE — KonaN Herrera' total=292.0ms
```

## 13) FIX — Bound Replicator reliable focus latency

**Motivo:** focus_eve_window_reliable verificaba foreground pero bloqueaba la macro durante cientos de ms. `BringWindowToTop` y `SetWindowPos` sin `SWP_ASYNCWINDOWPOS` son SendMessage síncronos; `SetFocus`/`SetActiveWindow` también.

**Nuevo diseño — presupuesto estricto:**
- `focus_eve_window_reliable(hwnd, max_total_ms=60)` — nunca supera el presupuesto.
- Solo usa `SetForegroundWindow` + `SetWindowPos(SWP_ASYNCWINDOWPOS)` — ambos async, < 5ms.
- Sin `BringWindowToTop` (SendMessage síncrono). Sin `SetWindowPos` síncrono.
- `ENABLE_ATTACH_THREAD_FALLBACK = False` — AttachThreadInput desactivado por defecto.

**Estrategias activas por defecto:**
1. **fast** — SetForegroundWindow + SetWindowPos(async) → verify 20ms
2. **retry_async** — repite la misma llamada → verify 25ms
3. **final** — un SetForegroundWindow más → verify 10ms

**Protección de presupuesto:** `_elapsed()` / `_remaining()` antes de cada verify. Si `remaining <= 0`, devuelve `ok=False` inmediatamente con `budget_exceeded=True`. El timeout de cada verify es `min(deseado, remaining)`.

**Detección de llamadas lentas:** Si alguna llamada Win32 tarda > 50ms, se añade `slow_call=NombreLlamada:Xms` al detail.

**Detail de ejemplo:**
```
reliable_focus strategy=fast verified=True verify_ms=8.2 actual=123 total_ms=9.1 attempts=fast:true budget_exceeded=False
reliable_focus strategy=retry_async verified=True verify_ms=18.7 actual=123 total_ms=31.4 attempts=fast:false,retry_async:true budget_exceeded=False
reliable_focus strategy=failed verified=False actual=0 total_ms=58.9 attempts=fast:false,retry_async:false budget_exceeded=False
reliable_focus strategy=failed verified=False actual=0 total_ms=63.2 attempts=fast:false,retry_async:false budget_exceeded=True
```

**Archivos Modificados:**
- `overlay/win32_capture.py` — `ENABLE_ATTACH_THREAD_FALLBACK=False`, rediseño completo de `focus_eve_window_reliable`
- `tests/test_hotkey_focus_verify.py` — 8 tests nuevos en `TestFocusEveWindowReliable`

**Pruebas:**
- `python -m py_compile overlay/win32_capture.py overlay/replicator_hotkeys.py` → OK
- `python -m pytest tests -k "replicator or hotkey or focus or win32"` → **125 passed**

**Cómo validar en diagnóstico:**
1. Limpiar `logs/hotkey_perf.log`. Abrir diagnóstico en vivo.
2. Ejecutar macro Sleep 70ms. Revisar líneas FOCUS.
3. No debe aparecer `total=900ms`, `total=200ms` etc.
4. Objetivo: mayoría < 30ms, peor caso < 80ms.
5. Si un ciclo falla, la línea debe mostrar `strategy=failed budget_exceeded=False/True` y no bloquear la macro.
6. Probar Sleep 60ms y Sleep 50ms si Sleep 70 funciona.

## 14) PERF — Reducción de carga visual durante ráfagas de hotkeys

**Problema:** Durante macros rápidas (F14/F15 con Sleep 50-70ms), la captura visual y los repaints de bordes compiten con el cambio de foco de ventana. Esto puede causar `[NOT VERIFIED]` puntuales incluso cuando el foco es correcto en la siguiente invocación (0.4ms).

**Solución:** Nuevo módulo `overlay/replicator_runtime_state.py` con estado de ráfaga compartido. Tanto `replicator_hotkeys.py` como `replication_overlay.py` lo importan sin riesgo de circular imports.

**Constantes:**
- `HOTKEY_BURST_VISUAL_SUSPEND_MS = 120` — ventana de suspensión visual por hotkey
- `HOTKEY_BURST_LOG_THROTTLE_MS = 500` — throttle de logs para evitar spam

**API pública del módulo:**
- `note_hotkey_burst_event(reason)` — extiende ventana de suspensión, incrementa contador
- `is_hotkey_burst_active() -> bool` — True durante ventana activa (barato, sin I/O)
- `get_hotkey_burst_remaining_ms() -> float` — ms restantes
- `get_hotkey_burst_count() -> int` — total de eventos registrados
- `should_log_burst() -> bool` — throttle de 500ms para entradas de log

**Cambios en `replicator_hotkeys.py`:**
- En `_cycle` y `_cycle_group`, justo después de `_capture_suspended_until`, se llama a `note_hotkey_burst_event(reason)`.
- Si `should_log_burst()`, se emite `[HOTKEY BURST] active suspend_ms=120 count=N` al perf log y evento `burst_visual_suspend` al diagnóstico en vivo.

**Cambios en `replication_overlay.py`:**
- `_pending_border_flush = False` añadido como variable de clase.
- `CaptureThread.run()`: importa `replicator_runtime_state` y añade guard `if _rs_mod.is_hotkey_burst_active(): skip frame`. Belt-and-suspenders junto con `_capture_suspended_until` existente.
- `notify_active_client_changed()`: durante burst, actualiza `_is_active_client` pero NO llama `ov.update()`. Establece `_pending_border_flush = True`. El log cambia de `logger.info` a `logger.debug`.
- `_monitor_focus()`: al inicio, verifica `_pending_border_flush`. Si burst ha terminado, limpia el flag y llama `ov.update()` en todos los overlays. Garantiza repaint en máximo 75ms tras fin de ráfaga.

**Log de diagnóstico:**
```
[HOTKEY BURST] active suspend_ms=120 count=42
```

**Archivos Modificados:**
- `overlay/replicator_runtime_state.py` — nuevo módulo (estado compartido)
- `overlay/replicator_hotkeys.py` — `note_hotkey_burst_event` en `_cycle` y `_cycle_group`
- `overlay/replication_overlay.py` — burst guard en captura, deferral en notify, flush en monitor
- `tests/test_replicator_burst.py` — nuevo archivo, 17 tests

**Pruebas:**
- `python -m py_compile overlay/replicator_runtime_state.py overlay/replicator_hotkeys.py overlay/replication_overlay.py` → OK
- `python -m pytest tests -k "replicator or hotkey or overlay or focus or win32 or burst"` → **146 passed, 1 skipped**

**Cómo validar en diagnóstico:**
1. Limpiar `logs/hotkey_perf.log`. Abrir diagnóstico en vivo.
2. Ejecutar macro Sleep 70ms. Revisar que aparecen líneas `[HOTKEY BURST]`.
3. Las réplicas pueden congelarse visualmente ~120ms durante la ráfaga — esto es correcto.
4. Los bordes activos se actualizan a más tardar 75ms después de cada ráfaga.
5. Comprobar que bajan o desaparecen los `[NOT VERIFIED]` puntuales.
6. Probar Sleep 60ms y Sleep 50ms si Sleep 70ms funciona.
