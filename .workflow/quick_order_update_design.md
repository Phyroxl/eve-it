# Quick Order Update Assistant — Diseño Técnico

**Proyecto:** EVE iT / Market Command / Mis Pedidos  
**Feature:** Quick Order Update Assistant  
**Estado:** Fase 1 implementada — commit `FEAT: Add Quick Order Update popup for My Orders`  
**Fecha diseño:** 2026-04-29 | **Fecha implementación Fase 1:** 2026-04-29  

### Checklist Fase 1 completada

- [x] Doble click ÍTEM conserva comportamiento anterior
- [x] Doble click TIPO lanza Quick Order Update
- [x] Orden recuperada por `order_id` (fallback por type_id + side)
- [x] `analysis.competitor_price` usado para recomendación
- [x] SELL recomienda `competitor_sell - tick`
- [x] BUY recomienda `competitor_buy + tick`
- [x] Precio copiado automáticamente al portapapeles (sin separadores de miles)
- [x] Mercado in-game abierto automáticamente
- [x] Popup no modal (`QDialog` con `.show()`)
- [x] Referencia guardada en `self._quick_order_dialog`
- [x] Sin pyautogui/pywinauto en esta fase
- [x] No se tocaron: filtros, candidate selector, cache, iconos, auth, taxes
- [x] 27 tests nuevos pasan (`test_quick_order_update_flow.py`)
- [x] 35 tests pricing pasan (regresión OK)
- [x] 12 tests ESI session pasan (regresión OK)
- [x] py_compile OK en todos los archivos

### Archivos creados / modificados en Fase 1

| Archivo | Cambio |
|---------|--------|
| `ui/market_command/quick_order_update_dialog.py` | Nuevo — `QuickOrderUpdateDialog`, `format_price_for_clipboard` |
| `ui/market_command/my_orders_view.py` | Modificado — `on_double_click_item` diferencia columnas, 6 nuevos helpers |
| `tests/test_quick_order_update_flow.py` | Nuevo — 27 tests |

---

## 1. Resumen

Cuando el usuario hace doble click sobre la celda **TIPO** (SELL/BUY) de una orden en Mis Pedidos, la app debe:

1. Identificar la orden seleccionada (type_id, order_id, side, precio actual).
2. Calcular el precio recomendado para superar al mejor competidor (ya calculado y disponible en `analysis.competitor_price`).
3. Abrir el mercado in-game del ítem (reutilizando el flujo existente).
4. Copiar el precio recomendado al portapapeles.
5. Mostrar un popup con toda la información y los botones de acción.
6. Opcionalmente (Fase 2+): intentar automatización de ventana EVE con delays configurables.

El doble click sobre la columna **ÍTEM** (columna 0) conserva el comportamiento actual (abrir mercado).

---

## 2. Flujo deseado

```
Usuario hace doble click sobre celda TIPO (col 1)
          │
          ▼
on_double_click_item() detecta item.column() == 1
          │
          ▼
_get_order_from_row(table, row) → OpenOrder
          │
          ▼
build_order_update_recommendation(order, order.analysis)
          │           ─────────────────────────────────
          │           Usa analysis.competitor_price
          │           (ya excluye mis propias órdenes)
          │           Calcula tick por rango de precio
          │           Recomienda ±1 tick sobre competidor
          ▼
QuickOrderUpdateDialog(order, recommendation)
          │
          ├─ [Copiar precio]  → clipboard.set(recommended_price)
          ├─ [Abrir mercado]  → ItemInteractionHelper.open_market_with_fallback()
          └─ [Iniciar asistente] → (Fase 2) window_automation (dry_run=True por defecto)
```

---

## 3. Estado actual del código

### 3.1 Doble click en Mis Pedidos

**Archivo:** `ui/market_command/my_orders_view.py`

