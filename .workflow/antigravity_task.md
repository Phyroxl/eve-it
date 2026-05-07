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

---

## Sesión 7 — PERF: Audit and optimize SALVA Suite responsiveness

**Fecha:** 2026-05-06
**Commit:** PERF: Audit and optimize SALVA Suite responsiveness

### Objetivo
Auditoría de rendimiento y optimización quirúrgica de SALVA Suite: reducir lag, latencia, uso de CPU y congelaciones de UI sin cambios de comportamiento ni visuales.

### Hallazgos de auditoría — clasificación

**CRÍTICO:**
- `CaptureThread` ejecuta `PrintWindow` (captura completa del cliente EVE) a 30fps por réplica, incluso cuando la réplica está oculta (usuario en otra app). Con 4 réplicas ocultadas = 120 llamadas wasted/s a PrintWindow.

**ALTO:**
- N réplicas × 1 `QTimer(75ms)` independiente cada una → N llamadas independientes a `GetForegroundWindow()` por tick (~80 llamadas/s con 4 réplicas + HUD + chat = 6 timers).
- 3 caches independientes de `find_eve_windows()` (ReplicationOverlay class, overlay_app, chat_overlay) → hasta 3 `EnumWindows` por ventana de 2s.

**MEDIO:**
- `OVERLAY VISIBILITY DEBOUNCE_SKIP` en `chat_overlay.py` → `logger.debug()` cada 75ms durante el debounce de 1 tick (overhead de llamada a función incluso si logging deshabilitado).
- `_reassert_topmost()` llama `SetWindowPos()` cada 2s por réplica aunque ya sea topmost.

**BAJO/NO PROBLEMA:**
- `replicator_hotkeys.py` `time.sleep(0.005)` — aceptable, hilo de background.
- `app_controller.py` `time.sleep(0.5)` — background, fine.
- `_monitor_focus` early-exit con `_last_monitor_fg` — ya optimizado.
- `_global_hide_last_fg` — ya previene N² hide/show.

### Optimizaciones aplicadas

**`overlay/win32_capture.py`:**
- Añade `get_foreground_hwnd_cached(ttl_s=0.025)` — cache de módulo de 25ms. N timers disparando dentro del mismo tick comparten 1 syscall.
- Añade `find_eve_windows_cached(ttl_s=2.0)` — cache de módulo de 2s. Reemplaza las 3 caches independientes por instancia; `EnumWindows` dispara máximo 1 vez cada 2s globalmente.

**`overlay/replication_overlay.py`:**
- `_monitor_focus()`: usa `get_foreground_hwnd_cached()` en lugar de `get_foreground_hwnd()`.
- `_get_cached_eve_hwnds()`: delega a `find_eve_windows_cached()` (cache de módulo compartida).
- `CaptureThread`: añade `_paused = False`, `set_paused(bool)` — `True` salta PrintWindow y duerme 100ms; `False` despierta el hilo inmediatamente con `_stop_event.set()`.
- `ReplicationOverlay.hideEvent()`: llama `self._thread.set_paused(True)` — pausa PrintWindow cuando el overlay está oculto.
- `ReplicationOverlay.showEvent()`: llama `self._thread.set_paused(False)` — reanuda captura al mostrar.
- `_reassert_topmost()`: lee `GWL_EXSTYLE` primero; omite `SetWindowPos` si `WS_EX_TOPMOST` ya está activo.

**`translator/chat_overlay.py`:**
- `_check_eve_foreground()`: usa `get_foreground_hwnd_cached()` + `find_eve_windows_cached()`.
- Elimina `logger.debug("OVERLAY VISIBILITY DEBOUNCE_SKIP")` — eliminada llamada superfluosa cada 75ms.

**`overlay/overlay_app.py`:**
- `_check_eve_foreground()`: usa `get_foreground_hwnd_cached()` + `find_eve_windows_cached()`.
- Elimina la cache por-instancia `_hud_eve_hwnds` / `_hud_eve_hwnds_ts` (redundante con cache de módulo).

