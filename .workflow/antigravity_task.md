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

## Pruebas Realizadas
- `python -m py_compile`: Validado en todos los módulos afectados.
- `pytest`: 87 tests de replicador pasados (incluye sync_resize, apply_settings_to_all, layout_profiles, focus_click, hide_inactive, snap, etc.).
- Verificación de clipping visual con formas `pill` y `rounded`.
- Verificación de detección inmediata de borde activo al lanzar la suite.

**Archivos Tocados:**
- `overlay/replication_overlay.py`
- `overlay/replicator_settings_dialog.py`
- `overlay/replicator_config.py`
- `.workflow/antigravity_task.md`
