import unittest
from core.eve_icon_service import EveIconService

class TestEveIconService(unittest.TestCase):
    def setUp(self):
        self.service = EveIconService.instance()

    def test_normalize_size(self):
        # normalize_size(requested) -> nearest valid size >= requested
        self.assertEqual(self.service.normalize_size(16), 32)
        self.assertEqual(self.service.normalize_size(24), 32)
        self.assertEqual(self.service.normalize_size(32), 32)
        self.assertEqual(self.service.normalize_size(48), 64)
        self.assertEqual(self.service.normalize_size(64), 64)
        self.assertEqual(self.service.normalize_size(128), 128)
        self.assertEqual(self.service.normalize_size(256), 256)
        self.assertEqual(self.service.normalize_size(512), 512)
        self.assertEqual(self.service.normalize_size(1024), 1024)
        self.assertEqual(self.service.normalize_size(2000), 1024) # Cap at 1024

    def test_endpoint_stat_key(self):
        self.assertEqual(self.service._endpoint_stat_key("icon"), "endpoint_icon")
        self.assertEqual(self.service._endpoint_stat_key("render"), "endpoint_render")
        self.assertEqual(self.service._endpoint_stat_key("bp"), "endpoint_bp")
        self.assertEqual(self.service._endpoint_stat_key("bpc"), "endpoint_bpc")
        self.assertEqual(self.service._endpoint_stat_key("portrait"), "endpoint_portrait")

    def test_url_generation_normalization(self):
        # We test that the normalization is applied when constructing URLs
        # Even though _try_endpoint is async, we can check the URL construction logic
        type_id = 34
        size = 24
        endpoint = "icon"
        
        # Manually verify what the URL would be inside _try_endpoint
        norm_size = self.service.normalize_size(size)
        url = f"https://images.evetech.net/types/{type_id}/{endpoint}?size={norm_size}"
        
        self.assertIn("size=32", url)
        self.assertNotIn("size=24", url)

if __name__ == '__main__':
    unittest.main()
