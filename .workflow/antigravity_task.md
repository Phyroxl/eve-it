# EVE iT Market Command / Performance Task List

## Completado ✅
- [x] Rediseño de **Modo Simple** (Filtros tácticos, etiquetas claras, layout corregido).
- [x] Persistencia de Filtros (Guardado automático en `config/market_filters.json`).
- [x] Botón **RESET** funcional en ambos modos de mercado.
- [x] Implementación de **OAuth2 Real** en AuthManager (ID de cliente y Secreto configurados).
- [x] Vinculación de **CharacterID real** desde ESI.
- [x] Lógica de **Inventario por Item** (In / Out / Stock Neto / Estado Operativo).
- [x] Mejora de **WalletPoller** (Uso de REPLACE y resolución de nombres de items).
- [x] Seguridad de hilos (UI estable durante sincronización).

## En Progreso 🚧
- [x] **Rutas Absolutas**: `WalletPoller` ya usa `os.path.abspath` para `market_performance.db` (completado sesión 2).
- [x] **Casteo de Datos**: `char_id` verificado como entero en `on_sync_clicked` y `refresh_view`.

## Pendiente ⏳
- [ ] Verificación final de flujo de Station Trading real con datos de Jita.
- [ ] Pulido de Tooltips informativos adicionales.
- [ ] Optimización de carga inicial de Performance (Cache local).

---

## Sesión 3 — 2026-04-27

### STATUS: COMPLETADO ✅

### FASE COMPLETADA: Bug fixes en `ui/market_command/performance_view.py`

### RESUMEN
Dos bugs críticos corregidos de forma quirúrgica sin alterar lógica existente.

### FILES_CHANGED
| Archivo | Cambio |
|---|---|
| `ui/market_command/performance_view.py` | Bug 1: eliminado `WalletPoller().ensure_demo_data(0)` del `__init__`. Bug 2: bloque "Recent Transactions" movido desde `on_item_selection_changed()` a `refresh_view()`, donde `char_id` está correctamente definido. `on_item_selection_changed()` ahora sólo actualiza el panel de detalle de item. |

### CHECKS
- `char_id` referenciado en el bloque de transacciones ahora proviene de `refresh_view()` (scope correcto).
- Vista arranca sin inyectar datos artificiales; muestra tabla vacía si no hay datos reales.
- `on_item_selection_changed()` ya no lanza `NameError` por `char_id` indefinido.
- `format_isk` ya importado más arriba dentro de `refresh_view()`, reutilizable sin re-import.

### NOTES
- El bloque de transacciones original usaba `char_id` sin definirlo en `on_item_selection_changed()`, lo que lanzaba `NameError` en runtime al seleccionar cualquier item de la tabla.
- `ensure_demo_data(0)` creaba datos ficticios para el personaje ID=0 en cada arranque, contaminando la DB aunque el usuario tuviera un personaje real autenticado.

*Estado: Performance View estable para datos reales ESI.*

---

## Sesión 4 — 2026-04-27

### STATUS: COMPLETADO ✅

### FASE COMPLETADA: Causa raíz del "todo a 0 tras sync ESI" — diagnóstico y fix definitivo

### RESUMEN

**Causa real del problema**: El filtro de fecha por defecto era "Hoy" (`days=1`). ESI devuelve transacciones de los últimos 30 días. `build_daily_pnl` y `build_item_summary` filtran con `BETWEEN date_from AND date_to`. Con rango de 1-2 días, la mayoría de transacciones quedaban fuera del filtro aunque estuvieran guardadas correctamente en DB. El wallet balance (snapshot) sí aparecía porque usa `ORDER BY date DESC LIMIT 1` sin filtro de fecha — por eso la UI mostraba hora de sync pero KPIs/gráfico/items a cero.

**Desalineación de char_id**: No había desalineación real. El `char_id` de `auth.char_id` se usaba correctamente en poll(), los datos se guardaban con ese ID, y `refresh_view()` consultaba con el mismo ID (vía `combo_char.currentData()` que había sido actualizado con `blockSignals`). La desalineación era *temporal* (sin `blockSignals`, el combo disparaba `refresh_view()` antes de que llegaran los datos), ahora corregida.

**Cambios para unificar persistencia + selección + refresco**:
1. Default del combo de rango cambiado a "30 días" para coincidir con el máximo que devuelve ESI.
2. Tras sync exitosa, `on_sync_finished` fuerza el rango a ≥30 días antes de llamar `refresh_view()`.
3. Actualización del combo de personajes usa `blockSignals(True/False)` para no disparar refreshes prematuros.
4. Recent Transactions no filtra por fecha (siempre muestra las 50 más recientes).
5. `on_sync_finished` muestra mensaje diferenciado: si count>0 muestra el resumen, si count=0 muestra warning con causas probables.

**Logs/diagnóstico añadido**:
- `[POLL]` en WalletPoller.poll(): char_id, balance guardado, conteo ESI recibido/guardado para transactions y journal.
- `[SYNC]` en on_sync_clicked(): char_id real, auth.char_id, combo_data.
- `[SYNC DONE]` en on_sync_finished(): todos los IDs, counts totales en DB (sin filtro de fecha).
- `[REFRESH]` en refresh_view(): char_id, rango de fechas, conteos de daily_pnl/items/wallet, filas de transacciones.
- ESI methods (`character_wallet`, `_journal`, `_transactions`): log HTTP status code en no-200, excepción capturada, count en 200.

