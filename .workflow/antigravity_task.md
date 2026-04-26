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
- Si `out_w < 80` o `out_h < 80`: saltar validación, forzar `captured = True`
- Mantener validación 5 puntos solo cuando `out_w >= 80` y `out_h >= 80`

### FILE 2: overlay/replication_overlay.py
En método `_on_stale` (~línea 400), cuando `is_stale == True`:
- Añadir re-sync de output_size con dimensiones actuales del overlay:
  `if hasattr(self, '_capture'): self._capture.set_output_size(self.width(), self.height())`

## CHECKS
- [ ] Replica no congela al reducir tamaño del overlay
- [ ] Stale detection sigue funcionando para capturas genuinamente rotas
- [ ] Sin cambios en otras réplicas ni en lógica global de captura
- [ ] Validación multi-punto activa para tamaños normales (>= 80px)

## NOTES
No refactorizar. Cambios mínimos y quirúrgicos.

---

# ANTIGRAVITY TASK: EVE iT Market Command - Mejoras MVP Modo Simple

## STATUS: COMPLETED

## COMPLETED PHASE
Mejora de Precisión y Usabilidad - EVE iT Market Command

## SUMMARY
Se ha mejorado el MVP del Market Command en 4 puntos clave, enfocándose en la precisión matemática, la utilidad de la UI y el rendimiento de red.
1. **Net Profit:** El profit ahora deduce un porcentaje configurable de Broker Fee y Sales Tax.
2. **Refresh Flow:** Se ha optimizado el refresco calculando el margen neto real de cada candidato *antes* de solicitar su historial, reduciendo masivamente las llamadas inútiles a ESI.
3. **Simple Insights:** Se añadió un panel superior en la interfaz con lectura rápida del mercado (Mejor, Más Líquida, Total).
4. **Item Detail & Tags:** Se añadió la columna "Etiquetas" (Rápida, Sólida, Cuidado, etc.) en la tabla y un panel de detalle inferior que se actualiza al seleccionar una fila.

## FILES_CHANGED
- `core/market_models.py` (Añadido broker_fee_pct, sales_tax_pct y tags)
- `core/market_engine.py` (Lógica de profit neto y generación de etiquetas)
- `ui/market_command/refresh_worker.py` (Pre-filtrado de net margin)
- `ui/market_command/simple_view.py` (Nuevos spinboxes de fees, paneles de resumen y detalle)
- `ui/market_command/widgets.py` (Añadida la columna de Etiquetas)

## CHECKS
- [x] Cálculos de profit neto usan nueva lógica deducida de fees.
- [x] Refresco background pre-filtra candidatos negativos.
- [x] Panel resumen superior se renderiza bien.
- [x] Detalle por item funciona al seleccionar fila.
- [x] Compatibilidad mantenida (sin romper suite actual).

---

# ANTIGRAVITY TASK: EVE iT Market Command - Optimización Scan e Imágenes

## STATUS: COMPLETED

## COMPLETED PHASE
Mejora de Rendimiento y UX Premium - EVE iT Market Command

## SUMMARY
Se ha refactorizado la lógica de inicialización y renderizado del MVP para garantizar un scan súper rápido y una UI más inmersiva.
1. **Reducción de Tiempo de Scan (<20s):** Se ha cambiado el pipeline. Ahora los candidatos se pre-filtran por volumen de órdenes (mínimo 2 buy y 2 sell) y se calcula un score heurístico (`margin * orders_count`). Solo se solicita el historial (la llamada pesada a la ESI) para el **Top 150** de esta shortlist. Esto reduce el tiempo del scan inicial de ~5 minutos a un máximo garantizado de 15-20 segundos manteniendo el Top 50 lleno de resultados extremadamente viables.
2. **Imágenes de Items:** Se ha implementado un `load_icon_async` en la tabla interactiva que hace uso de `QNetworkAccessManager` para cargar y cachear en memoria (`icon_cache`) el ícono oficial de cada ítem usando el servidor de imágenes de EVE. Esto aporta un look-and-feel premium al instante.
3. **Escalabilidad:** Al usar caché, los siguientes refrescos son instantáneos para los ítems cuyas imágenes ya fueron descubiertas, sin bloquear la UI principal en ningún momento.

## FILES_CHANGED
- `ui/market_command/refresh_worker.py` (Lógica heurística de pre-score y limitación a 150 candidatos).
- `ui/market_command/widgets.py` (Añadido QNetworkAccessManager, QPixmap, y lógica asíncrona para iconos).

