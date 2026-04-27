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