```python
# En fill_table():
t.itemDoubleClicked.connect(lambda i: self.on_double_click_item(i, t))

# En on_double_click_item():
def on_double_click_item(self, item, t):
    row = item.row()
    # Obtiene type_id de la primera celda con dato
    for col in range(t.columnCount()):
        it = t.item(row, col)
        if it:
            if not tid: tid = it.data(Qt.UserRole)
            if col == 0: name = it.text()
    # Abre mercado para CUALQUIER columna (no diferencia)
    ItemInteractionHelper.open_market_with_fallback(...)
```

**Problema:** No distingue en qué columna se hizo click. La extensión es simple:
añadir `if item.column() == 1:` para disparar el Quick Update.

### 3.2 Datos disponibles por fila

En `fill_table()`, cada celda almacena:

| Col | Header   | Qt.UserRole     | Qt.UserRole+1 |
|-----|----------|-----------------|---------------|
| 0   | ÍTEM     | `type_id`       | `order_id`    |
| 1   | TIPO     | `type_id`       | —             |
| 2–10| resto    | `type_id`       | —             |

Para recuperar una orden: `row_item(row, 0).data(Qt.UserRole+1)` → `order_id` → lookup en `self.all_orders`.

### 3.3 Objeto de orden (`OpenOrder` + `OpenOrderAnalysis`)

**Archivo:** `core/market_models.py`

```python
@dataclass
class OpenOrderAnalysis:
    is_buy: bool
    state: str               # "Liderando", "Superada", "Superada con beneficio"...
    net_profit_per_unit: float
    net_profit_total: float
    margin_pct: float
    best_buy: float          # Mejor precio de compra ABSOLUTO (incluye mis órdenes)
    best_sell: float         # Mejor precio de venta ABSOLUTO (incluye mis órdenes)
    spread_pct: float
    competitive: bool
    difference_to_best: float
    competitor_price: float  # ← CLAVE: mejor precio competidor SIN mis órdenes

@dataclass
class OpenOrder:
    order_id: int
    type_id: int
    item_name: str
    is_buy_order: bool
    price: float
    volume_total: int
    volume_remain: int
    issued: str
    location_id: int
    range: str
    analysis: Optional[OpenOrderAnalysis]
```

### 3.4 Exclusión de propias órdenes — ya implementada

**Archivo:** `core/market_engine.py` — función `analyze_character_orders()`

El motor ya calcula `best_competitor_buy` y `best_competitor_sell` excluyendo
las propias órdenes (detecta coincidencias de precio y cantidad y las resta).
El valor se guarda en `analysis.competitor_price`.

**Conclusión: NO necesitamos reimplementar esto.**

### 3.5 Abrir mercado in-game — ya implementada

**Archivo:** `ui/market_command/widgets.py`

```python
class ItemInteractionHelper:
    @staticmethod
    def open_market_with_fallback(esi_client, char_id, type_id, item_name, feedback_callback=None):
        # Llama a ESIClient.open_market_window(type_id, token)
        # Endpoint: POST /ui/openwindow/marketdetails/?type_id=X
        # Scope: esi-ui.open_window.v1
        # Fallback: copia item_name al portapapeles
```

### 3.6 Función de tick de precios — NO existe

`core/tick_calculator.py` contiene el TickCalculator de ciclos ESS/PvE
(detección de payouts de bounties), completamente diferente.

**Necesario crear:** `core/market_order_pricing.py` con `price_tick(price)`.

### 3.7 Cálculo de estado (LIDERANDO/SUPERADA) — ya implementado

En `market_engine.py`:

```python
# SELL: competitive = True si my_price <= comp_sell + EPSILON
# BUY:  competitive = True si my_price >= comp_buy  - EPSILON
# States: "Liderando", "Liderando (Empate)", "Superada", "Superada con beneficio", etc.
```

Ya disponible en `order.analysis.state` y `order.analysis.competitive`.

---

## 4. Archivos afectados

### Archivos a CREAR (stubs en Fase 0, completar en fases posteriores)