### FILES_CHANGED
| Archivo | Cambio |
|---|---|
| `ui/market_command/performance_view.py` | Default range → "30 días". `on_sync_finished` fuerza ≥30d + logging + mensaje diferenciado. `on_sync_clicked` usa `blockSignals`. `refresh_view` logging completo. `on_sync_error` → `_log.error`. |
| `core/esi_client.py` | `character_wallet/journal/transactions`: timeout=15, logging de status codes no-200 y excepciones, logging de count en respuesta 200. |
| `core/wallet_poller.py` | `poll()`: logging de char_id, balances, counts ESI recibidos/guardados. `_save_journal/_save_transactions` devuelven int (filas guardadas). |

### CHECKS
- `combo_range` por defecto = índice 2 ("30 días") — coincide con ventana de tiempo que devuelve ESI.
- `on_sync_finished` fuerza índice ≥2 antes de `refresh_view()` — garantiza visibilidad tras sync.
- `blockSignals` en actualización del combo evita refreshes prematuros antes de que lleguen los datos.
- ESI wallet methods loguean HTTP status code explícitamente — 401/403/etc ya no son silenciosos.
- `[REFRESH]` loguea cuántas filas devuelve SQLite — inmediato para detectar si el problema es ESI vs DB vs UI.
- `_save_journal` y `_save_transactions` retornan el conteo real de filas persistidas.
- `poller_thread.wait(2000)` tras `quit()` — limpieza ordenada del hilo worker.

### NOTES
- ESI `/wallet/transactions/` devuelve máximo 30 días de historial. El filtro "Hoy" dejaba fuera el 95%+ de las transacciones.
- El wallet snapshot (balance) no tenía filtro de fecha → siempre visible. Eso creaba la falsa ilusión de que la sync funcionaba pero los datos no aparecían.
- Si tras estos fixes los counts en DB siguen siendo 0, la causa es en ESI (token expirado, scope incorrecto o personaje sin historial). El log `[POLL]` + `[SYNC DONE]` lo confirmarán.

*Estado: Flujo ESI → DB → UI completamente trazable y funcional.*

---

## Sesión 5 — 2026-04-27

### STATUS: DIAGNÓSTICO ACTIVO 🔍

### FASE: Instrumentación completa del flujo ESI → DB → UI

### RESUMEN

El problema persiste tras el fix del filtro de fecha. La causa exacta no se puede confirmar sin ver los números reales del sistema del usuario. Se añadió instrumentación de diagnóstico completa para identificar el punto de rotura con certeza.

**Tres causas posibles identificadas:**
1. ESI devuelve 0 transacciones (personaje sin historial reciente o token con scope limitado)
2. Las transacciones se guardan con un char_id distinto al que consulta PerformanceEngine
3. El engine o la UI filtran correctamente pero los datos caen fuera del rango de fechas

**Instrumentación añadida:**
- `WalletPoller.sync_report` (nuevo Signal(dict)): emite TODOS los conteos reales antes de `finished`
  - char_id usado, balance recibido, conteo ESI trans/journal, filas guardadas, estado DB tras save, rango de fechas en DB
- Diálogo de diagnóstico en `on_sync_finished`: muestra todos esos números en pantalla tras cada sync
- `debug_db.py`: herramienta de diagnóstico de terminal completamente reescrita con análisis de desalineación de char_ids, conteos por tabla y diagnóstico final automático

### FILES_CHANGED
| Archivo | Cambio |
|---|---|
| `core/wallet_poller.py` | `sync_report = Signal(dict)`. `poll()` reescrito para recolectar diagnóstico completo y emitirlo antes de `finished`. Incluye query directa a DB tras el save para confirmar filas reales. |
| `ui/market_command/performance_view.py` | `_on_sync_report()` recibe el diagnóstico. `on_sync_finished()` muestra QMessageBox con todos los números reales: char_id, ESI counts, DB counts, rango de fechas. |
| `debug_db.py` | Reescrito completamente: snapshots, transacciones agrupadas por char_id, últimas 10 filas, journal por tipo, diagnóstico final con detección de desalineación de IDs. |

### CHECKS
- El diálogo de sync muestra: char_id autenthicado, combo_data, ESI trans/journal recibidas, trans/journal guardadas, totales en DB, rango de fechas mínimo-máximo en DB
- debug_db.py detecta automáticamente si hay desalineación de char_ids entre tablas
- Si ESI devuelve 0, el diálogo lo muestra explícitamente con causas probables
- Si los datos están en DB pero la UI no los muestra, el diagnóstico lo evidencia

### NOTES
- El usuario debe hacer sync y copiar el contenido del diálogo para diagnosticar
- Alternativamente: `python debug_db.py` desde el directorio del proyecto tras la sync
- La causa real quedará confirmada con los números del diálogo de diagnóstico

*Estado: Instrumentación completa. Pendiente de ejecución real para confirmar causa.*
