import unittest
import json
import os
import time
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Mock PySide6 BEFORE importing anything from core
from unittest.mock import MagicMock
mock_qt = MagicMock()
mock_qt.QtCore.QObject = object # Base class for signals
mock_qt.QtCore.Signal = lambda *args: MagicMock()
sys.modules['PySide6'] = mock_qt
sys.modules['PySide6.QtCore'] = mock_qt.QtCore
sys.modules['PySide6.QtWidgets'] = MagicMock()
sys.modules['PySide6.QtGui'] = MagicMock()

from core.auth_manager import AuthManager

class TestRealAuthManager(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        import shutil
        
        # Create temp dir
        self.test_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.test_dir.name)
        
        # Mock paths in AuthManager module
        import core.auth_manager
        self.old_config_path = core.auth_manager._CONFIG_FILE
        self.old_session_path = core.auth_manager._SESSION_FILE
        
        core.auth_manager._CONFIG_FILE = self.tmp_path / "eve_client.json"
        core.auth_manager._SESSION_FILE = self.tmp_path / "esi_session.json"
        
        # Reset Singleton for testing
        AuthManager._instance = None
        self.auth = AuthManager.instance()
        
        # Setup test config
        core.auth_manager._CONFIG_FILE.write_text(json.dumps({
            "client_id": "test_id", 
            "client_secret": "test_secret"
        }))

    def tearDown(self):
        import core.auth_manager
        core.auth_manager._CONFIG_FILE = self.old_config_path
        core.auth_manager._SESSION_FILE = self.old_session_path
        self.test_dir.cleanup()

    @patch('requests.post')
    def test_auto_refresh_on_get_token(self, mock_post):
        # Setup expired session
        self.auth.refresh_token = "valid_refresh_token"
        self.auth.expiry = time.time() - 100 # Expired
        
        # Mock successful refresh response
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "access_token": "new_access_token",
            "expires_in": 3600,
            "refresh_token": "rotated_refresh_token"
        }
        mock_post.return_value = mock_res
        
        # Act
        token = self.auth.get_valid_access_token()
        
        # Assert
        self.assertEqual(token, "new_access_token")
        self.assertEqual(self.auth.refresh_token, "rotated_refresh_token")
        self.assertTrue(self.session_path.exists())
        print("Real AuthManager Auto-Refresh: PASSED")

    @patch('requests.post')
    def test_handle_temporary_failure(self, mock_post):
        # Setup expired session
        self.auth.refresh_token = "valid_refresh_token"
        self.auth.current_token = "old_token"
        self.auth.expiry = time.time() - 100 # Expired
        
        # Mock 502 error
        mock_res = MagicMock()
        mock_res.status_code = 502
        mock_post.return_value = mock_res
        
        # Act
        token = self.auth.get_valid_access_token()
        
        # Assert
        self.assertIsNone(token) # Cannot return expired token
        self.assertFalse(self.auth.requires_reauth) # But should NOT require re-auth
        self.assertEqual(self.auth.refresh_token, "valid_refresh_token") # Should keep refresh token
        print("Real AuthManager Temporary Failure Handling: PASSED")

    @patch('requests.post')
    def test_handle_invalid_grant(self, mock_post):
        # Setup expired session
        self.auth.refresh_token = "bad_refresh_token"
        self.auth.expiry = time.time() - 100
        
        # Mock 400 invalid_grant
        mock_res = MagicMock()
        mock_res.status_code = 400
        mock_res.json.return_value = {"error": "invalid_grant"}
        mock_post.return_value = mock_res
        
        # Act
        token = self.auth.get_valid_access_token()
        
        # Assert
        self.assertIsNone(token)
        self.assertTrue(self.auth.requires_reauth)
        print("Real AuthManager Invalid Grant Handling: PASSED")

if __name__ == "__main__":
    unittest.main()
