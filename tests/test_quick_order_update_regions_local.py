"""
Tests for load/save logic of quick_order_update_regions.json.
Ensures graceful handling of missing files (local profile support).
"""
import unittest
import os
import json
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.quick_order_update_config import (
    load_quick_order_update_regions,
    save_quick_order_update_regions
)

class TestQuickOrderUpdateRegionsLocal(unittest.TestCase):
    def setUp(self):
        # Patch the regions path for testing
        import core.quick_order_update_config as mod
        self.orig_path = mod._REGIONS_PATH
        self.test_fd, self.test_path = tempfile.mkstemp(suffix=".json")
        os.close(self.test_fd)
        os.remove(self.test_path) # start with missing file
        mod._REGIONS_PATH = self.test_path

    def tearDown(self):
        import core.quick_order_update_config as mod
        mod._REGIONS_PATH = self.orig_path
        if os.path.exists(self.test_path):
            os.remove(self.test_path)

    def test_load_missing_file_returns_none_template(self):
        """Should return {"sell": None, "buy": None} if file is absent."""
        res = load_quick_order_update_regions()
        self.assertEqual(res, {"sell": None, "buy": None})

    def test_save_and_load_consistency(self):
        """Should be able to save and then load the same data."""
        data = {
            "sell": {"region": {"x_min_ratio": 0.1, "y_min_ratio": 0.2, "x_max_ratio": 0.3, "y_max_ratio": 0.4}, "quantity_column": None, "price_column": None},
            "buy": None
        }
        success = save_quick_order_update_regions(data)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.test_path))
        
        loaded = load_quick_order_update_regions()
        self.assertEqual(loaded, data)

    def test_load_corrupt_file_returns_none_template(self):
        """Should handle corrupt JSON by returning the default template."""
        with open(self.test_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")
        
        res = load_quick_order_update_regions()
        self.assertEqual(res, {"sell": None, "buy": None})

if __name__ == "__main__":
    unittest.main()