| Archivo | Propósito |
|---------|-----------|
| `core/market_order_pricing.py` | Cálculo de tick y precio recomendado — funciones puras |
| `core/quick_order_update_diagnostics.py` | Generador de reporte de ejecución |
| `ui/market_command/quick_order_update_dialog.py` | Popup de Quick Update (Fase 1) |
| `core/window_automation.py` | Automatización experimental de ventana EVE (Fase 2) |
| `config/quick_order_update.json` | Configuración de delays y feature flags |
| `tests/test_market_order_pricing.py` | Tests de funciones de pricing |
| `tests/test_quick_order_update_flow.py` | Tests de flujo completo (mocks) |

### Archivos a MODIFICAR (Fase 1)

| Archivo | Cambio |
|---------|--------|
| `ui/market_command/my_orders_view.py` | `on_double_click_item()`: añadir rama para col 1; `_get_order_from_row()` helper |

### Archivos a NO TOCAR

- `core/market_engine.py` — análisis de órdenes estable
- `core/market_models.py` — modelos de datos
- `core/auth_manager.py` — autenticación
- `core/esi_client.py` — cliente ESI
- `ui/market_command/widgets.py` — `ItemInteractionHelper` (reutilizar, no modificar)
- `core/market_candidate_selector.py` — filtros y candidatos
- `core/market_orders_cache.py` — caché de órdenes
- Todo lo relacionado con iconos

---

## 5. Diseño de arquitectura

### 5.1 Módulo de pricing (puro, sin dependencias UI)

```python
# core/market_order_pricing.py

def price_tick(price: float) -> float:
    """Tick mínimo de precio EVE según rango."""
    # price < 100          → 0.01
    # 100 <= price < 1K    → 0.10
    # 1K <= price < 10K    → 1.00
    # 10K <= price < 100K  → 10.00
    # 100K <= price < 1M   → 100.00
    # 1M <= price < 10M    → 1_000.00
    # 10M <= price < 100M  → 10_000.00
    # 100M+                → 100_000.00

def recommend_sell_price(competitor_sell: float) -> float:
    """Undercut competidor por un tick."""
    return max(0.01, competitor_sell - price_tick(competitor_sell))

def recommend_buy_price(competitor_buy: float) -> float:
    """Outbid competidor por un tick."""
    return competitor_buy + price_tick(competitor_buy)

def build_order_update_recommendation(order, analysis) -> dict:
    """
    Retorna dict con:
      side, my_price, competitor_price, best_buy, best_sell,
      tick, recommended_price, reason, action_needed
    """
    # Usa analysis.competitor_price directamente (ya excluye mis órdenes)
    # Si analysis.competitive → no hay acción urgente
    # Si no competitive → recomendar ±1 tick sobre competitor_price
```

### 5.2 Detección del doble click (extensión mínima)

```python
# ui/market_command/my_orders_view.py

def on_double_click_item(self, item, t):
    row = item.row()
    col = item.column()

    # Columna TIPO (1) → Quick Order Update
    if col == 1:
        order = self._get_order_from_row(t, row)
        if order and order.analysis:
            self._launch_quick_order_update(order)
        return

    # Columna ÍTEM (0) u otras → comportamiento actual
    tid = None
    name = ""
    for c in range(t.columnCount()):
        it = t.item(row, c)
        if it:
            if not tid: tid = it.data(Qt.UserRole)
            if c == 0: name = it.text()
    if tid:
        ItemInteractionHelper.open_market_with_fallback(...)

def _get_order_from_row(self, table, row) -> OpenOrder | None:
    """Recupera la orden de self.all_orders a partir de la fila de la tabla."""
    name_item = table.item(row, 0)
    if not name_item:
        return None
    order_id = name_item.data(Qt.UserRole + 1)
    return next((o for o in self.all_orders if o.order_id == order_id), None)

def _launch_quick_order_update(self, order):
    """Abre el dialog de Quick Order Update."""
    from ui.market_command.quick_order_update_dialog import QuickOrderUpdateDialog
    from core.market_order_pricing import build_order_update_recommendation
    rec = build_order_update_recommendation(order, order.analysis)
    dlg = QuickOrderUpdateDialog(order, rec, parent=self)
    dlg.show()  # No bloquea la UI
```

### 5.3 Popup (Fase 1)

