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


def _load_client_id() -> str:
    """Carga el Client ID desde variable de entorno, luego desde config file."""
    env_id = os.environ.get('EVE_CLIENT_ID', '').strip()
    if env_id:
        return env_id
    try:
        if _CONFIG_FILE.exists():
            data = json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
            return data.get('client_id', '')
    except Exception as e:
        logger.warning(f"No se pudo leer config de cliente EVE: {e}")
    return ''


class AuthManager(QObject):
    authenticated = Signal(str, dict) # character_name, tokens

    _instance = None

    def __init__(self):
        super().__init__()
        self.client_id = _load_client_id()
        self.redirect_uri = "http://localhost:12543/callback"
        self.scopes = "esi-ui.open_window.v1 esi-wallet.read_character_wallet.v1 esi-markets.read_character_orders.v1 esi-assets.read_assets.v1 esi-skills.read_skills.v1 esi-characters.read_standings.v1 esi-location.read_location.v1"
        self.current_token = None
        self.refresh_token = None
        self.expiry = 0
        self.char_name = None
        self.char_id = None
        self.auth_error = None
        self._lock = threading.Lock()
        
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = AuthManager()
        return cls._instance

    def get_token(self) -> str:
        """Retorna el access token actual, refrescándolo si es necesario."""
        with self._lock:
            if not self.current_token:
                return None
            
            # Si expira en menos de 60 segundos, renovar
            if self.refresh_token and time.time() > self.expiry - 60:
                logger.info("AuthManager: Token por expirar, refrescando...")
                if not self._do_refresh():
                    return None
            
            return self.current_token

    def _do_refresh(self) -> bool:
        """Lógica interna de refresh (llamada dentro del lock)."""
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
                auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
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
                logger.info("AuthManager: Token refrescado exitosamente.")
                return True
            else:
                logger.error(f"AuthManager: Fallo al refrescar token: HTTP {res.status_code} — {res.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"AuthManager: Excepción al refrescar token: {e}")
            return False
        
    def login(self):
        """Inicia el flujo SSO en el navegador."""
        if not self.client_id:
            logger.error("AuthManager: No Client ID configurado. Define EVE_CLIENT_ID o config/eve_client.json")
            return False
            
        url = (
            f"https://login.eveonline.com/v2/oauth/authorize/?"
            f"response_type=code&"
            f"redirect_uri={self.redirect_uri}&"
            f"client_id={self.client_id}&"
            f"scope={self.scopes}&"
            f"state=eve_it_market"
        )
        
        # Iniciar servidor local para capturar el código
        self.start_callback_server()
        webbrowser.open(url)
        return True

    def start_callback_server(self):
        import requests
        import base64

        def run_server():
            self.auth_error = None  # Reset en cada intento
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

                                    # Intentar primero como cliente confidencial (con secret)
                                    if client_secret:
                                        auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
                                        res = requests.post(
                                            "https://login.eveonline.com/v2/oauth/token",
                                            data=post_data,
                                            headers={
                                                "Authorization": f"Basic {auth_header}",
                                                "Content-Type": "application/x-www-form-urlencoded",
                                            },
                                            timeout=15,
                                        )
                                        logger.info(f"AuthManager: Token exchange (confidential) → HTTP {res.status_code}")
                                    else:
                                        res = None

                                    # Si no hay secret, o si falló con 401 (app pública/nativa sin secret):
                                    # reintentar con solo client_id en el body (PKCE native app)
                                    if res is None or res.status_code == 401:
                                        if res is not None:
                                            logger.warning("AuthManager: 401 con Basic auth → reintentando como public client (native app)")
                                        public_data = {**post_data, "client_id": client_id}
                                        res = requests.post(
                                            "https://login.eveonline.com/v2/oauth/token",
                                            data=public_data,
                                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                                            timeout=15,
                                        )
                                        logger.info(f"AuthManager: Token exchange (public/native) → HTTP {res.status_code}")

                                    if res.status_code == 200:
                                        tokens = res.json()
                                        self.current_token = tokens.get('access_token')
                                        self.refresh_token = tokens.get('refresh_token')
                                        self.expiry = time.time() + tokens.get('expires_in', 3600)
                                        logger.info("AuthManager: access_token y refresh_token obtenidos.")

                                        # Decodificar el JWT para extraer CharacterID/Name sin llamada extra
                                        try:
                                            import base64 as _b64
                                            payload_b64 = self.current_token.split('.')[1]
                                            # Añadir padding
                                            payload_b64 += '=' * (4 - len(payload_b64) % 4)
                                            payload = json.loads(_b64.urlsafe_b64decode(payload_b64).decode())
                                            sub = payload.get('sub', '')  # "CHARACTER:EVE:12345678"
                                            if sub.startswith('CHARACTER:EVE:'):
                                                self.char_id = int(sub.split(':')[2])
                                            self.char_name = payload.get('name', '')
                                            logger.info(f"AuthManager: JWT → char={self.char_name} ({self.char_id})")
                                        except Exception as jwt_err:
                                            logger.warning(f"AuthManager: No se pudo decodificar JWT: {jwt_err} — usando /oauth/verify")
                                            verify_res = requests.get(
                                                "https://login.eveonline.com/oauth/verify",
                                                headers={"Authorization": f"Bearer {self.current_token}"},
                                                timeout=10,
                                            )
                                            if verify_res.status_code == 200:
                                                vd = verify_res.json()
                                                self.char_name = vd.get('CharacterName')
                                                self.char_id = vd.get('CharacterID')
                                            else:
                                                logger.error(f"AuthManager: /oauth/verify → {verify_res.status_code}")

                                        logger.info(f"AuthManager: Autenticado como {self.char_name} ({self.char_id})")
                                        self.authenticated.emit(self.char_name, tokens)
                                    else:
                                        self.auth_error = f"Token exchange falló: HTTP {res.status_code} — {res.text[:300]}"
                                        logger.error(f"AuthManager: {self.auth_error}")
                                except Exception as e:
                                    self.auth_error = f"Excepción en auth: {e}"
                                    logger.error(f"AuthManager: {self.auth_error}", exc_info=True)
                            else:
                                self.auth_error = "Callback recibido sin código de autorización."
                                logger.error(f"AuthManager: {self.auth_error}")

                            # Responder al navegador (siempre, para que no quede colgado)
                            if self.auth_error:
                                body = f"<h1>EVE iT — Error de autenticación</h1><p>{self.auth_error}</p><p>Revisa los logs de la app.</p>"
                            else:
                                body = "<h1>EVE iT Autenticado</h1><p>Ya puedes cerrar esta ventana y volver a la app.</p>"
                            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n{body}"
                            conn.sendall(response.encode('utf-8'))
                except socket.timeout:
                    self.auth_error = "Timeout — el usuario no completó el login en 60s."
                    logger.warning(f"AuthManager: {self.auth_error}")
                except Exception as e:
                    self.auth_error = f"Server error: {e}"
                    logger.error(f"AuthManager: {self.auth_error}", exc_info=True)

        threading.Thread(target=run_server, daemon=True).start()