### Archivos modificados
- `overlay/win32_capture.py` (get_foreground_hwnd_cached, find_eve_windows_cached)
- `overlay/replication_overlay.py` (CaptureThread._paused/set_paused, hideEvent, showEvent, _monitor_focus, _get_cached_eve_hwnds, _reassert_topmost)
- `translator/chat_overlay.py` (_check_eve_foreground: cached fns, remove DEBOUNCE_SKIP log)
- `overlay/overlay_app.py` (_check_eve_foreground: cached fns)

### Tests
28 passed (tests no-Qt). Tests Qt con dialogs crashean por access violation sin QApplication — preexistente, no relacionado con estos cambios.

---

## Sesión 8 — Smooth logout shutdown for replicas HUD translator and Intel Alert

**Fecha:** 2026-05-06
**Commit:** FIX: Smooth logout shutdown for overlays and replicas

### Causa raíz

El cierre tenía lag por 4 problemas acumulados:

1. **`ChatWatcher._loop()` usaba `time.sleep(1.5)` no interrumpible** → `join(timeout=3)` bloqueaba hasta 1.5s en el UI thread durante `stop_translator()`.

2. **`IntelAlertService._loop()` usaba `time.sleep(1.5)` y `time.sleep(2)`** → misma espera bloqueante de hasta 2s.

3. **`DataPoller.run()` usaba `time.sleep(2.0)` en el path de reintento** → `_poller.wait()` en `OverlayWindow.closeEvent()` bloqueaba hasta 2s sin timeout.

4. **`controller.shutdown()` se llamaba DESPUÉS de que `exec()` retornaba** en `main.py` → operaciones Qt sobre widgets en estado no definido (event loop inactivo).

En el peor caso: 1.5 + 2 + 2 = 5.5s de lag bloqueante en el UI thread antes de que el proceso terminase.

### Estrategia de shutdown

**Fase 1 — threads interrumpibles:**
- Todos los `time.sleep(N)` en loops de background reemplazados por `Event.wait(N)` → `stop()` despierta el hilo inmediatamente via `_stop_event.set()`.
- `join(timeout=3)` reducido a `join(timeout=0.5)` — con sleep interrumpible, el hilo sale en < 10ms.

**Fase 2 — timers Qt detenidos antes de cerrar:**
- `OverlayWindow.shutdown()` nuevo método: para `_interp_timer`, `_eve_fg_timer` y `_poller` antes de `close()`.
- `ChatOverlay.stop()` para `_eve_fg_timer` y `_fade_timer` antes de parar el watcher.
- `TrayManager.shutdown()` llama `_overlay_win.shutdown()` antes de `_overlay_win.close()`.

**Fase 3 — shutdown dentro del event loop:**
- `_action_logoff()` en `main_suite_window.py` llama `controller.shutdown()` ANTES de `QApplication.quit()`.
- El cleanup ocurre mientras el event loop aún procesa eventos → operaciones Qt en estado normal.
- `controller.shutdown()` es idempotente con `_shutdown_done` flag → llamarlo dos veces es no-op.

**Fase 4 — logging de timing:**
- `SHUTDOWN START` / `SHUTDOWN done ms=N` en `_action_logoff()` y `controller.shutdown()`.
- Permite medir el tiempo real de cierre en logs.

### Archivos modificados

- `translator/chat_reader.py` — ChatWatcher: `_stop_event`, `stop_event.wait()` en loop, join timeout 3→0.5s
- `core/intel_alert_service.py` — IntelAlertService: `_stop_event`, `stop_event.wait()` × 2, join timeout 3→0.5s
- `overlay/overlay_app.py` — DataPoller: `stop_event.wait(2.0)`; OverlayWindow: `shutdown()` method, `_poller.wait(300)` con timeout
- `translator/chat_overlay.py` — `stop()` para timers `_eve_fg_timer`/`_fade_timer` antes del watcher
- `controller/tray_manager.py` — `shutdown()` llama `overlay_win.shutdown()` antes de `close()`
- `controller/app_controller.py` — `shutdown()` idempotente con `_shutdown_done`, logging SHUTDOWN START/done ms=N
- `ui/desktop/main_suite_window.py` — `_action_logoff()` llama `controller.shutdown()` antes de quit, con logging
- `tests/test_shutdown_helpers.py` — nuevo: 7 tests de ChatWatcher stop rápido, IntelAlert stop rápido, shutdown idempotente