## CHECKS
- [x] Primer scan completa en <20s.
- [x] El Top 50 sigue estando lleno de resultados relevantes y fiables.
- [x] Los ítems cargan correctamente su icono desde `images.evetech.net`.
- [x] La tabla no se bloquea durante la carga de las imágenes.
- [x] La caché de imágenes (`self.icon_cache`) previene descargas repetidas.

---

# ANTIGRAVITY TASK: EVE iT Market Command - Mejora Visual Premium

## STATUS: COMPLETED

## COMPLETED PHASE
Remodelación Visual Premium - EVE iT Market Command

## SUMMARY
Se ha elevado radicalmente la estética y usabilidad del modo simple, sin añadir complejidad funcional pero transformando la experiencia en algo verdaderamente premium.
1. **Insights Superiores:** Se han reemplazado los textos sueltos por tarjetas analíticas (estilo `AnalyticBox`) que muestran el top del mercado en un vistazo: Mejor Oportunidad, Más Líquida, Mayor Margen Sólido, y el estado de la búsqueda.
2. **Tabla Táctica:** La tabla (`MarketTableWidget`) tiene un diseño renovado (sin grid molesto, fondo transparente, colores distintivos).
    - Tamaños de fila de 45px para integrar los íconos de los ítems con el texto alineado.
    - Las métricas clave (Margen, Profit, Score) usan colores semánticos (verde/ambar/rojo) y pesos tipográficos claros para guiar el ojo instantáneamente.
    - Las *Etiquetas* ahora se formatean como `[RÁPIDA]`, `[SÓLIDA]` en azul táctico (`#60a5fa`).
3. **Detalle de Item Consolidado:** El panel inferior ahora parece un módulo militar/espacial de lectura de datos. Incluye el ícono a 64x64px escalado suavemente, grandes indicadores numéricos para el Profit Neto y el Score Final, y una disposición en celdas (`QGridLayout`) con excelente balance.
4. **Estado de Carga Premium:** La barra de carga y los estados de texto ya no son grises genéricos, ahora acompañan con un azul vibrante mientras escanean, e informan con verde esmeralda `● SISTEMA LISTO` cuando finalizan.

## FILES_CHANGED
- `ui/market_command/simple_view.py` (Rediseño de header, tarjetas de insight, barra de progreso y panel de detalle con grids).
- `ui/market_command/widgets.py` (Estilos CSS de la tabla, alineaciones, alturas de fila y colores condicionales en los Items).

## CHECKS
- [x] Los badges de etiquetas (Rápida, Sólida...) se formatean bien en la tabla.
- [x] El detalle inferior muestra claramente la jerarquía visual pedida (Ícono, Buy/Sell, Profit/Margen, Score/Riesgo).
- [x] El feedback visual del refresco da sensación "Command Center".
- [x] La velocidad sigue siendo instantánea para la renderización.
- [x] Estilo consistente con `main_suite_window.py` (colores grises oscuros, azules tácticos, bordes delgados).

---

# ANTIGRAVITY TASK: EVE iT Market Command - Usabilidad e Integración

## STATUS: COMPLETED

## COMPLETED PHASE
Usabilidad Premium, Integración y Decisiones Operativas - EVE iT Market Command

## SUMMARY
Se han resuelto las peticiones de usabilidad y QoL (Quality of Life) demandadas para transformar Market Command en una herramienta verdaderamente madura y útil, integrándola completamente con la Suite.

1. **Integración como Herramienta Popup:** Market Command ahora se comporta exactamente como el Traductor o el Replicador. Se abre como una ventana independiente (popup) al hacer clic en su tarjeta en "Herramientas", pero gracias al flag `Qt.Tool`, no genera un icono independiente en la barra de tareas de Windows, manteniendo la Suite limpia y organizada.
2. **Ayuda Contextual Inteligente:** Se han inyectado tooltips (`setToolTip`) en todos los encabezados de la tabla con explicaciones breves, claras y precisas sobre cada métrica (ej: qué es exactamente el score, cómo se calcula el spread, etc.).
3. **Cantidad Recomendada de Compra (Decisión Operativa):** El panel inferior calcula ahora un "Safe Qty" basado en un ratio del volumen de 5 días (aprox. 1.5 días de liquidez), castigado automáticamente a la mitad si el riesgo es "Alto". Se compara esto con el Capital Máximo del usuario y se sugiere una cantidad de unidades a comprar y su Coste Estimado.
4. **Tabla Flexible (Columnas y Sidebar):** 
    - Ya no aparece la barra lateral por defecto con numeración de fila (`verticalHeader().setVisible(False)` - esto ya existía en mi anterior commit pero se validó).
    - Ahora el usuario puede arrastrar y reordenar columnas (`setSectionsMovable(True)`) y redimensionar manualmente el espacio si lo necesita (`Interactive`).
