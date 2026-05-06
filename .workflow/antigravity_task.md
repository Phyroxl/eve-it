# Antigravity Task — EVE Client Lifecycle, Translator HUD Visual Clon & Shared Window Controls

**Fecha:** 2026-05-06
**Commit:** FIX: Repair EVE client lifecycle translator HUD visual clone and shared window controls

---

## Resumen del problema

Se detectaron bugs e implementaciones incompletas en SALVA Suite:

1. Ciclo de vida de replicas del Replicador: logs insuficientes, no extrae character_name.
2. Ocultacion de Chat Translator y HUD Overlay: parpadeos al cambiar de ventana.
3. Toggle de retratos en Chat Translator no actualizaba burbujas existentes.
4. Botones cerrar/minimizar inconsistentes entre ventanas.
5. Visual Clon con tamano incorrecto (450x800 en lugar de 450x1000).
6. Visual Clon sin verificacion de hash ni deteccion de EVE abierto.
7. HUD Overlay con estilo de botones diferente al resto de la suite.

---

## Archivos modificados

- ui/common/custom_titlebar.py: Botones 20x18, colores identicos a _TitleBar de main_suite_window.py.
- ui/desktop/main_suite_window.py: setFixedSize(450, 1000) para Visual Clon.
- translator/chat_overlay.py: _toggle_portraits actualiza burbujas existentes; _check_eve_foreground usa PID via should_show_overlays(); estilos BTN canonicos.
- overlay/overlay_app.py: _check_eve_foreground usa PID via should_show_overlays(); BTN_NEON/BTN_RED canonicos.
- overlay/replication_overlay.py: _extract_character_name(); logs CLIENT CLOSED/REPLICA AUTO CLOSED/CLIENT REOPENED/REPLICA AUTO RELAUNCHED/SKIP RELAUNCH MANUAL CLOSE/SKIP DUPLICATE REPLICA.
- core/visual_clon_service.py: _md5() verificacion hash; is_eve_running() deteccion cliente abierto; logs VISUAL CLON SOURCE/DEST/BACKUP CREATED/COPY FILE/VERIFY HASH OK-FAIL/WARNING EVE RUNNING.

---

## Solucion aplicada

### Ocultacion inteligente (items 2, 8)
Raiz del problema: `title == ""` como catch-all para ventanas propias fallaba con apps externas frameless.
Solucion: usar `should_show_overlays(fg_hwnd, eve_hwnds)` de win32_capture.py (ya existia, usa GetWindowThreadProcessId por PID). Cache de find_eve_windows() cada 2 s.

### Retratos en Chat Translator (item 3)
_toggle_portraits() ahora itera self._bubbles y llama _portrait_lbl.setVisible(checked).

### Botones unificados (item 5)
CustomTitleBar: botones 20x18, fondo #0f172a, borde 1px solid #1e293b, color #94a3b8.
Identico a _TitleBar en main_suite_window.py.

### Visual Clon tamano (item 6)
setFixedSize(450, 800) -> setFixedSize(450, 1000).

### Visual Clon copia robusta (item 9)
Hash MD5 post-copia, deteccion EVE abierto, logs detallados.
core_user_*.dat NO se copia: es por cuenta, no por personaje.

### Ciclo de vida replicas (item 1)
_save_replica_state() extrae character_name del titulo de ventana.
Logs: CLIENT CLOSED DETECTED, REPLICA AUTO CLOSED, CLIENT REOPENED DETECTED, REPLICA AUTO RELAUNCHED, SKIP RELAUNCH MANUAL CLOSE, SKIP DUPLICATE REPLICA.

---

## Limitaciones conocidas

1. Links EVE en mensajes: EVE elimina hiperlinks al escribir en chatlogs. Solo texto plano llega al ChatReader. El sender ya tiene link a zKillboard.
2. Pegado automatico de traduccion: se copia al portapapeles (seguro). Auto-paste directo interfiere con el Replicador y puede violar ToS.
3. Visual Clon desplazamiento de coordenadas: si el perfil origen fue grabado con diferente resolucion/DPI, las coordenadas binarias en core_char_*.dat estaran desfasadas. El formato binario de CCP no esta documentado publicamente.
4. HUD Overlay standalone: el import de should_show_overlays esta dentro de try/except para evitar ImportError si se ejecuta sin el paquete overlay en sys.path.

---

## Session 2 — Overlay visibility, portraits, Visual Clone resize, Intel Alert

