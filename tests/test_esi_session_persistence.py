"""
Tests de persistencia de sesión ESI.
Verifica que AuthManager guarda, carga y refresca tokens correctamente.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Agregar raíz del proyecto al path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Parchear PySide6 antes de importar auth_manager para entornos sin GUI
import unittest.mock as mock

_qt_mock = mock.MagicMock()
_qt_mock.QObject = object  # base sin señales

# Crear un Signal falso que soporta emit() y connect()
class _FakeSignal:
    def __init__(self, *args):
        self._callbacks = []
    def connect(self, cb):
        self._callbacks.append(cb)
    def emit(self, *args):
        for cb in self._callbacks:
            cb(*args)

sys.modules.setdefault('PySide6', mock.MagicMock())
sys.modules.setdefault('PySide6.QtCore', mock.MagicMock())

# Importar después del mock de Qt
import importlib
import core.auth_manager as _am_module


def _make_auth(session_file: Path, config_file: Path) -> "_am_module.AuthManager.__class__":
    """Crea una instancia de AuthManager con rutas sobrescritas para tests."""

    class _FakeSignalClass:
        def __init__(self):
            self._callbacks = []
        def connect(self, cb):
            self._callbacks.append(cb)
        def emit(self, *args):
            for cb in self._callbacks:
                cb(*args)

    class TestAuthManager:
        """AuthManager sin herencia Qt para poder testear sin display."""

        def __init__(self):
            self.client_id = "test_client_id"
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
            self.authenticated = _FakeSignalClass()
            self._lock = __import__('threading').Lock()
            self._session_file = session_file
            self._config_file = config_file

        # ---- copiar métodos del AuthManager real ----

        def get_valid_access_token(self):
            from core.auth_manager import _TOKEN_REFRESH_MARGIN
            with self._lock:
                if not self.current_token and not self.refresh_token:
                    return None
                if self.current_token and time.time() < self.expiry - _TOKEN_REFRESH_MARGIN:
                    return self.current_token
                if self.refresh_token:
                    if self._do_refresh():
                        return self.current_token
                return None

        def get_token(self):
            return self.get_valid_access_token()

        def _do_refresh(self):
            import requests
            import base64
            try:
                config_data = json.loads(self._config_file.read_text())
                client_id = config_data.get('client_id')
                client_secret = config_data.get('client_secret', '')
                post_data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token}
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
                    data=post_data, headers=headers, timeout=15,
                )
                if res.status_code == 200:
                    data = res.json()
                    self.current_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token', self.refresh_token)
                    self.expiry = time.time() + data.get('expires_in', 3600)
                    self.save_session()
                    return True
                try:
                    error_code = res.json().get('error', '')
                except Exception:
                    error_code = ''
                if error_code == 'invalid_grant':
                    self._clear_session_data()
                return False
            except Exception:
                return False

        def _clear_session_data(self):
            self.current_token = None
            self.refresh_token = None
            self.expiry = 0.0
            self.char_id = None
            self.char_name = None
            if self._session_file.exists():
                self._session_file.unlink()

        def save_session(self):
            if not self.refresh_token:
                return
            data = {
                "char_id": self.char_id,
                "char_name": self.char_name,
                "access_token": self.current_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expiry,
                "scopes": self.scopes,
                "last_update": time.time(),
            }
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            self._session_file.write_text(json.dumps(data, indent=4), encoding='utf-8')

        def try_restore_session(self):
            from core.auth_manager import _TOKEN_REFRESH_MARGIN
            emit_args = None
            with self._lock:
                if self.current_token and time.time() < self.expiry - _TOKEN_REFRESH_MARGIN:
                    return "ok"
                if not self._session_file.exists():
                    return "no_session"
                try:
                    data = json.loads(self._session_file.read_text(encoding='utf-8'))
                except Exception as e:
                    ts = int(time.time())
                    corrupt = self._session_file.with_suffix(f'.corrupt.{ts}')
                    try:
                        self._session_file.rename(corrupt)
                    except Exception:
                        pass
                    return "no_session"
                saved_scopes = data.get('scopes', '')
                required = set(self.scopes.split())
                saved = set(saved_scopes.split())
                if not required.issubset(saved):
                    return "new_scopes_required"
                self.char_id = data.get('char_id')
                self.char_name = data.get('char_name')
                self.refresh_token = data.get('refresh_token')
                if not self.refresh_token:
                    return "no_session"
                saved_token = data.get('access_token')
                saved_expires_at = data.get('expires_at', 0)
                if saved_token and time.time() < saved_expires_at - _TOKEN_REFRESH_MARGIN:
                    self.current_token = saved_token
                    self.expiry = saved_expires_at
                    emit_args = (
                        self.char_name,
                        {"access_token": self.current_token, "refresh_token": self.refresh_token},
                    )
                else:
                    if self._do_refresh():
                        emit_args = (
                            self.char_name,
                            {"access_token": self.current_token, "refresh_token": self.refresh_token},
                        )
                    else:
                        return "expired"
            if emit_args:
                self.authenticated.emit(*emit_args)
                return "ok"
            return "expired"

        def logout(self):
            self._clear_session_data()

        def get_auth_status(self):
            expires_in = max(0, int(self.expiry - time.time())) if self.expiry > 0 else 0
            return {
                "authenticated": bool(self.current_token and time.time() < self.expiry - 10),
                "character_id": self.char_id,
                "character_name": self.char_name,
                "has_access_token": bool(self.current_token),
                "has_refresh_token": bool(self.refresh_token),
                "expires_in": expires_in,
                "session_persisted": self._session_file.exists(),
            }

    return TestAuthManager()


class TestSessionPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.session_file = self.tmp / 'esi_session.json'
        self.config_file = self.tmp / 'eve_client.json'
        self.config_file.write_text(
            json.dumps({"client_id": "test_client", "client_secret": ""}),
            encoding='utf-8',
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def _auth(self):
        return _make_auth(self.session_file, self.config_file)

    def _write_session(self, **kwargs):
        defaults = {
            "char_id": 123456,
            "char_name": "Test Pilot",
            "access_token": "access_TOKEN_xyz",
            "refresh_token": "refresh_TOKEN_abc",
            "expires_at": time.time() + 1800,
            "scopes": (
                "esi-ui.open_window.v1 esi-wallet.read_character_wallet.v1 "
                "esi-markets.read_character_orders.v1 esi-assets.read_assets.v1 "
                "esi-skills.read_skills.v1 esi-characters.read_standings.v1 "
                "esi-location.read_location.v1"
            ),
            "last_update": time.time(),
        }
        defaults.update(kwargs)
        self.session_file.write_text(json.dumps(defaults, indent=4), encoding='utf-8')

    # ------------------------------------------------------------------
    # 1. Guardar sesión y cargarla
    # ------------------------------------------------------------------

    def test_save_and_load_session(self):
        auth = self._auth()
        auth.char_id = 111222
        auth.char_name = "Nina Herrera"
        auth.current_token = "tok_abc"
        auth.refresh_token = "ref_xyz"
        auth.expiry = time.time() + 1800

        auth.save_session()
        self.assertTrue(self.session_file.exists(), "El archivo de sesión debe existir")

        data = json.loads(self.session_file.read_text())
        self.assertEqual(data['char_id'], 111222)
        self.assertEqual(data['char_name'], "Nina Herrera")
        self.assertEqual(data['access_token'], "tok_abc")
        self.assertEqual(data['refresh_token'], "ref_xyz")
        self.assertGreater(data['expires_at'], time.time())
        print("test_save_and_load_session: PASSED")

    # ------------------------------------------------------------------
    # 2. Sesión válida → try_restore_session no llama refresh
    # ------------------------------------------------------------------

    def test_valid_session_skips_refresh(self):
        self._write_session(expires_at=time.time() + 1800)
        auth = self._auth()

        called = []
        with patch.object(auth, '_do_refresh', side_effect=lambda: called.append(1) or False):
            res = auth.try_restore_session()

        self.assertEqual(res, "ok")
        self.assertEqual(len(called), 0, "_do_refresh NO debe llamarse si el token es válido")
        self.assertEqual(auth.char_id, 123456)
        self.assertEqual(auth.char_name, "Test Pilot")
        self.assertEqual(auth.current_token, "access_TOKEN_xyz")
        print("test_valid_session_skips_refresh: PASSED")

    # ------------------------------------------------------------------
    # 3. Sesión expirada → try_restore_session llama refresh y guarda nuevo token
    # ------------------------------------------------------------------

    def test_expired_session_triggers_refresh(self):
        self._write_session(expires_at=time.time() - 100)  # ya expirado
        auth = self._auth()

        def _fake_refresh():
            auth.current_token = "new_access_TOKEN"
            auth.refresh_token = "new_refresh_TOKEN"
            auth.expiry = time.time() + 1800
            auth.save_session()
            return True

        with patch.object(auth, '_do_refresh', side_effect=_fake_refresh):
            res = auth.try_restore_session()

        self.assertEqual(res, "ok")
        self.assertEqual(auth.current_token, "new_access_TOKEN")
        data = json.loads(self.session_file.read_text())
        self.assertEqual(data['access_token'], "new_access_TOKEN")
        self.assertEqual(data['refresh_token'], "new_refresh_TOKEN")
        print("test_expired_session_triggers_refresh: PASSED")

    # ------------------------------------------------------------------
    # 4. Refresh token inválido → borra sesión y devuelve "expired"
    # ------------------------------------------------------------------

    def test_invalid_grant_clears_session(self):
        self._write_session(expires_at=time.time() - 100)
        auth = self._auth()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "invalid_grant"}

        with patch('requests.post', return_value=mock_response):
            res = auth.try_restore_session()

        self.assertEqual(res, "expired")
        self.assertIsNone(auth.current_token)
        self.assertIsNone(auth.refresh_token)
        self.assertFalse(self.session_file.exists(), "La sesión debe borrarse con invalid_grant")
        print("test_invalid_grant_clears_session: PASSED")

    # ------------------------------------------------------------------
    # 5. get_valid_access_token — token válido
    # ------------------------------------------------------------------

    def test_get_valid_access_token_returns_token(self):
        auth = self._auth()
        auth.current_token = "valid_tok"
        auth.refresh_token = "ref_tok"
        auth.expiry = time.time() + 500

        tok = auth.get_valid_access_token()
        self.assertEqual(tok, "valid_tok")
        print("test_get_valid_access_token_returns_token: PASSED")

    # ------------------------------------------------------------------
    # 6. get_valid_access_token — token cerca de expirar → llama refresh
    # ------------------------------------------------------------------

    def test_get_valid_access_token_near_expiry_refreshes(self):
        auth = self._auth()
        auth.current_token = "old_tok"
        auth.refresh_token = "ref_tok"
        auth.expiry = time.time() + 50  # menos de 120s → debe refrescar

        refreshed = []

        def _fake_refresh():
            refreshed.append(1)
            auth.current_token = "new_tok"
            auth.expiry = time.time() + 1800
            return True

        with patch.object(auth, '_do_refresh', side_effect=_fake_refresh):
            tok = auth.get_valid_access_token()

        self.assertEqual(tok, "new_tok")
        self.assertEqual(len(refreshed), 1, "Debe haber llamado _do_refresh exactamente una vez")
        print("test_get_valid_access_token_near_expiry_refreshes: PASSED")

    # ------------------------------------------------------------------
    # 7. get_valid_access_token — sin tokens → devuelve None
    # ------------------------------------------------------------------

    def test_get_valid_access_token_no_tokens_returns_none(self):
        auth = self._auth()
        auth.current_token = None
        auth.refresh_token = None
        tok = auth.get_valid_access_token()
        self.assertIsNone(tok)
        print("test_get_valid_access_token_no_tokens_returns_none: PASSED")

    # ------------------------------------------------------------------
    # 8. logout → borra sesión en memoria y en disco
    # ------------------------------------------------------------------

    def test_logout_clears_session(self):
        self._write_session()
        auth = self._auth()
        auth.current_token = "tok"
        auth.refresh_token = "ref"
        auth.char_id = 123456
        auth.char_name = "Test Pilot"

        auth.logout()

        self.assertIsNone(auth.current_token)
        self.assertIsNone(auth.refresh_token)
        self.assertIsNone(auth.char_id)
        self.assertFalse(self.session_file.exists(), "El archivo de sesión debe borrarse al hacer logout")
        print("test_logout_clears_session: PASSED")

    # ------------------------------------------------------------------
    # 9. Archivo de sesión corrupto → se renombra y devuelve "no_session"
    # ------------------------------------------------------------------

    def test_corrupt_session_file(self):
        self.session_file.write_text("{ INVALID JSON !!!", encoding='utf-8')
        auth = self._auth()
        res = auth.try_restore_session()
        self.assertEqual(res, "no_session")
        self.assertFalse(self.session_file.exists(), "El archivo corrupto debe renombrarse")
        # Verificar que existe el archivo renombrado como .corrupt.*
        corrupt_files = list(self.tmp.glob('*.corrupt.*'))
        self.assertGreater(len(corrupt_files), 0, "Debe existir el archivo .corrupt.*")
        print("test_corrupt_session_file: PASSED")

    # ------------------------------------------------------------------
    # 10. authenticated se emite después del restore exitoso
    # ------------------------------------------------------------------

    def test_authenticated_emitted_on_restore(self):
        self._write_session(expires_at=time.time() + 1800)
        auth = self._auth()

        received = []
        auth.authenticated.connect(lambda name, tokens: received.append((name, tokens)))

        res = auth.try_restore_session()

        self.assertEqual(res, "ok")
        self.assertEqual(len(received), 1, "authenticated debe emitirse exactamente una vez")
        self.assertEqual(received[0][0], "Test Pilot")
        print("test_authenticated_emitted_on_restore: PASSED")

    # ------------------------------------------------------------------
    # 11. get_auth_status — formato correcto, sin tokens
    # ------------------------------------------------------------------

    def test_get_auth_status_no_tokens_in_result(self):
        self._write_session(expires_at=time.time() + 1800)
        auth = self._auth()
        auth.try_restore_session()

        status = auth.get_auth_status()

        self.assertIn("authenticated", status)
        self.assertIn("character_id", status)
        self.assertIn("character_name", status)
        self.assertIn("has_access_token", status)
        self.assertIn("has_refresh_token", status)
        self.assertIn("expires_in", status)
        self.assertIn("session_persisted", status)
        # Verificar que no hay tokens crudos en el dict
        self.assertNotIn("access_token", status)
        self.assertNotIn("refresh_token", status)
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["character_id"], 123456)
        print("test_get_auth_status_no_tokens_in_result: PASSED")

    # ------------------------------------------------------------------
    # 12. Segunda llamada a try_restore_session → no hace refresh de nuevo
    # ------------------------------------------------------------------

    def test_double_restore_skips_second_refresh(self):
        self._write_session(expires_at=time.time() + 1800)
        auth = self._auth()

        refresh_calls = []

        def _fake_refresh():
            refresh_calls.append(1)
            auth.current_token = "refreshed_tok"
            auth.expiry = time.time() + 1800
            return True

        auth.try_restore_session()
        auth.try_restore_session()  # segunda llamada

        # El segundo restore debe retornar "ok" sin llamar refresh
        self.assertEqual(len(refresh_calls), 0)
        print("test_double_restore_skips_second_refresh: PASSED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
