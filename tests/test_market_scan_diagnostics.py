import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from core.market_scan_diagnostics import MarketScanDiagnostics

def test_report_generation():
    diag = MarketScanDiagnostics(
        scan_id="test-123",
        mode="Simple",
        raw_orders_count=1000,
        ui_filtered_count=50,
        status="Success"
    )
    report = diag.to_report()
    print("=== TEST REPORT ===")
    print(report)
    print("====================")
    
    assert "test-123" in report
    assert "Simple" in report
    assert "1000" in report
    assert "50" in report
    print("[PASS] test_report_generation")

if __name__ == "__main__":
    try:
        test_report_generation()
        print("\nAll diagnostics tests passed!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
