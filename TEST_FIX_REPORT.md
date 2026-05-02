# Test Fix Report — eve-it-main
**Date:** 2026-05-02  
**Branch:** main  
**Last commit before fixes:** 67f7b96

---

## Summary

Starting state: multiple test failures across the suite (contracts, visual detector, UI, freshness validation).  
Ending state: **704+ tests pass**. 3 files excluded due to a pre-existing Windows/Qt process isolation crash (not introduced by these fixes).

---

## Fixes Applied

### 1. `core/contracts_engine.py`
**Problem:** `diagnostics.profitable` counter never incremented when `net_profit == 0.0`.  
**Root cause:** Guard used strict `> 0` instead of `>= 0`.  
**Fix:**
```python
# Before
if c.net_profit > 0 and c.jita_sell_value > 0:
# After
if c.net_profit >= 0 and c.jita_sell_value > 0:
```

---

### 2. `core/eve_market_visual_detector.py`
Three separate bugs:

**A — `filtered_candidate_bands` missing from debug output**  
The key was never set in the result dict, causing KeyError in tests that read `result["debug"]["filtered_candidate_bands"]`.  
**Fix:** Added `result["debug"]["filtered_candidate_bands"] = filtered` after `blue_bands_found`.

**B — Acceptance criteria ignored `marker_required=False`**  
When `marker_required=False`, candidates were still rejected because the condition required `own_marker=True`.  
**Fix:**
```python
# Before
if (own_marker or (is_buy_order and is_background_band)) and price_ok:
# After
marker_ok = (own_marker or (is_buy_order and is_background_band)) or not self.marker_required
if marker_ok and price_ok:
```

**C — Final score gate also blocked on marker even when not required**  
**Fix:**
```python
marker_waived = not self.marker_required and best["matched_price"]
if best["score"] >= (self.score_threshold - 50) \
   or (best["matched_own_marker"] and best["matched_price"]) \
   or marker_waived:
```

**D — OCR backend errors were not granular**  
Tests expected specific error codes (`ocr_backend_unavailable_module_missing`, `ocr_backend_unavailable_tesseract_executable_missing`) but code returned a single generic string.  
**Fix:** Added early detection block before `_run_detection_pass` with two distinct error codes.

---

### 3. `ui/market_command/simple_view.py`
**Problem:** Tooltip labels used `snake_case` strings but tests searched for `"Gross"` and `"Sales Tax"`.  
**Fix:** Capitalized labels:
```python
# Before
f"  gross_spread:    {format_isk(...)} ISK\n"
f"  sales_tax_pct:   {bd['sales_tax_pct']:.2f}%\n"
# After
f"  Gross Spread:    {format_isk(...)} ISK\n"
f"  Sales Tax pct:   {bd['sales_tax_pct']:.2f}%\n"
```

---

### 4. `tests/test_contract_filters_boundary.py` + `test_contract_items_preservation.py` + `test_contract_ui_consistency.py`
**Problem:** `ContractsFilterConfig.capital_min_isk` defaults to `1_000_000` ISK, but test contracts used `contract_cost=1000.0` and were filtered out silently.  
**Fix:** Added `capital_min_isk=0` to all affected `ContractsFilterConfig(...)` calls.

**Additional in `test_contract_ui_consistency.py`:**  
`ContractArbitrageResult` constructor required 14 positional fields; test was only passing 4.  
**Fix:** Supplied all 14 fields including `jita_sell_value`, `jita_buy_value`, `gross_profit`, `net_profit`, `roi_pct`, `value_concentration`, `has_unresolved_items`, `unresolved_count`, `score`.

---

### 5. `tests/test_eve_market_visual_detector.py`
**Problem:** Spy function used in `TestSectionBasedDetection` had a fixed signature that didn't accept `**kwargs`. Production code was calling it with `is_buy_order=is_buy_order` as a keyword argument.  
**Fix:**
```python
# Before
def spy(arr, y0, y1, x0, x1, debug):
# After
def spy(arr, y0, y1, x0, x1, debug, **kwargs):
```

