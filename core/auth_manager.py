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

_TOKEN_REFRESH_MARGIN = 300  # seconds before expiry to trigger refresh (5 minutes)


def _load_client_id() -> str:
    env_id = os.environ.get('EVE_CLIENT_ID', '').strip()
    if env_id:
        return env_id
    try:
        if _CONFIG_FILE.exists():
            data = json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
            return data.get('client_id', '')
    except Exception as e:
        logger.warning(f"[ESI AUTH] Could not read EVE client config: {e}")
    return ''


class AuthManager(QObject):
    authenticated = Signal(str, dict)  # character_name, tokens
    auth_status_changed = Signal(str)  # human readable status

    _instance = None
    _global_lock = threading.Lock()

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
        
        self._refresh_lock = threading.Lock()
        self._last_refresh_attempt = 0
        self._is_refreshing = False
        
        # Diagnostic fields
        self.last_refresh_success = False
        self.last_refresh_error = None
        self.requires_reauth = False

    @classmethod
    def instance(cls):
        with cls._global_lock:
            if cls._instance is None:
                cls._instance = AuthManager()
            return cls._instance

    # ------------------------------------------------------------------
    # Token access
    # ------------------------------------------------------------------

    def get_token(self) -> str | None:
        """Alias for get_valid_access_token()."""
        return self.get_valid_access_token()

    def get_valid_access_token(self) -> str | None:
        """
        Ensures a valid access token is available.
        Refreshes automatically if close to expiry or already expired.
        Returns None only if no refresh_token is available or refresh fails permanently.
        """
        # 1. Quick check without lock
        if not self.current_token and not self.refresh_token:
            return None

        now = time.time()
        
        # 2. Check if current token is still valid (with margin)
        if self.current_token and now < (self.expiry - _TOKEN_REFRESH_MARGIN):
            return self.current_token

        # 3. Needs refresh or initial load
        with self._refresh_lock:
            # Re-check after acquiring lock
            if self.current_token and time.time() < (self.expiry - _TOKEN_REFRESH_MARGIN):
                return self.current_token

            if not self.refresh_token:
                logger.warning("[ESI AUTH] No refresh token available for background refresh.")
                return None

            logger.info(f"[ESI AUTH] Token expired or expiring soon (secs left: {int(self.expiry - now)}). Refreshing...")
            if self._do_refresh():
                return self.current_token
            
            # If refresh failed but it wasn't a permanent revocation, 
            # we might still return the old token as a last resort, 
            # but usually it's better to let the ESI call fail and retry.
            return self.current_token if (self.current_token and time.time() < self.expiry) else None

    # ------------------------------------------------------------------
    # Refresh internals
    # ------------------------------------------------------------------

    def _do_refresh(self) -> bool:
        """
        Performs the OAuth2 refresh token flow.
        Should be called within self._refresh_lock.
        """
        import requests
        import base64

        if not self.refresh_token:
            return False

        self._is_refreshing = True
        self._last_refresh_attempt = time.time()
        self.last_refresh_success = False
        
        try:
            if not _CONFIG_FILE.exists():
                logger.error(f"[ESI AUTH] Config file missing: {_CONFIG_FILE}")
                return False
                
            config_data = json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
            client_id = config_data.get('client_id')
            client_secret = config_data.get('client_secret', '')

            if not client_id:
                logger.error("[ESI AUTH] client_id missing in config.")
                return False

            post_data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "EVE-iT-Auth-Manager/1.2"
            }
            
            if client_secret:
                auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
                headers["Authorization"] = f"Basic {auth_header}"
            else:
                post_data["client_id"] = client_id

            logger.info(f"[ESI AUTH] Sending refresh request to CCP (client_id={client_id[:5]}...)")
            
            res = requests.post(
                "https://login.eveonline.com/v2/oauth/token",
                data=post_data,
                headers=headers,
                timeout=20,
            )

            if res.status_code == 200:
                data = res.json()
                self.current_token = data.get('access_token')
                # Rotation: CCP may send a new refresh token
                new_rt = data.get('refresh_token')
                if new_rt:
                    logger.info("[ESI AUTH] Received new refresh token (rotation enabled)")
                    self.refresh_token = new_rt
                
                self.expiry = time.time() + data.get('expires_in', 1200)
                self.last_refresh_success = True
                self.last_refresh_error = None
                self.requires_reauth = False
                
                logger.info(f"[ESI AUTH] Token refresh SUCCESS. New expiry in {int(self.expiry - time.time())}s")
                self.save_session()
                return True

            # Error handling
            error_code = ""
            try:
                error_body = res.json()
                error_code = error_body.get('error', '')
            except Exception:
                pass

            self.last_refresh_error = f"HTTP {res.status_code} {error_code}"
            
            if error_code == 'invalid_grant' or res.status_code == 400:
                logger.error(f"[ESI AUTH] Refresh token REVOKED or INVALID (invalid_grant). Login required.")
                self.requires_reauth = True
                # We DON'T automatically clear the session file here to avoid accidental loss 
                # on weird CCP transient 400s, but we mark it as requiring re-auth.
                # Only a deliberate logout or a confirmed fatal error should clear it.
                return False
            else:
                logger.warning(f"[ESI AUTH] Temporary refresh failure: {self.last_refresh_error}. Will retry later.")
                return False

        except Exception as e:
            self.last_refresh_error = str(e)
            logger.error(f"[ESI AUTH] Exception during token refresh: {e}")
            return False
        finally:
            self._is_refreshing = False

    def _clear_session_data(self):
        """Clears auth state from memory and disk."""
        with self._refresh_lock:
            self.current_token = None
            self.refresh_token = None
            self.expiry = 0.0
            self.char_id = None
            self.char_name = None
            self.requires_reauth = False
            if _SESSION_FILE.exists():
                try:
                    _SESSION_FILE.unlink()
                    logger.info("[ESI AUTH] Session file deleted from disk.")
                except Exception as e:
                    logger.warning(f"[ESI AUTH] Could not delete session file: {e}")
            logger.info("[ESI AUTH] Auth state cleared in memory.")

    # ------------------------------------------------------------------
    # Login flow (browser SSO)
    # ------------------------------------------------------------------

    def login(self):
        """Starts SSO flow in browser."""
        if not self.client_id:
            logger.error("[ESI AUTH] No Client ID configured.")
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
                try:
                    s.bind(('localhost', 12543))
                except Exception as e:
                    logger.error(f"[ESI AUTH] Callback server bind failed: {e}")
                    return
                    
                s.listen(1)
                s.settimeout(120)
                try:
                    conn, addr = s.accept()
                    with conn:
                        data = b''
                        conn.settimeout(5)
                        try:
                            while b'\r\n\r\n' not in data:
                                chunk = conn.recv(4096)
                                if not chunk: break
                                data += chunk
                        except socket.timeout:
                            pass
                        
                        data_str = data.decode('utf-8', errors='replace')
                        if "GET" in data_str:
                            path = data_str.split(' ')[1]
                            params = parse_qs(urlparse(path).query)
                            code = params.get('code', [None])[0]

                            if code:
                                try:
                                    config_data = json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
                                    c_id = config_data.get('client_id')
                                    c_secret = config_data.get('client_secret', '')

                                    post_data = {
                                        "grant_type": "authorization_code",
                                        "code": code,
                                        "redirect_uri": self.redirect_uri,
                                    }

                                    headers = {"Content-Type": "application/x-www-form-urlencoded"}
                                    if c_secret:
                                        auth_h = base64.b64encode(f"{c_id}:{c_secret}".encode()).decode()
                                        headers["Authorization"] = f"Basic {auth_h}"
                                    else:
                                        post_data["client_id"] = c_id

                                    res = requests.post(
                                        "https://login.eveonline.com/v2/oauth/token",
                                        data=post_data,
                                        headers=headers,
                                        timeout=20,
                                    )

                                    if res.status_code == 200:
                                        tokens = res.json()
                                        self.current_token = tokens.get('access_token')
                                        self.refresh_token = tokens.get('refresh_token')
                                        self.expiry = time.time() + tokens.get('expires_in', 1200)
                                        
                                        # Decode JWT
                                        try:
                                            import base64 as _b64
                                            payload_part = self.current_token.split('.')[1]
                                            payload_part += '=' * (4 - len(payload_part) % 4)
                                            payload = json.loads(_b64.urlsafe_b64decode(payload_part).decode())
                                            sub = payload.get('sub', '')
                                            if sub.startswith('CHARACTER:EVE:'):
                                                self.char_id = int(sub.split(':')[2])
                                            self.char_name = payload.get('name', '')
                                        except Exception:
                                            # Fallback verify
                                            v_res = requests.get(
                                                "https://login.eveonline.com/oauth/verify",
                                                headers={"Authorization": f"Bearer {self.current_token}"},
                                                timeout=10
                                            )
                                            if v_res.status_code == 200:
                                                vd = v_res.json()
                                                self.char_name = vd.get('CharacterName')
                                                self.char_id = vd.get('CharacterID')

                                        logger.info(f"[ESI AUTH] Login successful for {self.char_name} ({self.char_id})")
                                        self.requires_reauth = False
                                        self.save_session()
                                        self.authenticated.emit(self.char_name, tokens)
                                        body = "<h1>EVE iT Authenticated</h1><p>You can close this window and return to the app.</p>"
                                    else:
                                        self.auth_error = f"Token exchange failed: {res.status_code}"
                                        body = f"<h1>Auth Error</h1><p>{self.auth_error}</p>"
                                except Exception as e:
                                    self.auth_error = str(e)
                                    body = f"<h1>Exception</h1><p>{e}</p>"
                            else:
                                body = "<h1>Error</h1><p>No code received</p>"
                                
                            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n{body}"
                            conn.sendall(response.encode('utf-8'))
                except Exception as e:
                    logger.error(f"[ESI AUTH] Callback server error: {e}")

        threading.Thread(target=run_server, daemon=True).start()

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def save_session(self):
        """Persists session to disk."""
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
            logger.info(f"[ESI AUTH] Session persisted to disk for char_id={self.char_id}")
        except Exception as e:
            logger.error(f"[ESI AUTH] Could not save session: {e}")

    def try_restore_session(self) -> str:
        """
        Attempts to restore session from file.
        Returns: 'ok', 'no_session', 'expired', 'new_scopes_required', 'temporary_failure'
        """
        with self._refresh_lock:
            if self.current_token and time.time() < (self.expiry - _TOKEN_REFRESH_MARGIN):
                return "ok"

            if not _SESSION_FILE.exists():
                return "no_session"

            try:
                data = json.loads(_SESSION_FILE.read_text(encoding='utf-8'))
                self.char_id = data.get('char_id')
                self.char_name = data.get('char_name')
                self.refresh_token = data.get('refresh_token')
                self.current_token = data.get('access_token')
                self.expiry = data.get('expires_at', 0)
                
                # Verify scopes
                saved_scopes = data.get('scopes', '')
                required = set(self.scopes.split())
                saved = set(saved_scopes.split())
                if not required.issubset(saved):
                    logger.warning("[ESI AUTH] New scopes required.")
                    return "new_scopes_required"

                if not self.refresh_token:
                    return "no_session"

                # Check if we need to refresh
                if time.time() > (self.expiry - _TOKEN_REFRESH_MARGIN):
                    logger.info("[ESI AUTH] Restored session needs refresh...")
                    if self._do_refresh():
                        return "ok"
                    else:
                        if self.requires_reauth:
                            return "expired"
                        return "temporary_failure"
                
                logger.info(f"[ESI AUTH] Restored session for {self.char_name} (valid for {int(self.expiry - time.time())}s)")
                return "ok"
            except Exception as e:
                logger.error(f"[ESI AUTH] Restore failed: {e}")
                return "no_session"

    def logout(self):
        """Manual logout."""
        self._clear_session_data()
        logger.info("[ESI AUTH] Manual logout completed.")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_auth_status(self) -> dict:
        expires_in = max(0, int(self.expiry - time.time())) if self.expiry > 0 else 0
        return {
            "linked": bool(self.refresh_token),
            "authenticated": bool(self.current_token and expires_in > 10),
            "character_id": self.char_id,
            "character_name": self.char_name,
            "has_refresh_token": bool(self.refresh_token),
            "expires_in": expires_in,
            "requires_reauth": self.requires_reauth,
            "last_refresh_success": self.last_refresh_success,
            "last_refresh_error": self.last_refresh_error,
            "token_store_path": str(_SESSION_FILE)
        }