**Fecha:** 2026-05-06
**Commit:** FIX: Improve overlay visibility portraits visual clone and add intel alert

### Cambios aplicados

#### 1. Chat Translator — velocidad de ocultacion (75 ms)
- `translator/chat_overlay.py`: timer 500 ms → 75 ms; debounce threshold >= 4 → >= 2 ticks.
  Resultado: ocultacion en ~150 ms, igual que el Replicador.

#### 2. HUD ISK Tracker — ocultacion al perder foco
- `overlay/overlay_app.py`: mismo cambio de timer 500 → 75 ms y debounce 4 → 2.
  La ventana ahora se oculta y reaparece al mismo ritmo que el Replicador.

#### 3. Visual Clone — 900x675 con layout 2 columnas
- `ui/desktop/main_suite_window.py`: setFixedSize(450, 1000) → setFixedSize(900, 675).
- `ui/tools/visual_clon_view.py`: _setup_ui() reescrito con QHBoxLayout.
  Columna izquierda fija 370 px: carpeta + source + seguridad.
  Columna derecha stretch: targets + info de secciones.

#### 4. Chat Translator — portraits
- `utils/eve_api.py`: resolve_character_id() ya NO cachea None en disco.
  - Exitos: cachados en disco indefinidamente.
  - Fallos ESI definitivos (4xx / not found): TTL 30 min en memoria (_FAILED_NAMES).
  - Errores de red (5xx / timeout): no se cachean, se reintenta la proxima vez.
  - _load_cache() filtra entradas None/invalidas al iniciar.
  - _normalize_sender() elimina caracteres de control/invisibles del chatlog EVE.
- `translator/chat_overlay.py`: _start_portrait_load() normaliza sender antes de ESI;
  añade logging DEBUG PORTRAIT *; tamaño pedido 64 px (antes 32) para mejor calidad;
  portrait label sin border-radius (cuadrado).

#### 5. Bordes cuadrados
- `translator/chat_overlay.py`: eliminados todos los border-radius de los QStyleSheet del overlay.
- `overlay/overlay_app.py`: border-radius: 8px → 0px en el contenedor principal.

#### 6. Intel Alert — nueva herramienta
- `core/intel_alert_service.py` (nuevo): IntelAlertConfig (persistente en config/intel_alert.json),
  IntelAlertService (thread), IntelEvent.
  Monitorea chatlogs: Local (piloto nuevo = alerta) + canales custom (watchlist en texto).
  Cooldown anti-spam configurable. Sonido: winsound.MessageBeep → QApplication.beep() fallback.
- `ui/tools/intel_alert_window.py` (nuevo): UI frameless 620x560.
  Lista segura (whitelist), lista vigilancia (watchlist), toggle Activar/Detener,
  historial de eventos codificado por color, test sonido, reset sesion.
- `ui/desktop/main_suite_window.py`: card Intel Alert en Tools grid fila 1 col 2;
  handler _on_intel_alert_clicked().

### Archivos modificados en Session 2
- utils/eve_api.py
- translator/chat_overlay.py
- overlay/overlay_app.py
- ui/desktop/main_suite_window.py
- ui/tools/visual_clon_view.py
- core/intel_alert_service.py (nuevo)
- ui/tools/intel_alert_window.py (nuevo)

---

## Session 3 — Intel Alert v2, portraits and overlay polish

**Fecha:** 2026-05-06
**Commit:** FIX: Complete intel alert distance controls and translator portraits

### Completado

#### Intel Alert v2
- source_mode Local/Intel/Both selector en UI y en servicio.
- intel_channels: lista editable de canales Intel custom; fallback a ficheros con 'intel' si está vacía.
- current_system + max_jumps (QSpinBox 0-10) + alert_unknown_distance checkbox.
- Arquitectura distance: EveMapService singleton (core/eve_map_service.py). Sin SDE = distance_jumps() siempre None. extract_system_from_text() heurística (null-sec pattern + proper noun). distance_jumps(X,X)=0.
- Clasificación: safe / watchlist / unknown. Funciones puras: classify_pilot, should_alert, parse_intel_message.
- Cooldown key: source:pilot:system (antes solo pilot).
- alert_on_watchlist toggle: watchlist no suena si está off.
- update_config() resetea readers si cambia source/channels.
- IntelEvent ampliado: classification, source, system, jumps.
- Historial: [HH:MM:SS] [LOCAL/WATCH/INTEL] [sistema] [Xj] piloto — mensaje.
- Titlebar: CustomTitleBar compartida; closeEvent llama hide() en vez de destroy.
- Nota SDE visible en UI.

