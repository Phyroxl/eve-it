import json
import logging
import os
import webbrowser
import threading
import socket
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger('eve.auth')

_CONFIG_FILE = Path(__file__).resolve().parent.parent / 'config' / 'eve_client.json'
_SESSION_FILE = Path(__file__).resolve().parent.parent / 'config' / 'esi_session.json'

_TOKEN_REFRESH_MARGIN = 120  # seconds before expiry to trigger refresh


def _load_client_id() -> str:
    env_id = os.environ.get('EVE_CLIENT_ID', '').strip()
    if env_id:
        return env_id
    try:
        if _CONFIG_FILE.exists():
            data = json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
            return data.get('client_id', '')
    except Exception as e:
        logger.warning(f"[AUTH] Could not read EVE client config: {e}")
    return ''


class AuthManager(QObject):
    authenticated = Signal(str, dict)  # character_name, tokens

    _instance = None

    def __init__(self):
        super().__init__()
        self.client_id = _load_client_id()
        self.redirect_uri = "http://localhost:12543/callback"
        self.scopes = (
            "esi-ui.open_window.v1 esi-wallet.read_character_wallet.v1 "
            "esi-markets.read_character_orders.v1 esi-assets.read_assets.v1 "
            "esi-skills.read_skills.v1 esi-characters.read_standings.v1 "
            "esi-location.read_location.v1"
        )
        self.current_token = None
        self.refresh_token = None
        self.expiry = 0.0
        self.char_name = None
        self.char_id = None
        self.auth_error = None
        self._lock = threading.Lock()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = AuthManager()
        return cls._instance

    # ------------------------------------------------------------------
    # Token access
    # ------------------------------------------------------------------

    def get_token(self) -> str | None:
        """Retorna un access token válido. Alias de get_valid_access_token()."""
        return self.get_valid_access_token()

    def get_valid_access_token(self) -> str | None:
        """
        Retorna un access token válido.
        - Si el token actual expira en más de 120s, lo devuelve directamente.
        - Si está cerca de expirar o ya expiró, intenta refresh con el refresh_token.
        - Retorna None solo si no hay refresh_token o el refresh falla.
        """
        with self._lock:
            if not self.current_token and not self.refresh_token:
                return None

            if self.current_token and time.time() < self.expiry - _TOKEN_REFRESH_MARGIN:
                return self.current_token

            if self.refresh_token:
                logger.info(
                    f"[AUTH] Access token expires in {int(self.expiry - time.time())}s, refreshing..."
                )
                if self._do_refresh():
                    return self.current_token

            return None

    # ------------------------------------------------------------------
    # Refresh internals (call within _lock)
    # ------------------------------------------------------------------

    def _do_refresh(self) -> bool:
        """
        Refresca el access token usando el refresh_token actual.
        Debe llamarse desde dentro de self._lock.
        Limpia la sesión automáticamente si CCP devuelve invalid_grant.
        """
        import requests
        import base64
        try:
            config_data = json.loads(_CONFIG_FILE.read_text())
            client_id = config_data.get('client_id')
            client_secret = config_data.get('client_secret', '')

            post_data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }

            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            if client_secret:
                auth_header = base64.b64encode(
                    f"{client_id}:{client_secret}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {auth_header}"
            else:
                post_data["client_id"] = client_id

            res = requests.post(
                "https://login.eveonline.com/v2/oauth/token",
                data=post_data,
                headers=headers,
                timeout=15,
            )

            if res.status_code == 200:
                data = res.json()
                self.current_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token', self.refresh_token)
                self.expiry = time.time() + data.get('expires_in', 3600)
                logger.info(f"[AUTH] Token refresh successful; expires_at={self.expiry:.0f}")
                self.save_session()
                return True

            # Error handling — do not log raw response body (may contain tokens)
            try:
                error_body = res.json()
                error_code = error_body.get('error', '')
            except Exception:
                error_code = ''

            if error_code == 'invalid_grant':
                logger.warning("[AUTH] Refresh token invalid/revoked; login required")
                self._clear_session_data()
            else:
                logger.error(
                    f"[AUTH] Token refresh failed: HTTP {res.status_code} "
                    f"error={error_code or 'unknown'}"
                )
            return False

        except Exception as e:
            logger.error(f"[AUTH] Exception during token refresh: {e}")
            return False

    def _clear_session_data(self):
        """Limpia estado de autenticación en memoria y en disco. No adquiere el lock."""
        self.current_token = None
        self.refresh_token = None
        self.expiry = 0.0
        self.char_id = None
        self.char_name = None
        if _SESSION_FILE.exists():
            try:
                _SESSION_FILE.unlink()
            except Exception as e:
                logger.warning(f"[AUTH] Could not delete session file: {e}")
        logger.info("[AUTH] Session cleared")

    # ------------------------------------------------------------------
    # Login flow (browser SSO)
    # ------------------------------------------------------------------

    def login(self):
        """Inicia el flujo SSO en el navegador."""
        if not self.client_id:
            logger.error(
                "[AUTH] No Client ID configured. Set EVE_CLIENT_ID or config/eve_client.json"
            )
            return False

        url = (
            f"https://login.eveonline.com/v2/oauth/authorize/?"
            f"response_type=code&"
            f"redirect_uri={self.redirect_uri}&"
            f"client_id={self.client_id}&"
            f"scope={self.scopes}&"
            f"state=eve_it_market"
        )

        self.start_callback_server()
        webbrowser.open(url)
        return True

    def start_callback_server(self):
        import requests
        import base64

        def run_server():
            self.auth_error = None
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('localhost', 12543))
                s.listen(1)
                s.settimeout(60)
                try:
                    conn, addr = s.accept()
                    with conn:
                        data = b''
                        conn.settimeout(5)
                        try:
                            while b'\r\n\r\n' not in data:
                                chunk = conn.recv(4096)
                                if not chunk:
                                    break
                                data += chunk
                        except socket.timeout:
                            pass
                        data = data.decode('utf-8', errors='replace')

                        if "GET" in data:
                            path = data.split(' ')[1]
                            query = urlparse(path).query
                            params = parse_qs(query)
                            code = params.get('code', [None])[0]

                            if code:
                                try:
                                    config_data = json.loads(_CONFIG_FILE.read_text())
                                    client_id = config_data.get('client_id')
                                    client_secret = config_data.get('client_secret', '')

                                    post_data = {
                                        "grant_type": "authorization_code",
                                        "code": code,
                                        "redirect_uri": self.redirect_uri,
                                    }

                                    # Try confidential client first (with secret)
                                    if client_secret:
                                        auth_header = base64.b64encode(
                                            f"{client_id}:{client_secret}".encode()
                                        ).decode()
                                        res = requests.post(
                                            "https://login.eveonline.com/v2/oauth/token",
                                            data=post_data,
                                            headers={
                                                "Authorization": f"Basic {auth_header}",
                                                "Content-Type": "application/x-www-form-urlencoded",
                                            },
                                            timeout=15,
                                        )
                                        logger.info(
                                            f"[AUTH] Token exchange (confidential) → HTTP {res.status_code}"
                                        )
                                    else:
                                        res = None

                                    # Fallback to public/native client (PKCE)
                                    if res is None or res.status_code == 401:
                                        if res is not None:
                                            logger.warning(
                                                "[AUTH] 401 with Basic auth → retrying as public client"
                                            )
                                        public_data = {**post_data, "client_id": client_id}
                                        res = requests.post(
                                            "https://login.eveonline.com/v2/oauth/token",
                                            data=public_data,
                                            headers={
                                                "Content-Type": "application/x-www-form-urlencoded"
                                            },
                                            timeout=15,
                                        )
                                        logger.info(
                                            f"[AUTH] Token exchange (public/native) → HTTP {res.status_code}"
                                        )

                                    if res.status_code == 200:
                                        tokens = res.json()
                                        self.current_token = tokens.get('access_token')
                                        self.refresh_token = tokens.get('refresh_token')
                                        self.expiry = time.time() + tokens.get('expires_in', 3600)
                                        logger.info("[AUTH] access_token and refresh_token obtained")

                                        # Decode JWT to extract identity without extra network call
                                        try:
                                            import base64 as _b64
                                            payload_b64 = self.current_token.split('.')[1]
                                            payload_b64 += '=' * (4 - len(payload_b64) % 4)
                                            payload = json.loads(
                                                _b64.urlsafe_b64decode(payload_b64).decode()
                                            )
                                            sub = payload.get('sub', '')
                                            if sub.startswith('CHARACTER:EVE:'):
                                                self.char_id = int(sub.split(':')[2])
                                            self.char_name = payload.get('name', '')
                                            logger.info(
                                                f"[AUTH] JWT decoded: char_id={self.char_id}"
                                            )
                                        except Exception as jwt_err:
                                            logger.warning(
                                                f"[AUTH] JWT decode failed: {jwt_err} — using /oauth/verify"
                                            )
                                            verify_res = requests.get(
                                                "https://login.eveonline.com/oauth/verify",
                                                headers={
                                                    "Authorization": f"Bearer {self.current_token}"
                                                },
                                                timeout=10,
                                            )
                                            if verify_res.status_code == 200:
                                                vd = verify_res.json()
                                                self.char_name = vd.get('CharacterName')
                                                self.char_id = vd.get('CharacterID')
                                            else:
                                                logger.error(
                                                    f"[AUTH] /oauth/verify → {verify_res.status_code}"
                                                )

                                        logger.info(
                                            f"[AUTH] Authenticated as char_id={self.char_id}"
                                        )
                                        self.save_session()
                                        self.authenticated.emit(self.char_name, tokens)
                                    else:
                                        try:
                                            err_code = res.json().get('error', res.status_code)
                                        except Exception:
                                            err_code = res.status_code
                                        self.auth_error = (
                                            f"Token exchange failed: HTTP {res.status_code} "
                                            f"error={err_code}"
                                        )
                                        logger.error(f"[AUTH] {self.auth_error}")
                                except Exception as e:
                                    self.auth_error = f"Auth exception: {e}"
                                    logger.error(f"[AUTH] {self.auth_error}", exc_info=True)
                            else:
                                self.auth_error = "Callback received without authorization code."
                                logger.error(f"[AUTH] {self.auth_error}")

                            if self.auth_error:
                                body = (
                                    f"<h1>EVE iT — Auth Error</h1>"
                                    f"<p>{self.auth_error}</p>"
                                    f"<p>Check app logs for details.</p>"
                                )
                            else:
                                body = (
                                    "<h1>EVE iT Authenticated</h1>"
                                    "<p>You can close this window and return to the app.</p>"
                                )
                            response = (
                                f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n{body}"
                            )
                            conn.sendall(response.encode('utf-8'))
                except socket.timeout:
                    self.auth_error = "Timeout — user did not complete login in 60s."
                    logger.warning(f"[AUTH] {self.auth_error}")
                except Exception as e:
                    self.auth_error = f"Server error: {e}"
                    logger.error(f"[AUTH] {self.auth_error}", exc_info=True)

        threading.Thread(target=run_server, daemon=True).start()

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def save_session(self):
        """Guarda la sesión actual en config/esi_session.json (incluye access_token y expires_at)."""
        if not self.refresh_token:
            return

        session_data = {
            "char_id": self.char_id,
            "char_name": self.char_name,
            "access_token": self.current_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expiry,
            "scopes": self.scopes,
            "last_update": time.time(),
        }
        try:
            _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SESSION_FILE.write_text(json.dumps(session_data, indent=4), encoding='utf-8')
            logger.info(f"[AUTH] Session saved for char_id={self.char_id}")
        except Exception as e:
            logger.error(f"[AUTH] Could not save session: {e}")

    def try_restore_session(self) -> str:
        """
        Intenta restaurar la sesión desde el archivo guardado.
        Retorna: 'ok', 'no_session', 'expired', 'new_scopes_required'

        Si el access_token guardado sigue siendo válido, se usa directamente sin
        hacer ninguna llamada de red. Si está caducado, se refresca usando el
        refresh_token. El signal authenticated se emite FUERA del lock para evitar
        deadlocks cuando los slots llaman a get_valid_access_token().
        """
        emit_args = None  # (char_name, tokens) — se emite fuera del lock

        with self._lock:
            # Si ya hay un token válido en memoria, no repetir el restore
            if self.current_token and time.time() < self.expiry - _TOKEN_REFRESH_MARGIN:
                logger.info(f"[AUTH] Session already active for char_id={self.char_id}")
                return "ok"

            if not _SESSION_FILE.exists():
                logger.info("[AUTH] No session file found")
                return "no_session"

            # Leer y parsear el archivo de sesión
            try:
                raw = _SESSION_FILE.read_text(encoding='utf-8')
                data = json.loads(raw)
            except Exception as e:
                ts = int(time.time())
                corrupt_path = _SESSION_FILE.with_suffix(f'.corrupt.{ts}')
                try:
                    _SESSION_FILE.rename(corrupt_path)
                except Exception:
                    pass
                logger.error(
                    f"[AUTH] Session file corrupted, renamed to {corrupt_path.name}: {e}"
                )
                return "no_session"

            logger.info("[AUTH] Session file exists")

            # Verificar scopes
            saved_scopes = data.get('scopes', '')
            required = set(self.scopes.split())
            saved = set(saved_scopes.split())
            if not required.issubset(saved):
                logger.warning("[AUTH] Saved scopes insufficient; re-auth required")
                return "new_scopes_required"

            # Cargar identidad y refresh_token
            self.char_id = data.get('char_id')
            self.char_name = data.get('char_name')
            self.refresh_token = data.get('refresh_token')

            if not self.refresh_token:
                return "no_session"

            logger.info(f"[AUTH] Restored session char_id={self.char_id}")

            # Si el access_token guardado aún es válido, usarlo sin llamada de red
            saved_token = data.get('access_token')
            saved_expires_at = data.get('expires_at', 0)
            if saved_token and time.time() < saved_expires_at - _TOKEN_REFRESH_MARGIN:
                secs = int(saved_expires_at - time.time())
                logger.info(f"[AUTH] Access token valid for {secs}s, skipping network refresh")
                self.current_token = saved_token
                self.expiry = saved_expires_at
                emit_args = (
                    self.char_name,
                    {"access_token": self.current_token, "refresh_token": self.refresh_token},
                )
            else:
                # Token caducado o cerca de caducar → refrescar
                logger.info("[AUTH] Access token expired/near expiry, refreshing...")
                if self._do_refresh():
                    emit_args = (
                        self.char_name,
                        {"access_token": self.current_token, "refresh_token": self.refresh_token},
                    )
                else:
                    # _do_refresh limpia la sesión si fue invalid_grant
                    return "expired"

        # Emitir authenticated FUERA del lock (evita deadlock con slots que llaman get_valid_access_token)
        if emit_args:
            logger.info(f"[AUTH] Session restored successfully for char_id={self.char_id}")
            self.authenticated.emit(*emit_args)
            return "ok"

        return "expired"

    def logout(self):
        """Cierra sesión: borra el archivo persistente y limpia el estado en memoria."""
        self._clear_session_data()
        logger.info("[AUTH] User logged out")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_auth_status(self) -> dict:
        """Retorna el estado actual de autenticación. No incluye valores de tokens."""
        expires_in = max(0, int(self.expiry - time.time())) if self.expiry > 0 else 0
        return {
            "authenticated": bool(
                self.current_token and time.time() < self.expiry - 10
            ),
            "character_id": self.char_id,
            "character_name": self.char_name,
            "has_access_token": bool(self.current_token),
            "has_refresh_token": bool(self.refresh_token),
            "expires_in": expires_in,
            "session_persisted": _SESSION_FILE.exists(),
        }