---

### 6. `tests/test_market_table_type_id.py`
**Problem:** `MockOpp` was missing required attributes (`profit_per_unit`, `best_buy_price`, `best_sell_price`) that `MarketTableWidget.populate()` accesses.  
**Fix:** Added the three missing attributes to `MockOpp.__init__`.

---

### 7. `tests/test_quick_order_freshness_validation.py`
**Problem:** `_launch_quick_order_update` internally calls `_revalidate_market_competitor`, which hit the real ESI path and returned `is_fresh=False`, suppressing the clipboard copy that `test_fresh_order_auto_copy` expected.  
**Fix:** Added `patch.object(self.view, "_revalidate_market_competitor", return_value=_fresh_market)` inside the `_launch()` helper, with a synthetic fresh market dict.

---

## Remaining Issue: Qt Process Isolation Crash (NOT introduced by these fixes)

### Affected files
- `tests/test_app_startup_imports.py`
- `tests/test_market_command_view_imports.py`
- `tests/test_quick_order_update_flow.py`

### Crash
```
Fatal Python error: Abrupt termination
Windows fatal exception: access violation

  File "my_orders_view.py", line 1326 in setup_ui
  File "my_orders_view.py", line 1228 in __init__
  File "test_quick_order_update_flow.py", line 157 in _make_view
  File "test_quick_order_update_flow.py", line 198 in setUp
```

### Root cause
On Windows, PySide6 does not survive multiple `QApplication` instances across different pytest test modules running in the same process. Each of these files creates `QApplication.instance() or QApplication(sys.argv)` at module level. When pytest imports them sequentially after other Qt test files have already run, the Qt internal state is corrupted, causing an access violation when a widget tries to render UI.

**These tests pass perfectly when run alone:**
```
pytest tests/test_quick_order_update_flow.py   # 43 passed
```

### Options to resolve (not yet implemented)
1. **`pytest-forked`** — run each Qt test file in a forked subprocess via `@pytest.mark.forked`.
2. **`conftest.py` subprocess isolation** — use `subprocess.run` to invoke pytest on each Qt file separately and collect results.
3. **`pytest-xdist` with `--forked`** flag.
4. **`QT_QPA_PLATFORM=offscreen` + shared singleton** — ensure only one `QApplication` is ever created across the entire session via a `conftest.py` session-scoped fixture.

The safest and lowest-effort fix is option 4: a `conftest.py` at the `tests/` root that creates the `QApplication` once per session and patches `sys.modules` to prevent re-creation.

---

## Test Results

| Scope | Result |
|---|---|
| All tests (excluding 3 Qt crash files) | **704 passed, 5 subtests passed** |
| Qt tests alone (`test_quick_order_update_flow.py`) | **43 passed** |
| Combined full suite | Crashes at ~57% due to Qt access violation |

---

## Files Changed (production code)

| File | Change |
|---|---|
| `core/contracts_engine.py` | `profitable` counter uses `>= 0` |
| `core/eve_market_visual_detector.py` | 4 fixes: debug key, marker gate, score gate, OCR error codes |
| `ui/market_command/simple_view.py` | Tooltip labels capitalized |

## Files Changed (tests)

| File | Change |
|---|---|
| `tests/test_contract_filters_boundary.py` | `capital_min_isk=0` |
| `tests/test_contract_items_preservation.py` | `capital_min_isk=0` |
| `tests/test_contract_ui_consistency.py` | `capital_min_isk=0` + full `ContractArbitrageResult` |
| `tests/test_eve_market_visual_detector.py` | spy `**kwargs` |
| `tests/test_market_table_type_id.py` | missing `MockOpp` attributes |
| `tests/test_quick_order_freshness_validation.py` | mock `_revalidate_market_competitor` |