```python
# ui/market_command/quick_order_update_dialog.py

class QuickOrderUpdateDialog(QDialog):
    """
    Ventana de Quick Order Update. No bloquea la UI principal (.show() no .exec()).
    
    Muestra:
      - Ítem, tipo (SELL/BUY), Order ID, Volume Remain
      - Mi precio actual
      - Mejor precio competidor (excluye mis órdenes)
      - Precio recomendado + tick
      - Estado actual (Liderando / Superada)
      - Razón de la recomendación
    
    Botones:
      - Copiar precio  → clipboard.setText(str(recommended_price))
      - Abrir mercado  → ItemInteractionHelper.open_market_with_fallback()
      - Iniciar asistente → (Fase 2, desactivado inicialmente)
      - Cerrar
    """
```

### 5.4 Automatización experimental (Fase 2 — stub, sin conectar)

```python
# core/window_automation.py

class EVEWindowAutomation:
    """
    Automatización experimental de la ventana del cliente EVE.
    
    DESACTIVADO POR DEFECTO (enabled=False en config).
    
    Funciona sólo si pywinauto o pyautogui están disponibles.
    No introduce dependencias nuevas como requisito — usa importación condicional.
    
    Flujo:
      1. find_eve_window() → busca ventana por título
      2. focus_eve_window() → activa la ventana
      3. wait(focus_delay_ms)
      4. (Fase 3) send_open_modify_order() → Shift+Click o tecla de atajo
      5. wait(open_modify_delay_ms)
      6. (Fase 3) paste_price() → clipboard → Ctrl+A, Ctrl+V
      7. wait(paste_delay_ms)
      8. LOG + report (nunca confirmar sin acción explícita del usuario)
    """
    
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.dry_run = config.get("dry_run", True)
        self.confirm_required = config.get("confirm_required", True)
        ...
    
    def execute(self, order_data: dict, recommended_price: float) -> dict:
        """
        Ejecuta el flujo de automatización.
        Retorna dict de diagnóstico con steps_executed, errors, etc.
        """
        if not self.enabled:
            return {"status": "disabled", "steps": [], "errors": []}
        if self.dry_run:
            return {"status": "dry_run", "steps": ["logged only"], "errors": []}
        ...
```

### 5.5 Configuración

```json
// config/quick_order_update.json (por defecto)
{
  "enabled": false,
  "dry_run": true,
  "confirm_required": true,
  "open_market_delay_ms": 800,
  "focus_client_delay_ms": 500,
  "paste_delay_ms": 300,
  "restore_clipboard_after": true,
  "client_window_title_contains": "EVE"
}
```

### 5.6 Diagnóstico

```python
# core/quick_order_update_diagnostics.py

def format_quick_update_report(data: dict) -> str:
    """
    Genera reporte de texto:
    
    EVE iT — QUICK ORDER UPDATE REPORT
    [ORDER]   item, type_id, order_id, side, volume_remain, my_price
    [MARKET]  best_buy, best_sell, competitor_price, spread, state
    [RECOMMENDATION]  tick, recommended_price, reason, action_needed
    [ACTIONS] market_open, clipboard, popup, automation, dry_run, window_focused
    [CONFIG]  delays, confirm_required, client_window_title
    [ERRORS]  lista
    [NOTES]   lista
    """
```

---

## 6. Fases de implementación

### Fase 0 — Stubs y pricing (ESTE COMMIT)

- [x] `core/market_order_pricing.py` — funciones puras de precio y tick
- [x] `core/quick_order_update_diagnostics.py` — generador de reporte
- [x] `tests/test_market_order_pricing.py` — tests de pricing
- [x] `.workflow/quick_order_update_design.md` — este documento
- [ ] NO se conecta nada a la UI todavía

### Fase 1 — Popup y conexión al doble click

**Entregables:**
- `ui/market_command/quick_order_update_dialog.py`
- Modificar `on_double_click_item()` en `my_orders_view.py`
- Añadir `_get_order_from_row()` y `_launch_quick_order_update()`
- Copiar precio al portapapeles
- Botón "Abrir mercado" reutiliza `ItemInteractionHelper`
- Tests de flujo con mocks

