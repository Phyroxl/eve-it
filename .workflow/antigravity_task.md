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
