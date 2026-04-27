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
        self.scopes = "esi-ui.open_window.v1 esi-wallet.read_character_wallet.v1"
        self.current_token = None
        self.char_name = None
        self.char_id = None
        
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = AuthManager()
        return cls._instance
        
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
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('localhost', 12543))
                s.listen(1)
                s.settimeout(60) # 1 minuto para loguear
                try:
                    conn, addr = s.accept()
                    with conn:
                        data = conn.recv(1024).decode('utf-8')
                        if "GET" in data:
                            path = data.split(' ')[1]
                            query = urlparse(path).query
                            params = parse_qs(query)
                            code = params.get('code', [None])[0]
                            
                            if code:
                                try:
                                    # 1. Exchange code for tokens
                                    from core.auth_manager import _CONFIG_FILE
                                    import json
                                    config_data = json.loads(_CONFIG_FILE.read_text())
                                    client_id = config_data.get('client_id')
                                    client_secret = config_data.get('client_secret')
                                    
                                    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
                                    
                                    res = requests.post(
                                        "https://login.eveonline.com/v2/oauth/token",
                                        data={"grant_type": "authorization_code", "code": code},
                                        headers={"Authorization": f"Basic {auth_header}", "Content-Type": "application/x-www-form-urlencoded"}
                                    )
                                    
                                    logger.info(f"AuthManager: Token exchange status: {res.status_code}")
                                    
                                    if res.status_code == 200:
                                        tokens = res.json()
                                        self.current_token = tokens.get('access_token')
                                        logger.info("AuthManager: Token obtenido con éxito.")
                                        
                                        # 2. Verify token to get CharacterID and Name
                                        verify_res = requests.get(
                                            "https://login.eveonline.com/oauth/verify",
                                            headers={"Authorization": f"Bearer {self.current_token}"}
                                        )
                                        
                                        if verify_res.status_code == 200:
                                            verify_data = verify_res.json()
                                            self.char_name = verify_data.get('CharacterName')
                                            self.char_id = verify_data.get('CharacterID')
                                            
                                            logger.info(f"AuthManager: Autenticado como {self.char_name} ({self.char_id})")
                                            self.authenticated.emit(self.char_name, tokens)
                                        else:
                                            logger.error(f"AuthManager: Error verificando token: {verify_res.status_code} - {verify_res.text}")
                                    else:
                                        logger.error(f"AuthManager: Error intercambiando código: {res.status_code} - {res.text}")
                                except Exception as e:
                                    logger.error(f"AuthManager: Excepción en intercambio: {e}")
                                
                            # Responder al navegador
                            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                            response += "<h1>EVE iT Autenticado</h1><p>Ya puedes cerrar esta ventana y volver a la app.</p>"
                            conn.sendall(response.encode('utf-8'))
                except socket.timeout:
                    logger.warning("AuthManager: Login timeout — el usuario no completó el login en 60s.")
                except Exception as e:
                    logger.error(f"AuthManager: Server error: {e}", exc_info=True)

        threading.Thread(target=run_server, daemon=True).start()