**Criterios de aceptación Fase 1:**
- Doble click en ÍTEM → comportamiento anterior sin cambios
- Doble click en TIPO → popup con datos correctos
- Copiar precio funciona
- Abrir mercado funciona
- El popup no bloquea la UI

### Fase 2 — Automatización experimental (opt-in)

**Entregables:**
- `core/window_automation.py`
- `config/quick_order_update.json`
- Botón "Iniciar asistente" en el popup (activado solo si `enabled=True` en config)
- `dry_run=True` por defecto — nunca ejecuta sin flag explícito
- Logs detallados de cada step

**Requisitos de seguridad Fase 2:**
- `enabled=False` por defecto (opt-in manual en JSON)
- `confirm_required=True` siempre hasta Fase 3
- Nunca pulsar el botón final de confirmación en EVE sin acción explícita
- Cancela si: no encuentra ventana EVE, order_id inválido, precio <= 0
- Usa importación condicional de pywinauto/pyautogui (no romper sin ellos)

### Fase 3 — Perfiles de timing y afinado

**Entregables:**
- Presets: rápido / normal / lento / custom
- UI de configuración de delays en el popup o en Settings
- Validaciones de precio absurdo (spread > umbral configurable)
- `tests/test_quick_order_update_flow.py` completo

### Fase 4 — Diagnóstico integrado

**Entregables:**
- Reporte de ejecución al terminar (dialog o log)
- Historial de actualizaciones (opcional, en memoria)
- Métricas: órdenes actualizadas, errores, tiempo promedio

---

## 7. Riesgos técnicos

| Riesgo | Severidad | Mitigación |
|--------|-----------|------------|
| Cliente EVE no enfocado al activar automatización | Alta | Verificar ventana antes, cancelar si no está activa |
| CCP cambia la UI del cliente | Alta | Feature flag, dry_run por defecto, no hardcodear posiciones de pixel |
| El usuario mueve el ratón durante automatización | Media | Usar keys en lugar de clicks cuando sea posible |
| Lag de red hace que el mercado tarde en abrir | Media | Delays configurables, no asumir tiempo fijo |
| Tick de precio incorrecto para items exóticos | Baja | Función configurable, override manual en popup |
| Doble click accidental en TIPO dispara el flujo | Baja | El popup tiene botón Cerrar, no automatiza sin acción explícita |
| `competitor_price` = 0 (no hay competidores) | Baja | Manejar explícitamente: recomendar mantener precio |
| `competitor_price` = 999...999 (sentinel) | Baja | Manejar como "sin competencia" |
| Sesión ESI expirada al abrir mercado | Baja | `ItemInteractionHelper` ya maneja esto con auto-refresh |

---

## 8. Plan de pruebas

### Unit tests — `tests/test_market_order_pricing.py`

```
test_price_tick_ranges                 # cada rango devuelve tick correcto
test_sell_recommend_undercut           # 12550 → 12540 (tick 10)
test_buy_recommend_outbid              # 15740000 → 15750000 (tick 10000)
test_sell_already_leading              # action_needed=False
test_buy_already_leading               # action_needed=False
test_no_competitor_sell                # competitor_sell=0 → mantener precio
test_no_competitor_buy                 # competitor_buy=0 → mantener precio
test_recommended_price_not_negative    # nunca devuelve precio <= 0
test_tick_boundary_exact               # precio en exactamente el límite (100.0)
test_full_recommendation_sell          # build_order_update_recommendation SELL
test_full_recommendation_buy           # build_order_update_recommendation BUY
```

### Integration tests — `tests/test_quick_order_update_flow.py` (Fase 1)

```
test_double_click_tipo_column_dispatches_update    # col 1 dispara quick update
test_double_click_item_column_opens_market         # col 0 no cambia
test_get_order_from_row_finds_correct_order        # helper encuentra orden
test_get_order_from_row_unknown_order_id           # devuelve None
test_dialog_opens_on_valid_order                   # mock dialog
test_clipboard_set_correctly                       # precio correcto copiado
```