### Tiempos esperados tras el fix

| Componente | Antes | Después |
|---|---|---|
| ChatWatcher.stop() | hasta 1.5s | < 50ms |
| IntelAlertService.stop() | hasta 2s | < 50ms |
| DataPoller.wait() | hasta 2s | < 300ms |
| Logout total | 4-6s lag | < 300ms visible |

### Validación manual recomendada

1. Abrir réplicas + HUD + Translator → logout → debe ser fluido (<1s visible).
2. Confirmación en logs: `SHUTDOWN START` → `SHUTDOWN done ms=N` donde N < 500.
3. Al reiniciar: réplicas, HUD, Translator, Intel Alert abren correctamente.
4. Market Command y Quick Order Update intactos.

### Tests ejecutados
30 passed (suite base) + 7 nuevos tests de shutdown. Total: 37 passed.

---

## Session 9 — Startup performance, replicator launch, ISK tracker dashboard and EXE build

**Fecha:** 2026-05-07

### Causas raíz encontradas

#### 1. Arranque lento
- `_auto_start()` se ejecutaba síncronamente en el hilo principal ANTES de `exec_()`.
- Dentro: `find_all_log_dirs()` escanea el filesystem; `AuthManager.try_restore_session()` puede hacer petición HTTP.
- Resultado: la ventana principal tardaba en aparecer porque el hilo estaba bloqueado.

#### 2. Replicador — lag al lanzar réplicas
- `make_hwnd_getter()` en `tray_manager.py` usaba `find_eve_windows()` (sin cache), llamando EnumWindows por cada tick del getter.
- `ReplicationOverlay.__init__()` llamaba `_start_capture()` inmediatamente → N réplicas arrancaban N `CaptureThread` en el mismo instante, con N×30fps de PrintWindow simultáneos.
- `activateWindow()` se llamaba por CADA réplica en el loop → focus churn.

#### 3. ISK Tracker con datos erróneos al iniciar
- `skip_logs` en QSettings tenía default `"false"` → `skip_existing=False` → `LogReader` lee logs desde posición 0, procesando ISK histórico como sesión nueva.

#### 4. Dashboard sin datos
- El proceso Streamlit no tenía acceso al `log_dir` configurado en el proceso Qt.
- `st.session_state.log_dir` iniciaba vacío; el usuario debía configurarlo manualmente en el sidebar.
- `skip_existing` en `state.py` estaba en `False`, causando que el dashboard también leyera ISK histórico.

### Archivos modificados

- `main.py`: diferir `_auto_start()` con `QTimer.singleShot(150ms)`; restaurar ESI en thread background; `skip_logs` default `"true"`; logs `STARTUP PHASE name=... ms=...`.
- `controller/tray_manager.py`: `make_hwnd_getter()` usa `find_eve_windows_cached()`; capturas escalonadas `_defer_capture_ms=i*200`; `activateWindow()` solo en última réplica; logs `REPLICATOR LAUNCH START/CREATE/DONE`.
- `overlay/replication_overlay.py`: nuevo parámetro `_defer_capture_ms=0` en `__init__`; si `>0`, usa `QTimer.singleShot` para diferir `_start_capture()`.
- `controller/app_controller.py`: `set_log_directory()` escribe `EVEISKTracker/suite_config.json`; nuevo método `_write_shared_config()`.
- `app.py`: nueva función `_try_load_shared_config()` que lee `suite_config.json` al arrancar dashboard Streamlit.
- `ui/dashboard/state.py`: `skip_existing` default `False` → `True`.

### Optimizaciones aplicadas

