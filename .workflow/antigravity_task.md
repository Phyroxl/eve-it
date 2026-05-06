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