#### Portraits Chat Translator
- eve_icon_service.py: añadido redirect policy NoLessSafeRedirectPolicy (EVE image server usa redirects).
- Logging: PORTRAIT DOWNLOAD OK / PORTRAIT DOWNLOAD ERROR / PORTRAIT PIXMAP NULL / PORTRAIT SET OK.
- Portrait label initial style: eliminado border-radius:3px (ahora square).
- log PORTRAIT SET OK confirma que el pixmap llegó al widget.

#### Square borders
- chat_overlay.py: portrait label sin border-radius.
- overlay_app.py: container ya tenía border-radius:0px. Comentario stale corregido (4×500ms → 2×75ms).

#### Nuevo: core/eve_map_service.py
- EveMapService singleton con API extensible.
- is_available()=False, distance_jumps()=None (excepto same-system=0).
- extract_system_from_text(): heurística null-sec pattern + fallback proper-noun.
- TODO claro para integrar BFS con SDE.

### Tests añadidos
- tests/test_intel_alert_v2.py: 32 tests, todos pasan.
  - config_round_trip, classify_*, should_alert_*, parse_intel_*, cooldown_key_*, source_*_matches_*, normalize_sender_*

### Archivos modificados
- core/intel_alert_service.py (reescrito)
- ui/tools/intel_alert_window.py (reescrito, usa CustomTitleBar)
- core/eve_icon_service.py (redirect policy + logging portraits)
- translator/chat_overlay.py (portrait label square + log PORTRAIT SET OK)
- overlay/overlay_app.py (comentario stale corregido)

### Archivos nuevos
- core/eve_map_service.py
- tests/test_intel_alert_v2.py

### Limitaciones conocidas
- Distancias por saltos: distance_jumps() siempre None (sin SDE). alert_unknown_distance controla el comportamiento.
- Local Intel chat: el watcher detecta pilotos que HABLAN en Local, no toda la lista local (EVE no escribe toda la lista en el chatlog, solo mensajes).
- Portraits: si ESI /universe/ids/ falla o el personaje no existe en ESI, el retrato no carga. TTL 30min en memoria para reintentar.

---

## Session 4 — HUD visibility fix, square corners DWM, Intel Alert reliability and sound

**Fecha:** 2026-05-06
**Commit:** FIX: Repair HUD visibility portraits square overlays and Intel Alert reliability

### Problemas diagnosticados y resueltos

#### 1. HUD/Overlay — excepción silenciosa en _check_eve_foreground
- Causa: `except Exception: pass` tragaba cualquier ImportError o fallo en should_show_overlays.
- Fix: `except Exception as _exc: logger.debug(...)` en overlay_app.py y chat_overlay.py.

#### 2. Esquinas cuadradas reales en Win11
- Causa: CSS `border-radius:0` no es suficiente — DWM de Win11 fuerza esquinas redondeadas a nivel OS.
- Fix: `ui/common/window_shape.py` nuevo con `force_square_corners(hwnd)`:
  DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE=33, &DWMWCP_DONOTROUND=1, 4).
- Aplicado en `showEvent` de OverlayWindow (overlay_app.py), ChatOverlay (chat_overlay.py), IntelAlertWindow.

#### 3. Intel Alert — nunca detectaba mensajes de canales Intel
- Causa: `_handle_intel_message` solo disparaba cuando un watch_name estaba en el texto.
  Con watch_names:[] (config por defecto), NUNCA alertaba.
- Fix: detección por keywords (neutral/neut/red/hostile/spike/attn…) como clasificación 'intel'.
  Watchlist tiene prioridad; si hay keyword sin watchlist → clasifica 'intel' y alerta.
  Lista de keywords configurable en alert_keywords (con defaults).

#### 4. Intel Alert — descubrimiento de canales
- Nuevo: `discover_chat_channels(max_age_hours=48)` escanea el directorio de chatlogs.
- UI: botón "⟳ Descubrir" + combo de canales detectados para seleccionar y añadir a la lista.

#### 5. Intel Alert — selector de sonido
- Nuevos campos en IntelAlertConfig: `alert_sound_mode` ("beep"|"silent"|"wav"), `alert_sound_path`.
- Back-compat: carga configs antiguas con `alert_sound:bool` y lo convierte a `alert_sound_mode`.
- UI: combo Pitido/Silencio/WAV + botón "▶" para probar + selector de archivo .wav.