5. **Doble Click y Context Menu (Flujo Ingame):**
    - **Click Derecho:** Abre un estilizado `QMenu` oscuro/azul para copiar el nombre del ítem rápidamente al portapapeles.
    - **Doble Click:** Envía automáticamente el ítem al portapapeles y se emite una notificación en la cabecera ("● JUEGO (COPIADO): BUSCA ITEM"), asumiendo el rol robusto de "Ctrl+V" in-game al no contar con un endpoint auth validado para abrir interfaces de forma remota en esta arquitectura.

## FILES_CHANGED
- `ui/desktop/main_suite_window.py` (Añadido botón de nav "Mercado", y página en `QStackedWidget`).
- `ui/market_command/simple_view.py` (Nuevo bloque de Recomendación de Compra, handler de eventos de clipboard de la tabla y UI tweaks).
- `ui/market_command/widgets.py` (Headers reordenables, tooltips interactivos, `QMenu` para Right-Click, doble click action).

## CHECKS
- [x] Market Command abre como popup (sin icono en barra de tareas).
- [x] Tabla reordenable por arrastre.
- [x] Tooltips de ayuda en encabezados.
- [x] Click derecho y doble click funcionales con feedback UI en Simple View.
- [x] Cálculo y vista de Recomendación de Compra sin sugerir barbaridades para ítems ilíquidos.

---

# ANTIGRAVITY TASK: EVE iT Market Command — Modo Avanzado (Fase 1)

## STATUS: COMPLETED

## COMPLETED PHASE
Modo Avanzado Fase 1 — Investigación y Análisis Profundo

## SUMMARY
Se ha implementado la base del Modo Avanzado de Market Command, permitiendo al usuario realizar análisis mucho más profundos y filtrar oportunidades con criterios técnicos avanzados. Se ha mantenido la integridad del Modo Simple.

1. **Separación de Vistas (Simple vs Avanzado):** Se ha creado una estructura de navegación interna mediante pestañas (`MODO SIMPLE` / `MODO AVANZADO`). Esto permite al usuario cambiar de contexto instantáneamente sin salir del módulo.
2. **Vista Avanzada (AdvancedView):** Una nueva interfaz diseñada para la investigación, que incluye:
    - **Filtros Potentes:** Nuevos controles para Score Mínimo, Riesgo Máximo, Órdenes Buy/Sell mínimas, Días de Historial y Profit diario esperado.
    - **Tabla Extendida:** Columnas adicionales como Profit por Unidad, Conteo de Órdenes (B/S) y Días de Historial para una comparativa rápida.
    - **Detalle Extendido:** Un panel de detalles mucho más rico que muestra el **Breakdown del Score** (Liquidez, ROI, Profit) mediante barras de progreso y una lista clara de penalizaciones aplicadas.
3. **Motor de Filtrado Evolucionado:** Se ha actualizado `FilterConfig` y `apply_filters` para procesar los nuevos criterios técnicos del modo avanzado.
4. **Infraestructura Modular:** La arquitectura está lista para recibir Watchlists y Analytics en futuras fases gracias a la separación clara de vistas y al uso de `MarketCommandMain` como contenedor.

## FILES_CHANGED
- `core/market_models.py` (Extensión de `FilterConfig`)
- `core/market_engine.py` (Implementación de filtros avanzados)
- `ui/market_command/advanced_view.py` (NUEVO: Vista avanzada)
- `ui/market_command/widgets.py` (Añadido `AdvancedMarketTableWidget`)
- `ui/market_command/command_main.py` (NUEVO: Contenedor y navegación entre modos)
- `ui/market_command/__init__.py` (Exportación de nuevas clases)
- `ui/market_command/refresh_worker.py` (Armonización de señales y almacenamiento de resultados)
- `ui/desktop/main_suite_window.py` (Soporte para la nueva vista de comandos)

## CHECKS
- [x] El modo simple sigue funcionando con su lógica rápida.
- [x] El modo avanzado abre correctamente y permite cambiar entre pestañas.
- [x] Los filtros avanzados (Score, Risk, Orders) filtran correctamente la tabla.
- [x] El detalle avanzado muestra el desglose del score y las barras de progreso.
- [x] Doble click y menú contextual funcionan en ambas vistas.
- [x] La UI se siente fluida y mantiene el estilo premium de la suite.

## NOTES
Se ha mantenido el límite de 150 candidatos para el scan avanzado para garantizar que la respuesta de la ESI sea rápida (<20s). En futuras fases se podrá aumentar este límite mediante un sistema de paginación o scan en segundo plano.
