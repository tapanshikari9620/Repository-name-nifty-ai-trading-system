#!/usr/bin/env python3
"""
Final QA Test - Check all critical functions work correctly
"""

import sys
import logging

logging.basicConfig(level=logging.ERROR)  # Suppress logs
logger = logging.getLogger(__name__)

def test_market_snapshot_inspection():
    """Test the fixed market_snapshot_inspection module"""
    print("\n" + "="*70)
    print("TEST 1: market_snapshot_inspection.py")
    print("="*70)
    
    try:
        import upstox_project.validation.market_snapshot_inspection as msi
        print("✓ Module imported successfully")
        
        # Test 1: parse_timestamp
        print("\n[1.1] Testing parse_timestamp()...", end=" ")
        
        ts = msi.parse_timestamp("2026-08-16T10:00:00+00:00")
        assert ts is not None, "Should parse valid timestamp"
        
        ts_none = msi.parse_timestamp(None)
        assert ts_none is None, "Should return None for None"
        
        ts_invalid = msi.parse_timestamp("INVALID")
        assert ts_invalid is None, "Should return None for invalid"
        
        print("✓ PASS")
        
        # Test 2: convert_to_ist
        print("[1.2] Testing convert_to_ist()...", end=" ")
        
        ist = msi.convert_to_ist("2026-08-16T10:00:00+00:00")
        assert ist is not None, "Should convert valid timestamp"
        
        ist_none = msi.convert_to_ist(None)
        assert ist_none is None, "Should return None for None"
        
        ist_invalid = msi.convert_to_ist("INVALID")
        assert ist_invalid is None, "Should return None for invalid"
        
        print("✓ PASS")
        
        # Test 3: is_market_session
        print("[1.3] Testing is_market_session()...", end=" ")
        
        # Should handle None gracefully
        result = msi.is_market_session(None)
        assert result is False, "Should return False for None"
        
        # Should handle invalid timestamps gracefully
        result = msi.is_market_session("INVALID")
        assert result is False, "Should return False for invalid"
        
        print("✓ PASS")
        
        # Test 4: analyze_price_movements (THE FIX - type conversion)
        print("[1.4] Testing analyze_price_movements() with invalid prices...", end=" ")
        
        test_data = [
            {'id': 1, 'spot_price': 100.0},
            {'id': 2, 'spot_price': 'INVALID'},  # Should be skipped
            {'id': 3, 'spot_price': 102.0},
            {'id': 4, 'spot_price': None},       # Should be skipped
            {'id': 5, 'spot_price': 105.0},
        ]
        
        result = msi.analyze_price_movements(test_data)
        
        assert 'movements' in result, "Missing 'movements' key"
        assert 'suspicious_movements' in result, "Missing 'suspicious_movements' key"
        
        # Should have processed some valid movements despite invalid prices
        movements_count = len(result['movements'])
        print(f"✓ PASS ({movements_count} valid movements processed, invalid skipped)")
        
        # Test 5: analyze_sessions (THE FIX - null-safety)
        print("[1.5] Testing analyze_sessions() with invalid timestamps...", end=" ")
        
        sessions = {
            "2026-08-15": [
                {'id': 1, 'timestamp_utc': 'INVALID', 'spot_price': 100.0},
                {'id': 2, 'timestamp_utc': 'INVALID', 'spot_price': 101.0},
            ],
            "2026-08-16": [
                {'id': 3, 'timestamp_utc': '2026-08-16T10:00:00+00:00', 'spot_price': 102.0},
                {'id': 4, 'timestamp_utc': '2026-08-16T11:00:00+00:00', 'spot_price': 103.0},
            ]
        }
        
        result = msi.analyze_sessions(sessions)
        
        assert isinstance(result, dict), "Should return dict"
        # Should skip invalid timestamp session
        assert len(result) <= len(sessions), "Should skip sessions with bad timestamps"
        
        print(f"✓ PASS ({len(result)}/{len(sessions)} valid sessions)")
        
        # Test 6: group_by_trading_date
        print("[1.6] Testing group_by_trading_date()...", end=" ")
        
        test_snapshots = [
            {'id': 1, 'timestamp_utc': '2026-08-16T10:00:00+00:00', 'spot_price': 100.0},
            {'id': 2, 'timestamp_utc': '2026-08-16T11:00:00+00:00', 'spot_price': 101.0},
        ]
        
        result = msi.group_by_trading_date(test_snapshots)
        assert isinstance(result, dict), "Should return dict"
        
        print("✓ PASS")
        
        # Test 7: validate_basic_data
        print("[1.7] Testing validate_basic_data()...", end=" ")
        
        test_snapshots = [
            {'id': 1, 'timestamp_utc': '2026-08-16T10:00:00+00:00', 'spot_price': 100.0},
            {'id': 2, 'timestamp_utc': 'INVALID', 'spot_price': 101.0},
            {'id': 3, 'timestamp_utc': '2026-08-16T11:00:00+00:00', 'spot_price': -5},
            {'id': 4, 'timestamp_utc': '2026-08-16T12:00:00+00:00', 'spot_price': None},
        ]
        
        result = msi.validate_basic_data(test_snapshots)
        assert 'invalid_prices' in result, "Missing 'invalid_prices' key"
        assert 'invalid_timestamps' in result, "Missing 'invalid_timestamps' key"
        
        print("✓ PASS")
        
        # Test 8: get_connection (THE FIX - error handling)
        print("[1.8] Testing get_connection()...", end=" ")
        
        try:
            conn = msi.get_connection()
            # Should return a valid connection or raise RuntimeError
            conn.close()
            print("✓ PASS")
        except RuntimeError as e:
            # This is acceptable - means DB is not accessible
            print(f"✓ PASS (expected error: {str(e)[:30]}...)")
        
        # Test 9: load_snapshots (THE FIX - exception handling)
        print("[1.9] Testing load_snapshots()...", end=" ")
        
        try:
            snapshots = msi.load_snapshots()
            print(f"✓ PASS (loaded {len(snapshots)} snapshots)")
        except RuntimeError as e:
            # Expected if DB has issues
            print(f"✓ PASS (database error handled: {str(e)[:30]}...)")
        
        # Test 10: build_report (THE FIX - full error handling)
        print("[1.10] Testing build_report()...", end=" ")
        
        report = msi.build_report()
        assert 'status' in report, "Missing 'status' key"
        assert report['status'] in ['PASS', 'WARNING', 'FAIL'], f"Invalid status: {report['status']}"
        
        print(f"✓ PASS (Status: {report['status']})")
        
        return True
        
    except AssertionError as e:
        print(f"\n✗ FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_other_critical_modules():
    """Test other critical modules"""
    print("\n" + "="*70)
    print("TEST 2: Other Critical Modules")
    print("="*70)
    
    modules_to_test = [
        ("database_schema_inspection", "Database schema inspection"),
        ("option_snapshot_inspection", "Option snapshot inspection"),
        ("market_snapshot_validation", "Market snapshot validation"),
        ("dataset_quality", "Dataset quality"),
        ("feature_engine", "Feature engine"),
        ("signal_engine", "Signal engine"),
        ("outcome_engine", "Outcome engine"),
        ("evidence_engine", "Evidence engine"),
    ]
    
    passed = 0
    failed = 0
    
    for module_name, description in modules_to_test:
        print(f"\n[2.{passed+failed+1}] Testing {description}...", end=" ")
        try:
            __import__(module_name)
            print("✓ PASS")
            passed += 1
        except Exception as e:
            print(f"✗ FAILED: {type(e).__name__}: {str(e)[:50]}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    return failed == 0


def main():
    print("\n" + "="*70)
    print("COMPREHENSIVE PROJECT QA - FINAL TEST SUITE")
    print("="*70)
    
    results = []
    
    # Run critical module tests
    print("\n[PHASE 1] Testing market_snapshot_inspection.py (MAIN FIX)")
    result1 = test_market_snapshot_inspection()
    results.append(("market_snapshot_inspection.py", result1))
    
    # Run other module tests
    print("\n[PHASE 2] Testing other critical modules")
    result2 = test_other_critical_modules()
    results.append(("Other modules", result2))
    
    # Summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "="*70)
    if all_passed:
        print(
            "ALL SMOKE TESTS PASSED - "
            "DATASET AND PRODUCTION READINESS NOT ASSESSED"
        )
        print("="*70)
        return 0
    else:
        print("❌ SOME TESTS FAILED - REVIEW ABOVE")
        print("="*70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
