"""
tests/test_pack2_fixes.py — Pack 2 UX/data fix coverage.
Tests that do NOT require a QApplication (pure logic / unit tests).
"""
import unittest


class TestPerformanceNextSyncInitialized(unittest.TestCase):
    """_next_sync_seconds must be set before setup_ui() is called."""

    def test_attribute_exists_in_source(self):
        import ast, pathlib
        src = pathlib.Path("ui/market_command/performance_view.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "MarketPerformanceView":
                for item in ast.walk(node):
                    if (isinstance(item, ast.Assign) and
                            any(isinstance(t, ast.Attribute) and t.attr == "_next_sync_seconds"
                                for t in item.targets)):
                        return  # found
        self.fail("_next_sync_seconds not assigned in MarketPerformanceView.__init__")


class TestTradeProfitsTaxCachePerLocation(unittest.TestCase):
    """TradeProfitsWorker.run must cache tax lookups per loc_id (not per transaction)."""

    def test_tax_cache_dict_in_source(self):
        import pathlib
        src = pathlib.Path("ui/market_command/my_orders_view.py").read_text(encoding="utf-8")
        self.assertIn("tax_cache", src,
                      "tax_cache dict not found — get_effective_taxes is still called per transaction")
        self.assertIn("tax_cache[loc_id]", src)

    def test_tax_cache_logic(self):
        """Simulate the caching logic: same loc_id should only produce one lookup."""
        call_count = 0

        def fake_get_effective_taxes(char_id, loc_id, token):
            nonlocal call_count
            call_count += 1
            return (4.5, 1.2, "test", {})

        tax_cache = {}
        transactions = [
            {"location_id": 60003760},
            {"location_id": 60003760},
            {"location_id": 60004588},
            {"location_id": 60004588},
            {"location_id": 60004588},
        ]
        for t in transactions:
            loc_id = t["location_id"]
            if loc_id not in tax_cache:
                s, b, _, _ = fake_get_effective_taxes(0, loc_id, None)
                tax_cache[loc_id] = (s, b)

        self.assertEqual(call_count, 2,
                         f"Expected 2 tax lookups (one per unique loc_id), got {call_count}")


class TestScanCategoryNoSizeLimit(unittest.TestCase):
    """Phase 2 category scan must use all market type_ids, not the old _BROAD_POOL_SIZE cap."""

    def test_broad_pool_not_limiting_phase2(self):
        import pathlib
        src = pathlib.Path("ui/market_command/refresh_worker.py").read_text(encoding="utf-8")
        # The fix stores _all_market_type_ids after building temp_grouped
        self.assertIn("_all_market_type_ids", src,
                      "_all_market_type_ids not stored — category scan is still capped")

    def test_phase1_no_slice_on_final_pool(self):
        import pathlib
        src = pathlib.Path("ui/market_command/refresh_worker.py").read_text(encoding="utf-8")
        # Phase 1 should iterate final_pool_cands without [:_BROAD_POOL_SIZE] slice
        self.assertNotIn("final_pool_cands[:_BROAD_POOL_SIZE]", src,
                         "Phase 1 still slices final_pool_cands by _BROAD_POOL_SIZE")


class TestScanOverlayTransparentForMouse(unittest.TestCase):
    """Scan overlay must have WA_TransparentForMouseEvents so it never blocks interaction."""

    def test_transparent_attribute_in_source(self):
        import pathlib
        src = pathlib.Path("ui/market_command/simple_view.py").read_text(encoding="utf-8")
        self.assertIn("WA_TransparentForMouseEvents", src,
                      "Scan overlay does not set WA_TransparentForMouseEvents")
        self.assertIn("_scan_overlay", src)


class TestTradeProfitsDialogFixes(unittest.TestCase):
    """TradeProfitsDialog structural fixes: no duplicate btn_global, error signal connected."""

    def test_no_duplicate_btn_global(self):
        import pathlib
        src = pathlib.Path("ui/market_command/my_orders_view.py").read_text(encoding="utf-8")
        count = src.count("fl.addWidget(self.btn_global)")
        self.assertEqual(count, 1,
                         f"btn_global added to layout {count} times (expected 1)")

    def test_error_signal_connected(self):
        import pathlib
        src = pathlib.Path("ui/market_command/my_orders_view.py").read_text(encoding="utf-8")
        self.assertIn("worker.error.connect", src,
                      "TradeProfitsWorker.error signal not connected in load_data")

    def test_refresh_theme_method_exists(self):
        import pathlib
        src = pathlib.Path("ui/market_command/my_orders_view.py").read_text(encoding="utf-8")
        self.assertIn("def refresh_theme(self):", src,
                      "TradeProfitsDialog.refresh_theme method not found")


class TestHoverTooltipsPrecomputed(unittest.TestCase):
    """on_bar_hovered must use precomputed tooltips, not live CostBasisService calls."""

    def test_chart_hover_tooltips_stored(self):
        import pathlib
        src = pathlib.Path("ui/market_command/my_orders_view.py").read_text(encoding="utf-8")
        self.assertIn("_chart_hover_tooltips", src,
                      "_chart_hover_tooltips not found — hover tooltips not precomputed")

    def test_on_bar_hovered_no_live_import(self):
        import ast, pathlib
        src = pathlib.Path("ui/market_command/my_orders_view.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "on_bar_hovered":
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        self.fail("on_bar_hovered contains a live import (still doing on-hover work)")
                    if isinstance(child, ast.ImportFrom):
                        self.fail(f"on_bar_hovered contains a live 'from ... import' ({child.module})")
                return
        self.fail("on_bar_hovered method not found")


if __name__ == "__main__":
    unittest.main()
