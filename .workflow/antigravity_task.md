# Replicator Polish Task

## 1) Hotkey Group Names
**Problema:** El selector de grupos de hotkeys no mostraba los nombres personalizados (ej. "Basic"), dificultando la identificación de los grupos.
**Causa:** El combo se inicializaba con textos estáticos y no se actualizaba tras guardar el nombre.
**Solución:** Se implementó `_reload_group_combo()` que utiliza `itemData` para los IDs y formatea las etiquetas como "Grupo ID — Nombre". Se dispara el refresco automáticamente al guardar.

## 2) Active Border Initial Detection
**Problema:** Al lanzar los overlays, el cliente EVE en primer plano no mostraba el borde activo hasta que se interactuaba con él.
**Causa:** La detección dependía exclusivamente de eventos de foco o del timer de 500ms, pero no se validaba el estado en el momento justo del arranque.
**Solución:** Se añadió `_init_active_check` en `ReplicationOverlay.__init__` (vía un timer de 100ms para asegurar que el HWND esté listo) que consulta inmediatamente `get_foreground_hwnd()`.

## 3) Compact Settings Dialog
**Problema:** Ventana de ajustes con exceso de espacio vacío a la derecha.
**Causa:** `setMinimumWidth` en 440px y layouts con expansiones por defecto.
**Solución:** Reducción de ancho mínimo a 340px y optimización de alineaciones.

## 4) Border Shape Clipping
**Problema:** La imagen capturada sobresalía de los bordes redondeados o con formas especiales.
**Causa:** Se dibujaba el pixmap en el rect completo del widget sin aplicar máscaras o recortes basados en la forma del borde.
**Solución:** Implementación de `QPainterPath` con `setClipPath` en `paintEvent`. Ahora el contenido se recorta dinámicamente según si la forma es `rounded`, `pill` o `glow`, respetando el grosor del borde.

## Pruebas Realizadas
- `python -m py_compile`: Todo correcto.
- `pytest`: Tests de persistencia y hotkeys superados.
- Validación manual de renderizado de formas y detección de foco inicial.

**Archivos Tocados:**
- `overlay/replication_overlay.py`
- `overlay/replicator_settings_dialog.py`
- `overlay/replicator_config.py` (referencia de keys)