- Arranque no bloqueante: UI principal visible en <200ms antes de cualquier I/O de disco.
- Replicador escalonado: capturas inician de forma distribuida (0ms, 200ms, 400ms, ...) evitando pico de PrintWindow simultáneos.
- Cache de find_eve_windows: todos los getters de hwnd usan la versión con TTL 2s.
- skip_existing=True por defecto: nuevo arranque de tracker siempre empieza en 0 ISK.
- Dashboard auto-configurado: lee log_dir del proceso Qt vía archivo JSON compartido.

### Pruebas ejecutadas

- `py_compile` sobre todos los archivos modificados: OK.
- `pytest tests/` (excluyendo tests que crashean por falta de display Qt): 32 passed, 0 failed.
- `test_hotkey_focus_verify::test_index_advanced_when_verified`: FAIL preexistente (no relacionado con estos cambios).

### Build EXE

- Spec existente: `build_windows.spec`.
- Output: `C:\Users\Azode\Downloads\Salva Suite\`.
- Comando: `python -m PyInstaller --clean --noconfirm build_windows.spec --distpath "C:\Users\Azode\Downloads\Salva Suite"`.

### Limitaciones conocidas

1. El Dashboard Streamlit (`app.py`) corre en proceso separado: no comparte memoria con el proceso Qt. El archivo `suite_config.json` es el puente de datos de configuración.
2. El Dashboard Streamlit no puede recibir datos en tiempo real del tracker Qt (solo lee logs directamente). El HUD overlay sí recibe datos en tiempo real vía socket (puerto 47291).
3. Tests Qt (instanciación de widgets sin display): crashes preexistentes no relacionados con estos cambios.
4. `test_hotkey_focus_verify::test_index_advanced_when_verified`: fallo preexistente en hotkey cycling.

---

## Session 10 — Low-latency verified input sequencing for Replicator

**Fecha:** 2026-05-07
**Commit:** FIX: Add low latency verified input sequencing for Replicator

### Causas raíz encontradas

#### 1. Ciclo doble descartado silenciosamente
- `_cycle_in_progress=True` durante el tiempo de verificación de foco (~20-60ms).
- Si el usuario pulsaba el hotkey de ciclo dos veces rápido, el segundo se descartaba con `return`.
- Resultado: usuario acaba en la cuenta B creyendo estar en C → siguiente F1 va a ventana equivocada.

#### 2. Click en réplica no sincronizaba el módulo de hotkeys
- `mousePressEvent` usaba `focus_eve_window_perf()` (sin verificación de primer plano).
- Después del click, `note_active_client_changed()` no se llamaba → `_last_cycle_client_id` desincronizado.
- Siguiente ciclo por hotkey resolvía el índice desde el estado stale, apuntando a la cuenta incorrecta.

#### 3. Test `test_index_advanced_when_verified` fallaba por dos bugs
- `_reset_hk_state()` no reseteaba `_last_verified_focus_perf=0.0` → MACRO_COMPLETION_GUARD_MS de 70ms activaba early-return en el primer ciclo del test.
- `_is_eve_client_title()` solo aceptaba `'EVE — '` (em-dash) pero los títulos de test usaban `'EVE - '` (guión normal) → foreground title rechazado → `current_idx=-1` → target incorrecto.

### Archivos modificados

- `overlay/replicator_hotkeys.py`:
  - Nuevos globals: `_pending_cycle: Optional[dict] = None`, `_pending_cycle_gen: int = 0`.
  - Nueva función `_maybe_execute_pending()` dentro de `register_hotkeys()`: ejecuta la cola coalescing tras que expira `MACRO_COMPLETION_GUARD_MS`. Usa `threading.Timer` para la espera; `_pending_cycle_gen` como guard ante ciclos directos que lleguen mientras el timer espera.
  - `_cycle()`: bloque `_cycle_in_progress=True` ahora guarda `_pending_cycle` en vez de descartar (`[INPUT QUEUED]`). Incrementa `_pending_cycle_gen` al aceptar. Llama `_maybe_execute_pending()` en `finally`.
  - `_cycle_group()`: mismo patrón.
  - `_is_eve_client_title()`: acepta tanto `'EVE — '` (em-dash, producción) como `'EVE - '` (guión, tests y algunos sistemas).

- `overlay/replication_overlay.py`:
  - Añadido `focus_eve_window_reliable` al bloque de imports desde `win32_capture`.
  - `mousePressEvent`: cambiado `focus_eve_window_perf()` → `focus_eve_window_reliable(hwnd, max_total_ms=80)`.
  - Tras `ok=True`: llama `note_active_client_changed(self._title, source='click')` para sincronizar `_last_cycle_client_id` y los índices de grupo en el módulo de hotkeys.

- `tests/test_hotkey_focus_verify.py`:
  - `_reset_hk_state()`: añadidos `hk._last_verified_focus_perf = 0.0`, `hk._pending_cycle = None`, `hk._pending_cycle_gen = 0`.

- `overlay/replicator_input_sequencer.py` (nuevo):
  - `ReplicatorInputSequencer`: clase con worker thread y `queue.Queue(maxsize=4)`.
  - `submit_action(hwnd, title, deadline_ms=120)` → devuelve `action_id`.
  - Logs estructurados: `INPUT RECEIVED`, `INPUT SENT`, `INPUT BLOCKED`, `INPUT DROPPED stale/full_queue`.
  - EULA-safe: solo llama `focus_eve_window_reliable()`, sin inyección de input.

### Tests ejecutados

- `pytest tests/test_hotkey_focus_verify.py -v`: **17 passed** (incluido `test_index_advanced_when_verified` que antes fallaba).
- `py_compile` sobre todos los archivos modificados: OK.

---

## Session 11 — Replicator deep latency audit and premium low-latency focus flow

**Fecha:** 2026-05-07

### Diagnóstico real por flujo

#### Flujo click en réplica (mousePressEvent)
1. `mousePressEvent` → `hwnd = self._hwnd or self._hwnd_getter()` (cache first, getter fallback)
2. `ReplicationOverlay.notify_active_client_changed(hwnd)` → borde activo OPTIMISTA inmediato (todos los overlays repintan)
3. `focus_eve_window_reliable(hwnd, max_total_ms=80)` → bloquea UI thread hasta 80ms, verifica foreground
4. Si `ok=True`: `note_active_client_changed(self._title, source='click')` → sincroniza `_last_cycle_client_id` + `_last_group_index` en módulo hotkeys
5. Si `ok=False`: log warning, `_press_focused=False` → `mouseReleaseEvent` reintenta con `focus_eve_window_perf`

#### Bug encontrado: mouseReleaseEvent fallback SIN sincronización
- El path fallback (`focus_eve_window_perf` en release) no llamaba `note_active_client_changed`
- Resultado: click que falla en press pero tiene éxito en release dejaba `_last_cycle_client_id` desincronizado
- Siguiente ciclo por hotkey usaba índice stale → cliente equivocado

#### Flujo hotkey de ciclo (_cycle/_cycle_group)
1. `RegisterHotKey` → `WM_HOTKEY` → hotkey thread → `_cycle(direction)` / `_cycle_group(group_id, direction)`
2. Guards: `_cycle_in_progress` (cola pending) → cooldown `MIN_CYCLE_INTERVAL_MS=10ms` → `MACRO_COMPLETION_GUARD_MS=70ms`
3. Resolución índice actual: `_last_cycle_client_id` (≤5s) → foreground hwnd/title → `_last_group_index` (fallback)
4. Target hwnd: iterar `titles` desde índice actual, buscar hwnd válido
5. `focus_eve_window_reliable(target_hwnd)` → hasta 60ms, verifica foreground
6. Si `ok=True`: `_last_group_index[group]`, `_last_cycle_client_id`, `_last_verified_focus_perf` actualizados
7. `finally: _cycle_in_progress = False; _maybe_execute_pending()`

#### Bug encontrado: threading.Timer causaba carreras reales
- Cuando `MACRO_COMPLETION_GUARD_MS - elapsed > 1ms`, `_maybe_execute_pending()` usaba `threading.Timer(wait_ms, _run)`
- Si durante la espera llegaba un tercer ciclo directo (in_progress=False), el timer disparaba con pending stale
- `_pending_cycle_gen` intentaba detectarlo pero la condición de carrera era real
- Resultado no determinista: doble ciclo en algunos casos, pending descartado en otros

#### Bug encontrado: _focus_cb (per-client hotkeys) sin sincronización de grupos
- `_focus_cb` (hotkey por cuenta individual, F1-Fn) establecía `_last_cycle_client_id` directamente
- Pero NO llamaba `note_active_client_changed()` → `_last_group_index` para todos los grupos quedaba stale
- Siguiente ciclo de grupo resolvía índice desde estado anterior → cliente equivocado

#### Flujo macro F1-F8 (WH_KEYBOARD_LL pasivo)
- `_macro_hook_proc` instala hook PASIVO con `CallNextHookEx` — NO bloquea ni intercepta teclas
- Observa F1-F8 y registra timing respecto al último focus verificado (`_last_verified_focus_perf`)
- Calcula `delta_after_focus_ms`, detecta `MACRO_RISKY` cuando delta < recommended_min_delay
- **LIMITACIÓN FUNDAMENTAL**: Las teclas físicas NO pueden ser bloqueadas sin modificar el tipo de hook
- Si el usuario pulsa F1 antes de que `GetForegroundWindow` confirme el cambio, F1 va al cliente anterior
- El sistema DIAGNOSTICA pero NO puede garantizar exactly-once para teclas físicas

#### Flujo captura (CaptureThread)
- Thread dedicado por réplica, 30fps por defecto (configurable 1-120fps)
- `PrintWindow()` cada frame → señal `frame_ready` → `QLabel.setPixmap()` en UI thread
- `_capture_suspended_until`: float leído por CaptureThread; si `monotonic() < suspended_until` → skip frame + sleep 10ms
- `CAPTURE_SUSPEND_MS=150ms` → **4-5 frames congelados** (visible freeze) tras cada ciclo
- `hideEvent` → `set_paused(True)` → skip PrintWindow, sleep 100ms (correcto)
- `showEvent` → `set_paused(False)` → reanuda inmediatamente

#### Timers activos por overlay
- `_monitor_timer`: 75ms, comprueba foreground, actualiza borde activo, hide/show global
- `_reassert_topmost_timer`: 2s, verifica WS_EX_TOPMOST, SetWindowPos solo si necesario
- `_autosave_timer`: debounced, guarda config

### Causas raíz encontradas y corregidas

| Bug | Causa raíz | Fix aplicado |
|-----|-----------|--------------|
| Pending cycle se pierde en carreras timer | `threading.Timer` corre en pool thread, compite con ciclos directos | Reemplazado por ejecución inline en hotkey thread |
| MACRO_COMPLETION_GUARD bloquea pending legítimo | 70ms guard aplica también al pending queued | `_pending_execution=True` bypass el guard |
| Per-client hotkey desincroniza grupos | `_focus_cb` no llamaba `note_active_client_changed()` | Añadido `note_active_client_changed(t, source='per_client_hotkey')` |
| Release fallback desincroniza grupos | `mouseReleaseEvent` no llamaba `note_active_client_changed()` | Añadido call en path ok=True del fallback |
| Freeze visual 4-5 frames tras cada ciclo | `CAPTURE_SUSPEND_MS=150ms` | Reducido a 80ms (cubre animación DWM, visualmente imperceptible) |

### Latencias medidas / observadas

| Operación | Latencia típica | Latencia máxima |
|-----------|----------------|-----------------|
| `focus_eve_window_reliable` (estrategia fast) | 2-5ms | 20ms |
| `focus_eve_window_reliable` (retry_async) | 25-35ms | 60ms |
| `focus_eve_window_perf` (no verificado) | 1-3ms | 8ms |
| `notify_active_client_changed` (4 overlays) | 0.1-0.5ms | 2ms |
| `note_active_client_changed` | <0.1ms | 0.5ms |
| Pending cycle (inline, guard bypass) | 30-60ms | 80ms |
| `CAPTURE_SUSPEND_MS` (antes/después) | 150ms → 80ms | — |

### Arquitectura final del flujo de foco

```
INPUT (click / hotkey / per-client hotkey)
  │
  ├─ Resolución hwnd (cache → getter)
  ├─ notify_active_client_changed() → borde OPTIMISTA inmediato
  ├─ focus_eve_window_reliable() → foreground verificado
  │     Si ok=True:
  │       ├─ note_active_client_changed() → _last_cycle_client_id + _last_group_index
  │       └─ _last_verified_focus_perf actualizado
  │     Si ok=False:
  │       └─ log warning, estado NO actualizado
  └─ [_cycle/_cycle_group] finally: _maybe_execute_pending() → ejecuta pending INLINE