#### 6. Intel Alert — modo compacto
- Añadido QStackedWidget: página 0 = compact (340×88, solo ON/OFF + estado); página 1 = full.
- Botón "▣" en titlebar alterna entre modos.
- Ambos botones de toggle están sincronizados.

#### 7. Intel Alert — diagnósticos
- IntelAlertService.get_diagnostics(): archivos vigilados, último archivo, último mensaje, última alerta, total alertas, modo fuente, canales, keywords.
- Panel de diagnóstico mini en columna derecha: se refresca cada 3 s.
- Botón "📋 Diagnóstico" inserta snapshot en el historial.
- Botón "Copiar" copia diagnóstico al portapapeles.

### Archivos modificados
- ui/common/window_shape.py (nuevo)
- overlay/overlay_app.py (fix excepción + showEvent square corners)
- translator/chat_overlay.py (fix excepción + showEvent square corners)
- core/intel_alert_service.py (keyword detection, discover_chat_channels, sound fields, diagnostics)
- ui/tools/intel_alert_window.py (compact mode, channel discovery, sound selector, diagnostics panel)
- tests/test_intel_alert_v2.py (47 tests: +15 nuevos para keywords, sound, diagnostics, discover)

### Tests
47 tests, todos pasan.

---

## Session 5 — HUD visibility, session timer, portraits and Intel Alert UX reliability

**Fecha:** 2026-05-06
**Commit:** FIX: Repair HUD session portraits and Intel Alert detection UX

### Problemas diagnosticados y resueltos

#### 1. HUD ISK Tracker — visibilidad no seguía al foco (igual que Chat Translator)
- Causa raíz: `_user_hidden=True` se fijaba al cerrar el HUD con el botón X, pero `show_overlay()` en `app_controller` llamaba `.show()` sin resetear ese flag. El check de auto-hide `if not self._user_hidden` fallaba permanentemente.
- Fix: nuevo método `reveal()` en `overlay_app.py` que resetea `_user_hidden=False, _auto_hidden=False` antes de `show()`. `app_controller.show_overlay()` ahora llama `reveal()` si está disponible.
- Añadido logging throttled (cada 5 s) en `_check_eve_foreground`: `HUD VIS CHECK`, `HUD SHOW eve_or_app`, `HUD HIDE external_window`.

#### 2. Contador de sesión ISK — se disparaba sin datos (bug de timer descontrolado)
- Causa raíz 1: `_push_overlay_data` llamaba `overlay_window._on_data(payload)` DIRECTAMENTE desde el thread del tracker, Y el DataPoller también entregaba los mismos datos via socket en el hilo principal → doble-update + race condition en `_local_secs`.
- Causa raíz 2: `_local_tick` incrementaba aunque no hubiera datos recientes (session timer corriendo en vacío tras desconexión).
- Fix: eliminada la llamada directa `overlay_window._on_data()` de `_push_overlay_data`. Solo el DataPoller (socket, hilo Qt) entrega datos ahora.
- Fix: `_local_tick` guarda `_last_data_ts` en `_on_data` y no incrementa si han pasado más de 8 s sin datos frescos.

#### 3. Chat Translator — portraits no cargaban (QTimer.singleShot cross-thread)
- Causa raíz: `C.QTimer.singleShot(0, _on_main)` llamado desde un `threading.Thread` (sin event loop Qt) → callback NUNCA se ejecutaba.
- Fix: Se captura `_portrait_request.emit` (Signal.emit) en el hilo principal ANTES de lanzar el thread. El thread llama `_emit_fn(ref, char_id)` — `Signal.emit()` es thread-safe, el slot corre en el hilo principal.
- Añadida señal `_portrait_request = Signal(object, int)` en `ChatOverlay` + slot `_on_portrait_request` (usa `EveIconService.get_portrait`).

#### 4. Intel Alert — "Descubrir" dejaba UI bloqueada en "Buscando…"
- Misma causa raíz que portraits: `QTimer.singleShot(0, callback)` desde `threading.Thread` no funcionaba.
- Fix: señal `_discover_done = Signal(list)` + `self._discover_done.emit(channels)` desde el thread. Slot `_on_discovered` restaura el botón y rellena el combo.

#### 5. Intel Alert — filtro de standing (corp/alianza/buen standing)
- Nuevo módulo: `core/intel_standing_resolver.py` — `IntelStandingResolver` con cache TTL 30 min.
  Prioridad: safe_names → watch_names → ESI (no disponible sin auth) → neutral.
