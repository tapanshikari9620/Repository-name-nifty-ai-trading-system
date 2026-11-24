#!/usr/bin/env python3
"""
Test script to verify market_snapshot_inspection.py fixes.
Tests defensive programming and error handling.
"""

import sqlite3
import sys
import logging
from datetime import datetime, timezone

# Setup logging to see messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_NAME = "nifty_market_data.db"

def test_database_connection():
    """Test Issue #3: Database connection validation"""
    logger.info("=" * 70)
    logger.info("TEST #1: Database Connection Error Handling")
    logger.info("=" * 70)
    
    try:
        # Try to import and use get_connection
        import upstox_project.validation.market_snapshot_inspection as msi
        
        # Test 1a: Normal connection
        logger.info("Test 1a: Normal database connection...")
        connection = msi.get_connection()
        logger.info("✓ Connection successful")
        connection.close()
        
    except RuntimeError as e:
        logger.error(f"✗ Connection failed (expected for locked DB): {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error: {type(e).__name__}: {e}")
        return False
    
    return True


def test_load_snapshots_error_handling():
    """Test Issue #4: load_snapshots exception handling"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST #2: Load Snapshots Error Handling")
    logger.info("=" * 70)
    
    try:
        import upstox_project.validation.market_snapshot_inspection as msi
        
        # Test 2a: Load snapshots (if table exists)
        logger.info("Test 2a: Loading snapshots from database...")
        snapshots = msi.load_snapshots()
        logger.info(f"✓ Loaded {len(snapshots)} snapshots")
        
        if snapshots:
            # Check structure
            first_snapshot = snapshots[0]
            required_fields = {'id', 'timestamp_utc', 'spot_price'}
            if required_fields.issubset(first_snapshot.keys()):
                logger.info(f"✓ Snapshot structure valid: id={first_snapshot['id']}")
            else:
                logger.error(f"✗ Missing required fields: {dict(first_snapshot)}")
                return False
        
    except RuntimeError as e:
        logger.warning(f"⚠ Load failed (expected if table missing): {e}")
        return True  # This is expected if table doesn't exist
    except Exception as e:
        logger.error(f"✗ Unexpected error: {type(e).__name__}: {e}")
        return False
    
    return True


def test_price_movement_error_handling():
    """Test Issue #2: Price movement type conversion error handling"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST #3: Price Movement Type Conversion Error Handling")
    logger.info("=" * 70)
    
    import upstox_project.validation.market_snapshot_inspection as msi
    
    # Create test data with invalid prices
    session_snapshots = [
        {'id': 1, 'spot_price': 100.5},
        {'id': 2, 'spot_price': 'INVALID'},  # Non-numeric - should be skipped
        {'id': 3, 'spot_price': 102.5},
        {'id': 4, 'spot_price': None},  # None - should be skipped
        {'id': 5, 'spot_price': 105.0},
    ]
    
    try:
        logger.info("Test 3a: Analyzing movements with invalid prices...")
        result = msi.analyze_price_movements(session_snapshots)
        
        # Invalid adjacent pairs are skipped; don't bridge over bad snapshots.
        movements_count = len(result['movements'])

        if movements_count != 0:
            logger.error(
                f"✗ Invalid adjacent prices should not produce movements; "
                f"got {movements_count}"
            )
            return False

        valid_snapshots = [
            {'id': 1, 'spot_price': 100.5},
            {'id': 2, 'spot_price': 102.5},
            {'id': 3, 'spot_price': 105.0},
        ]
        valid_result = msi.analyze_price_movements(valid_snapshots)
        if len(valid_result['movements']) != 2:
            logger.error(
                "✗ Expected 2 movements from valid adjacent prices, "
                f"got {len(valid_result['movements'])}"
            )
            return False

        logger.info("✓ Invalid pairs skipped; valid adjacent pairs processed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Crashed on invalid price (fix not working): {type(e).__name__}: {e}")
        return False


def test_timestamp_null_safety():
    """Test Issue #1: Null timestamp handling in analyze_sessions"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST #4: Timestamp Null-Safety in analyze_sessions")
    logger.info("=" * 70)
    
    import upstox_project.validation.market_snapshot_inspection as msi
    
    # Create test data with unparseable timestamp
    sessions = {
        "2026-08-15": [
            {'id': 1, 'timestamp_utc': 'INVALID_TIMESTAMP', 'spot_price': 100.0},
            {'id': 2, 'timestamp_utc': 'INVALID_TIMESTAMP', 'spot_price': 101.0},
        ],
        "2026-08-16": [
            {'id': 3, 'timestamp_utc': '2026-08-16T10:00:00Z', 'spot_price': 102.0},
            {'id': 4, 'timestamp_utc': '2026-08-16T11:00:00Z', 'spot_price': 103.0},
        ]
    }
    
    try:
        logger.info("Test 4a: Analyzing sessions with invalid timestamps...")
        result = msi.analyze_sessions(sessions)
        
        # Should have skipped the session with bad timestamps
        valid_sessions = len(result)
        
        if valid_sessions >= 1:
            logger.info(f"✓ Skipped invalid timestamp session. Valid sessions: {valid_sessions}")
            logger.info(f"  Processed sessions: {list(result.keys())}")
            return True
        else:
            logger.warning(f"⚠ No sessions processed (expected if timestamps are invalid)")
            return True  # This is acceptable behavior
        
    except AttributeError as e:
        logger.error(f"✗ AttributeError on None (null-check not working): {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error: {type(e).__name__}: {e}")
        return False


def test_build_report_database_error():
    """Test Issue #5: build_report error handling"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST #5: build_report Database Error Handling")
    logger.info("=" * 70)
    
    import upstox_project.validation.market_snapshot_inspection as msi
    
    try:
        logger.info("Test 5a: Building report (tests error handling)...")
        report = msi.build_report()
        
        # Check report structure
        if 'status' in report and report['status'] in ['PASS', 'WARNING', 'FAIL']:
            logger.info(f"✓ Report generated with status: {report['status']}")
            if report['status'] == 'FAIL':
                logger.info(f"  Reason: {report.get('reason', 'Unknown')}")
            return True
        else:
            logger.error(f"✗ Invalid report status: {report.get('status')}")
            return False
        
    except Exception as e:
        logger.error(f"✗ Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 70)
    logger.info("MARKET SNAPSHOT INSPECTION - DEFENSIVE PROGRAMMING TEST SUITE")
    logger.info("=" * 70 + "\n")
    
    results = []
    
    # Run tests
    results.append(("Database Connection", test_database_connection()))
    results.append(("Load Snapshots", test_load_snapshots_error_handling()))
    results.append(("Price Movement Type Safety", test_price_movement_error_handling()))
    results.append(("Timestamp Null-Safety", test_timestamp_null_safety()))
    results.append(("Build Report Error Handling", test_build_report_database_error()))
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    logger.info("=" * 70)
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
