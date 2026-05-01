import pytest
from unittest.mock import MagicMock, patch
from core.esi_client import ESIClient
from core.contracts_models import ScanDiagnostics

def test_public_contracts_pagination():
    client = ESIClient()
    client._rate_limit = MagicMock()
    
    # Mock _fetch_public_contracts_page
    def mock_fetch(region_id, page):
        if page == 1:
            return [{"contract_id": 1, "type": "item_exchange", "status": "outstanding"}], 2
        if page == 2:
            return [{"contract_id": 2, "type": "item_exchange", "status": "outstanding"}], 2
        return [], 2
        
    client._fetch_public_contracts_page = MagicMock(side_effect=mock_fetch)
    
    diag = ScanDiagnostics()
    res = client.public_contracts(10000002, diagnostics=diag, force_refresh=True)
    
    assert len(res) == 2
    assert diag.esi_total_pages == 2
    assert diag.esi_pages_fetched == 2
    assert diag.esi_raw_contracts == 2
    assert diag.esi_unique_contracts == 2
    assert diag.esi_fetch_stopped_reason == "complete"

def test_public_contracts_deduplication():
    client = ESIClient()
    client._rate_limit = MagicMock()
    
    # Duplicate contract IDs across pages
    def mock_fetch(region_id, page):
        if page == 1:
            return [{"contract_id": 1, "type": "item_exchange", "status": "outstanding"}], 2
        if page == 2:
            return [{"contract_id": 1, "type": "item_exchange", "status": "outstanding"}], 2
        return [], 2
        
    client._fetch_public_contracts_page = MagicMock(side_effect=mock_fetch)
    
    diag = ScanDiagnostics()
    res = client.public_contracts(10000002, diagnostics=diag, force_refresh=True)
    
    assert len(res) == 1
    assert diag.esi_raw_contracts == 2
    assert diag.esi_unique_contracts == 1