- `IntelAlertConfig` nuevos campos: `ignore_corp_members=True`, `ignore_good_standing=True`, `alert_neutrals=True`, `alert_bad_standing=True`.
- `_handle_local_pilot` usa `get_resolver().resolve()` → `StandingResult.should_alert` determina si alertar.
- UI: sección "Filtro standing (ESI)" con 3 checkboxes + label de estado ESI.
- `_collect_config_from_ui` guarda los 3 valores; `_load_config_to_ui` los carga.

#### 6. Intel Alert — soporte MP3
- `_browse_wav()`: filtro `"Audio (*.wav *.mp3);;WAV (*.wav);;MP3 (*.mp3)"`.
- `_play_audio_file(path)`: WAV → winsound; MP3 → QMediaPlayer + QAudioOutput.
- `_play_alert_sound()` en servicio: detecta `.mp3`, posta a hilo principal via `_post_mp3_play` → `_play_mp3_main`.

#### 7. Intel Alert — modo compacto 200×80 px
- `_build_compact_panel()`: `panel.setFixedSize(200, 80)`.
- `_toggle_compact()`: `setMinimumSize/setMaximumSize/resize(200, 80)`.

### Archivos modificados
- `overlay/overlay_app.py` (reveal(), _last_data_ts, throttled logging)
- `controller/app_controller.py` (show_overlay usa reveal(); eliminada doble-llamada _on_data)
- `translator/chat_overlay.py` (Signal-based portraits cross-thread)
- `core/intel_alert_service.py` (standing fields, MP3, _handle_local_pilot usa resolver)
- `ui/tools/intel_alert_window.py` (Signal discover, compact 200×80, MP3, standing checkboxes, _collect_config_from_ui)
- `core/intel_standing_resolver.py` (nuevo)

### Tests
82 passed, 1 skipped.

---

## Session 6 — Replicator shutdown layout region profiles and Intel Alert diagnosis

**Fecha:** 2026-05-06
**Commit:** FIX: Repair replicator shutdown layout region profiles and intel diagnostics

### Problemas diagnosticados y resueltos

#### 1. Cierre/logout con réplicas — lag en PC
- **Causa raíz**: `_client_watch_timer` (QTimer cada 1 s) NO se detenía durante el shutdown global. Seguía disparando `_client_watcher_tick()` después de que las réplicas fueran cerradas, haciendo llamadas Win32 (`resolve_eve_window_handle`) para cada entrada en `_REPLICA_STATE_CACHE`. Con 4 cuentas y entradas en cache = 4×Win32 lookups/s durante el apagado.
- **Fix**: Añadida función `_stop_client_watcher()` en `replication_overlay.py`. Llamada al inicio de `close_replicator_overlays()` en `tray_manager.py` — antes de tocar ningún overlay. Esto previene cualquier reintento de relaunch durante el teardown.
- **Fix adicional**: El keyboard hook (nuevo) también se desinstala durante shutdown.
- **Logging añadido**: `REPLICATOR SHUTDOWN START count=N`, `REPLICATOR SHUTDOWN DONE overlays=N hide_ms=X total_ms=Y`.

#### 2. Flechas de región rotas
- **Causa raíz**: Las réplicas tienen `WS_EX_NOACTIVATE` — EVE Online siempre tiene Win32 focus. Las flechas van a EVE, no al widget Qt. El `setFocus()` en `enterEvent()` da focus Qt interno pero Win32 sigue en EVE. El `keyPressEvent()` de Qt nunca se activa para flechas cuando EVE tiene focus.
- **Fix**: Nuevo hook global `WH_KEYBOARD_LL` (análogo al `WH_MOUSE_LL` existente para la rueda).
  - Intercepta VK_UP/DOWN/LEFT/RIGHT cuando `_hover_overlay` no es None.
  - Llama `_deliver_hook_nudge(ref, vk, shift)` via `QTimer.singleShot(0, ...)` — igual que el mouse hook.
  - Retorna `_LRESULT(1)` SIN llamar `CallNextHookEx` → suprime la tecla de EVE.
  - Shift + flecha = step grande (0.01), sin Shift = pequeño (0.002).
  - Se instala junto al mouse hook en el primer overlay creado.
  - Se desinstala en `close_replicator_overlays()`.
- **Logging**: `REGION NUDGE title=... vk=... region=...`