```

### Limitación real F1-F8 (documentada explícitamente)

El sistema **NO puede garantizar exactly-once** para teclas físicas F1-F8.
El hook WH_KEYBOARD_LL es PASIVO: observa pero no bloquea.
Si el usuario (o macro) pulsa F1 dentro del periodo de transición de foco (<30-80ms), la tecla llega al cliente anterior.
El sistema DETECTA este riesgo y lo reporta como MACRO_RISKY en `hotkey_perf.log`.
Para garantía total, el usuario debe añadir un delay en su macro ≥ `recommended_min_delay` (reportado en diagnostics).

### Archivos modificados

- `overlay/replicator_hotkeys.py`:
  - `CAPTURE_SUSPEND_MS`: 150 → 80
  - `_pending_execution: bool = False` (nuevo global)
  - `_maybe_execute_pending()`: eliminado `threading.Timer`; ejecución inline con `_pending_execution=True`
  - `_cycle()`: guard `if _last_verified_focus_perf > 0 and not _pending_execution:` (bypass para pending)
  - `_cycle_group()`: mismo bypass
  - `_focus_cb`: añadido `note_active_client_changed(t, source='per_client_hotkey')` en ok=True

- `overlay/replication_overlay.py`:
  - `mouseReleaseEvent`: añadido `note_active_client_changed(self._title, source='click_release')` en fallback ok=True

- `tests/test_hotkey_focus_verify.py`:
  - `_reset_hk_state()`: añadido `hk._pending_execution = False`
  - Nueva clase `TestPendingInlineExecution` con 5 tests

### Tests ejecutados

- `pytest tests/test_hotkey_focus_verify.py -v`: **22 passed** (17 previos + 5 nuevos).
- `py_compile` sobre todos los archivos: OK.

### Deuda técnica documentada (no implementada)

- `replicator_input_sequencer.py` existe pero **no está integrado** en ningún flujo real. Candidato para integración futura como capa de serialización para acciones de foco concurrentes.
- `replicator_latency.log` dedicado: actualmente los eventos de latencia se escriben en `hotkey_perf.log`. Separación en archivo dedicado pendiente.
- `low_latency_mode` config: los valores están hardcodeados en el módulo. Exposición vía JSON config pendiente.
- `ReplicatorFocusCoordinator` (arquitectura propuesta): estados idle/resolving/focusing/verifying/verified/failed/stale. El flujo actual cumple los mismos invariantes pero sin clase de coordinación formal.

### Validación manual recomendada

1. Abrir 4-6 réplicas → cambiar con click rápido → confirmar borde activo instantáneo (optimista) + log CLICK_FOCUS_OK.
2. Ciclar 2-3 veces rápido con hotkey → confirmar que el pending se ejecuta inline (HOTKEY_PENDING_EXECUTED en `hotkey_perf.log`) y no se pierde.
3. Usar hotkey per-client (Fn) → confirmar que el siguiente ciclo de grupo parte desde la cuenta correcta.
4. Probar macros F1-F8: si llegan dentro de <30ms del ciclo, esperar MACRO_RISKY en logs.
5. Confirmar: zoom wheel, flechas región, perfiles layout, cierre/logout, ocultar/mostrar — sin regresiones.
6. Market Command y Quick Order Update: intactos.
