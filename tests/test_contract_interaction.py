import pytest
from unittest.mock import MagicMock, patch
from core.esi_client import ESIClient

def test_open_contract_window_uses_correct_params():
    client = ESIClient()
    client.session = MagicMock()
    
    # Mock _request_auth to return a fake response
    mock_res = MagicMock()
    mock_res.status_code = 204
    client._request_auth = MagicMock(return_value=mock_res)
    
    res = client.open_contract_window(12345, "fake_token")
    
    assert res is True
    client._request_auth.assert_called_once()
    args, kwargs = client._request_auth.call_args
    assert args[0] == "POST"
    assert args[1] == "/ui/openwindow/contract/"
    assert args[2] == "fake_token"
    assert kwargs['params'] == {'contract_id': 12345}

def test_open_contract_window_missing_scope():
    client = ESIClient()
    mock_res = MagicMock()
    mock_res.status_code = 403
    client._request_auth = MagicMock(return_value=mock_res)
    
    res = client.open_contract_window(12345, "fake_token")
    assert res == "missing_scope"