#### 3. Botón "Copiar región" en perfil de layout
- Añadido botón `"Copiar región a todas"` en el tab Layout del settings dialog.
- Al pulsar: copia `self._ov._region` (dict x/y/w/h relativo) a todos los peers.
- Actualiza `_ov_cfg['region_x/y/w/h']` en cada destino para persistencia.
- Llama `target.update()` + `target._schedule_autosave()` en cada destino.
- No toca geometría de ventana, FPS, colores, hotkeys.
- Feedback en botón: `"✓ Copiado a N réplicas"` por 3 s.
- Logging: `COPY REGION source=... targets=N region=...`

#### 4. Perfiles de layout no globales
- **Causa raíz**: Cada overlay tiene su propio `_cfg` dict en memoria. Al guardar un perfil desde la réplica A (`save_layout_profile` actualiza `_cfg['layout_profiles']`), el dict en memoria de la réplica B no se actualizaba. Cuando B abría el settings dialog, `_reload_lp_combo()` leía el dict de B que estaba desactualizado.
- **Fix 1**: `_reload_lp_combo()` ahora re-lee los perfiles desde disco (`load_config()`) y actualiza `self._ov._cfg['layout_profiles']` antes de poblar el combo.
- **Fix 2**: Después de cada `_lp_new()` y `_lp_save()`, propaga el dict actualizado de perfiles a todos los overlays activos en `_OVERLAY_REGISTRY`.
- **Logging**: `[LAYOUT PROFILE LOAD] count=N names=[...]`

#### 5. Intel Alert — sin detección de enemigo al entrar al sistema
- **Causa raíz y limitación EVE confirmada**: EVE Online NO escribe en los chatlogs la lista de presencia de Local ni las entradas/salidas de pilotos. Los chatlogs solo registran MENSAJES ESCRITOS por pilotos (formato `[timestamp] piloto > texto`). Si un enemigo entra al sistema y no escribe nada en Local, el chatlog no lo registra. Esta limitación es inherente al formato de chatlogs de EVE y no tiene solución desde la app.
- **Lo que SÍ funciona**: Si un piloto enemigo ESCRIBE en Local → alerta. Si un mensaje Intel tiene keyword (neutral/red/hostile/neut/attn/spike) → alerta. Lista de vigilancia (watch_names) en texto Intel → alerta.
- **Mejoras de diagnóstico**:
  - `_diag_local_log_path`: trackea el path real del archivo Local detectado.
  - `_diag_last_skip_pilot` + `_diag_last_skip_reason`: registra por qué se saltó la última alerta (already_seen_this_session / standing:... / safe_list).
  - Panel UI nuevo: `Local: ruta_archivo` (verde si detectado, rojo si NO DETECTADO).
  - Label de skip: `Skip: piloto — reason`.
  - Label de limitación EVE: explicación clara en la UI.
  - Nuevo botón "▶ Probar alerta simulada": dispara `fire_test_alert()` que reproduce sonido y añade evento al historial.
  - `fire_test_alert()` en `IntelAlertService`: crea evento PRUEBA_ALERTA, llama `_play_alert_sound()` y callback.

### Limitaciones reales documentadas
- **Intel Alert — detección Local**: EVE no escribe presencia en chatlogs. Solo se detectan pilotos que ESCRIBEN en Local o aparecen en mensajes Intel con keywords. Documentado en UI y workflow.
- **Flechas**: el keyboard hook suprime las teclas de EVE cuando el ratón está sobre una réplica. Si el usuario necesita las flechas en EVE mientras ve una réplica, debe mover el ratón fuera.
- **Perfiles de layout — ESI standing**: los checkboxes de corp/alliance/good-standing requieren ESI auth (no implementado todavía). Los filtros operan sobre listas manuales.

### Archivos modificados
- `overlay/replication_overlay.py` (keyboard hook WH_KEYBOARD_LL, _stop_client_watcher, install en __init__)
- `controller/tray_manager.py` (shutdown: _stop_client_watcher, _uninstall_keyboard_hook, logging)
- `overlay/replicator_settings_dialog.py` (_reload_lp_combo desde disco, propagación perfiles, botón Copiar región)
- `core/intel_alert_service.py` (diag: local_log_path, skip_reason/pilot; fire_test_alert())
- `ui/tools/intel_alert_window.py` (diag: local label, skip label, limitación EVE, botón prueba)

### Tests
170 passed, 2 skipped.