---

## 9. Decisiones pendientes

| Decisión | Opciones | Recomendación |
|----------|----------|---------------|
| ¿Confirmar si no hay `competitor_price`? | A) Mostrar popup de todas formas. B) No mostrar si no hay acción. | A — siempre mostrar, informar de la situación |
| Formato del precio en clipboard | `"12540"` vs `"12.540,00"` | `"12540"` — sin separadores, compatible con EVE |
| ¿El popup bloquea la UI? | `.exec()` (modal) vs `.show()` (no modal) | `.show()` — no modal, el usuario puede seguir usando la app |
| ¿Mostrar tick en el popup? | Sí / No | Sí — ayuda al usuario a entender el cálculo |
| ¿Automatización usa pywinauto o pyautogui? | pywinauto (más robusto en Windows) / pyautogui (más simple) | pywinauto si disponible, pyautogui como fallback, ninguno como mínimo |
| ¿Config de automatización en JSON o en Settings UI? | JSON por ahora / UI en Fase 3 | JSON en Fase 2, UI en Fase 3 |
| ¿El popup muestra el reporte de diagnóstico? | Sí / Solo en log | En el popup hay botón opcional "Ver reporte"; siempre en log |

---

## 10. Recomendación de implementación por fases

**Implementar en orden estricto, sin saltarse fases:**

1. **Fase 0 (ahora):** Stubs de pricing + tests. Sin tocar UI. Sin riesgo.
2. **Fase 1 (siguiente PR):** Popup + conexión al doble click en TIPO. Confirmar que funciona manualmente en la app antes de continuar.
3. **Fase 2 (PR separado):** Automatización experimental con `enabled=False`. Probar solo activándola manualmente en JSON.
4. **Fase 3 (PR separado):** Perfiles, UI de configuración, validaciones extra.
5. **Fase 4 (PR separado):** Diagnóstico integrado en popup.

**Rationale:** El valor máximo con el mínimo riesgo viene de Fase 1 (popup + clipboard + abrir mercado). Las fases 2–4 son mejoras progresivas. Si Fase 2 resulta frágil (cambia UI de EVE), las fases 1, 3 y 4 siguen funcionando sin cambios.

---

## Apéndice A — Estructura de columnas en Mis Pedidos

```
Col 0: ÍTEM       → type_id en UserRole, order_id en UserRole+1
Col 1: TIPO       → "SELL"/"BUY", type_id en UserRole  ← PUNTO DE ENTRADA
Col 2: PRECIO     → mi precio actual
Col 3: PROMEDIO   → WAC (coste promedio)
Col 4: MEJOR      → ref_v: best_buy (si BUY) o best_sell (si SELL) — ABSOLUTO
Col 5: TOTAL      → volume_total
Col 6: RESTO      → volume_remain
Col 7: SPREAD     → spread_pct
Col 8: MARGEN     → margin_pct
Col 9: PROFIT     → net_profit_total
Col 10: ESTADO    → analysis.state
```

## Apéndice B — Campos de OpenOrderAnalysis relevantes

```python
analysis.competitor_price  # mejor precio competidor (excluye mis órdenes) ← USAR ESTE
analysis.best_buy          # mejor compra ABSOLUTA (puede ser mía)
analysis.best_sell         # mejor venta ABSOLUTA (puede ser mía)
analysis.competitive       # bool: ¿estoy liderando?
analysis.state             # "Liderando", "Superada", "Superada con beneficio"...
analysis.margin_pct        # margen neto %
analysis.spread_pct        # spread %
```

## Apéndice C — Función de tick de precios EVE

```
Precio          Tick
< 100           0.01
100–999         0.10
1K–9K           1.00
10K–99K         10.00
100K–999K       100.00
1M–9M           1,000.00
10M–99M         10,000.00
100M+           100,000.00
```

Basado en la mecánica de mercado de EVE Online (fuente: observación empírica de la comunidad).
CCP no documenta el tick oficialmente pero este es el comportamiento estándar del cliente.
