"""
Tests para MarketHistoryCache sin conexion real a ESI.
Ejecutar: python tests/test_market_history_cache.py
"""
import sys, os, time, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.market_history_cache import MarketHistoryCache, HISTORY_CACHE_TTL_SECONDS

FAKE_REGION = 10000002
FAKE_TYPE = 12345
FAKE_HISTORY = [{'date': '2024-01-01', 'volume': 100, 'average': 1000.0}]


def make_isolated_cache(tmp_dir):
    """Crea una instancia de cache aislada apuntando a un archivo temporal."""
    cache = MarketHistoryCache.__new__(MarketHistoryCache)
    cache._data = {}
    cache._cache_file = os.path.join(tmp_dir, 'test_history_cache.json')
    return cache


def test_set_get():
    with tempfile.TemporaryDirectory() as tmp:
        cache = make_isolated_cache(tmp)
        cache.set(FAKE_REGION, FAKE_TYPE, FAKE_HISTORY)
        result = cache.get(FAKE_REGION, FAKE_TYPE)
        assert result == FAKE_HISTORY, f"Expected {FAKE_HISTORY}, got {result}"
        print("  [PASS] set/get")


def test_get_missing():
    with tempfile.TemporaryDirectory() as tmp:
        cache = make_isolated_cache(tmp)
        result = cache.get(FAKE_REGION, 99999)
        assert result is None, f"Expected None for missing key, got {result}"
        print("  [PASS] get missing key returns None")


def test_ttl_valid():
    with tempfile.TemporaryDirectory() as tmp:
        cache = make_isolated_cache(tmp)
        cache._data[cache._key(FAKE_REGION, FAKE_TYPE)] = {
            'timestamp': time.time() - 100,  # 100s ago, within TTL
            'history': FAKE_HISTORY
        }
        result = cache.get(FAKE_REGION, FAKE_TYPE)
        assert result == FAKE_HISTORY, "TTL within range should return data"
        print("  [PASS] TTL valid (recent entry)")


def test_ttl_expired():
    with tempfile.TemporaryDirectory() as tmp:
        cache = make_isolated_cache(tmp)
        cache._data[cache._key(FAKE_REGION, FAKE_TYPE)] = {
            'timestamp': time.time() - HISTORY_CACHE_TTL_SECONDS - 1,  # expired
            'history': FAKE_HISTORY
        }
        result = cache.get(FAKE_REGION, FAKE_TYPE)
        assert result is None, f"Expired TTL should return None, got {result}"
        print("  [PASS] TTL expired returns None")


def test_get_many():
    with tempfile.TemporaryDirectory() as tmp:
        cache = make_isolated_cache(tmp)
        cache.set(FAKE_REGION, 1, [{'date': 'a'}])
        cache.set(FAKE_REGION, 2, [{'date': 'b'}])
        result = cache.get_many(FAKE_REGION, [1, 2, 3])
        assert 1 in result and 2 in result, "Expected keys 1 and 2"
        assert 3 not in result, "Key 3 should be missing"
        print("  [PASS] get_many: hits and misses")


def test_save_load():
    with tempfile.TemporaryDirectory() as tmp:
        cache1 = make_isolated_cache(tmp)
        cache1.set(FAKE_REGION, FAKE_TYPE, FAKE_HISTORY)
        cache1.save()

        cache2 = make_isolated_cache(tmp)
        cache2._load()
        result = cache2.get(FAKE_REGION, FAKE_TYPE)
        assert result == FAKE_HISTORY, f"Data should persist after save/load. Got: {result}"
        print("  [PASS] save/load persistence")


def test_corrupt_file_renamed():
    with tempfile.TemporaryDirectory() as tmp:
        cache_file = os.path.join(tmp, 'test_history_cache.json')
        with open(cache_file, 'w') as f:
            f.write("{ not valid json @@@ }")

        cache = make_isolated_cache(tmp)
        cache._cache_file = cache_file
        cache._load()

        # Cache debe estar vacio
        assert cache._data == {}, "Cache should be empty after corrupt file"
        # Archivo original debe haber sido renombrado
        files = os.listdir(tmp)
        corrupt_files = [f for f in files if '.corrupt.' in f]
        assert len(corrupt_files) == 1, f"Expected 1 corrupt file, found: {files}"
        print("  [PASS] corrupt file renamed, cache starts empty")


def test_expired_entries_cleaned_on_load():
    with tempfile.TemporaryDirectory() as tmp:
        cache_file = os.path.join(tmp, 'test_history_cache.json')
        raw = {
            f"{FAKE_REGION}:1": {'timestamp': time.time() - 1, 'history': FAKE_HISTORY},
            f"{FAKE_REGION}:2": {'timestamp': time.time() - HISTORY_CACHE_TTL_SECONDS - 1, 'history': []},
        }
        with open(cache_file, 'w') as f:
            json.dump(raw, f)

        cache = make_isolated_cache(tmp)
        cache._cache_file = cache_file
        cache._load()

        assert cache.get(FAKE_REGION, 1) == FAKE_HISTORY, "Valid entry should be loaded"
        assert cache.get(FAKE_REGION, 2) is None, "Expired entry should be cleaned on load"
        print("  [PASS] expired entries cleaned on load")


def run_tests():
    print("\n=== test_market_history_cache ===\n")
    tests = [
        test_set_get,
        test_get_missing,
        test_ttl_valid,
        test_ttl_expired,
        test_get_many,
        test_save_load,
        test_corrupt_file_renamed,
        test_expired_entries_cleaned_on_load,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
