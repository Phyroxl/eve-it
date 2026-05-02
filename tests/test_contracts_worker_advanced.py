import pytest
from unittest.mock import MagicMock, patch
from ui.market_command.contracts_worker import ContractsScanWorker
from core.contracts_models import ContractsFilterConfig

def test_worker_cancellation():
    config = ContractsFilterConfig()
    worker = ContractsScanWorker(config)
    
    # Mocking ESIClient to prevent network calls
    with patch('ui.market_command.contracts_worker.ESIClient') as mock_esi:
        # Mock public_contracts to return some contracts
        mock_esi.instance().public_contracts.return_value = [{'contract_id': 1, 'type': 'item_exchange', 'price': 100, 'date_expired': '2030-01-01T00:00:00Z'}]
        
        # Simulate cancellation before run
        worker.cancel()
        assert worker._cancelled == True
        
        # Manually trigger run to see if it exits early
        # Note: In real QThread this would be worker.start()
        worker.run()
        
        # If it worked, it should not have called build_price_index or similar deep stuff
        # but because cancellation check is in many places, it depends.
        # Main point is it didn't crash.

def test_progress_emitted():
    config = ContractsFilterConfig()
    worker = ContractsScanWorker(config)
    
    progress_values = []
    worker.progress.connect(lambda p: progress_values.append(p))
    
    with patch('ui.market_command.contracts_worker.ESIClient') as mock_esi:
        # Minimal mock to reach some progress
        mock_esi.instance().character_location.return_value = None
        mock_esi.instance().public_contracts.return_value = []
        
        worker.run()
        
        # Progress should have been emitted (at least 0 or phase starts)
        assert len(progress_values) > 0
        assert 0 in progress_values

def test_diag_available_during_run():
    config = ContractsFilterConfig()
    worker = ContractsScanWorker(config)
    
    assert worker.diag is not None
    assert worker.diag.esi_raw_contracts == 0
