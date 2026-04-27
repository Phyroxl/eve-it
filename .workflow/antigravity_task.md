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
- [ ] **Depuración de Visualización Performance**: El dashboard no muestra los datos a pesar de la sincronización exitosa.
- [ ] **Rutas Absolutas**: Estandarizar el acceso a `market_performance.db` para evitar inconsistencias de directorio.
- [ ] **Casteo de Datos**: Asegurar que IDs de personaje sean tratados siempre como Integers en la capa de persistencia.

## Pendiente ⏳
- [ ] Verificación final de flujo de Station Trading real con datos de Jita.
- [ ] Pulido de Tooltips informativos adicionales.
- [ ] Optimización de carga inicial de Performance (Cache local).

---
*Estado: Bloqueado en visualización de datos ESI.*
