import unittest
from core.contracts_models import ContractItem, ContractArbitrageResult, ContractsFilterConfig
from core.contracts_engine import analyze_contract_items, calculate_contract_metrics, apply_contracts_filters

class TestContractBlueprintFilters(unittest.TestCase):
    def setUp(self):
        self.config = ContractsFilterConfig(
            profit_min_isk=1_000_000,
            roi_min_pct=5.0,
            exclude_blueprints=True,
            exclude_bpcs=True
        )
        self.price_index = {
            100: {'best_sell': 200_000_000.0, 'best_buy': 180_000_000.0}, # BPO price
            200: {'best_sell': 10_000_000.0, 'best_buy': 8_000_000.0}     # Normal item
        }
        self.name_map = {
            100: "Wasp I Blueprint",
            200: "Tritanium"
        }

    def test_bpc_valuation_is_zero(self):
        # Case: Contract with a BPC that has a high BPO market price
        items_raw = [
            {'type_id': 100, 'quantity': 1, 'is_included': True, 'is_blueprint_copy': True}
        ]
        # metadata_map: category_id 9 is Blueprint
        metadata_map = {100: {'category_id': 9}}
        
        items = analyze_contract_items(items_raw, self.price_index, self.name_map, self.config, metadata_map)
        self.assertTrue(items[0].is_copy)
        self.assertEqual(items[0].valuation_status, "bpc_ignored")
        
        contract_raw = {'price': 5_000_000.0, 'contract_id': 1}
        result = calculate_contract_metrics(contract_raw, items, self.config)
        
        # Jita sell value should be 0 because BPC is ignored
        self.assertEqual(result.jita_sell_value, 0.0)
        self.assertLess(result.net_profit, 0) # Should be negative profit (cost of contract)
        self.assertIn("Contiene BPC", result.valuation_warning)

    def test_exclude_blueprints_filter(self):
        # Case: exclude_blueprints=True, contract has a BPO
        items_raw = [
            {'type_id': 100, 'quantity': 1, 'is_included': True, 'is_blueprint_copy': False}
        ]
        metadata_map = {100: {'category_id': 9}}
        items = analyze_contract_items(items_raw, self.price_index, self.name_map, self.config, metadata_map)
        
        contract_raw = {'price': 50_000_000.0, 'contract_id': 1}
        result = calculate_contract_metrics(contract_raw, items, self.config)
        
        # Filter it
        filtered = apply_contracts_filters([result], self.config)
        self.assertEqual(len(filtered), 0)

    def test_exclude_bpcs_only(self):
        # Case: exclude_blueprints=False, exclude_bpcs=True
        self.config.exclude_blueprints = False
        self.config.exclude_bpcs = True
        
        # 1. BPO should pass
        items_bpo = analyze_contract_items(
            [{'type_id': 100, 'quantity': 1, 'is_included': True, 'is_blueprint_copy': False}],
            self.price_index, self.name_map, self.config, {100: {'category_id': 9}}
        )
        res_bpo = calculate_contract_metrics({'price': 50_000_000.0, 'contract_id': 1}, items_bpo, self.config)
        # Manually set high profit so it passes other filters
        res_bpo.net_profit = 100_000_000
        res_bpo.roi_pct = 200
        
        filtered_bpo = apply_contracts_filters([res_bpo], self.config)
        self.assertEqual(len(filtered_bpo), 1)
        
        # 2. BPC should be excluded
        items_bpc = analyze_contract_items(
            [{'type_id': 100, 'quantity': 1, 'is_included': True, 'is_blueprint_copy': True}],
            self.price_index, self.name_map, self.config, {100: {'category_id': 9}}
        )
        res_bpc = calculate_contract_metrics({'price': 1_000_000.0, 'contract_id': 2}, items_bpc, self.config)
        filtered_bpc = apply_contracts_filters([res_bpc], self.config)
        self.assertEqual(len(filtered_bpc), 0)

    def test_partial_valuation_with_mix(self):
        # Case: Normal items + BPC
        items_raw = [
            {'type_id': 200, 'quantity': 1, 'is_included': True}, # Tritanium: 10M
            {'type_id': 100, 'quantity': 1, 'is_included': True, 'is_blueprint_copy': True} # BPC
        ]
        metadata_map = {100: {'category_id': 9}, 200: {'category_id': 18}}
        items = analyze_contract_items(items_raw, self.price_index, self.name_map, self.config, metadata_map)
        
        contract_raw = {'price': 2_000_000.0, 'contract_id': 1}
        result = calculate_contract_metrics(contract_raw, items, self.config)
        
        # Only Tritanium should count
        self.assertEqual(result.jita_sell_value, 10_000_000.0)
        self.assertIn("Contiene BPC", result.valuation_warning)

if __name__ == '__main__':
    unittest.main()
