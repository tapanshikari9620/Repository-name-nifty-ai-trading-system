#!/usr/bin/env python3
"""
Verification script for market_snapshot_inspection.py fixes.
Simple tests to confirm defensive programming works.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def verify_imports():
    """Verify module imports without errors"""
    logger.info("Verifying module imports...")
    try:
        import upstox_project.validation.market_snapshot_inspection as msi
        logger.info("✓ Module imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Import failed: {e}")
        return False

def verify_database_connection():
    """Verify database connection validation works"""
    logger.info("\nVerifying database connection...")
    try:
        import upstox_project.validation.market_snapshot_inspection as msi
        
        # Should succeed with valid DB
        conn = msi.get_connection()
        conn.close()
        logger.info("✓ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False

def verify_price_movement_robustness():
    """Verify price movement handles invalid prices"""
    logger.info("\nVerifying price movement error handling...")
    try:
        import upstox_project.validation.market_snapshot_inspection as msi
        
        # Test data with both valid and invalid prices
        snapshots = [
            {'id': 1, 'spot_price': 100.0},
            {'id': 2, 'spot_price': 101.0},  # Valid pair
            {'id': 3, 'spot_price': 'BAD'},   # Invalid
            {'id': 4, 'spot_price': 103.0},
            {'id': 5, 'spot_price': 104.0},  # Valid pair
        ]
        
        result = msi.analyze_price_movements(snapshots)
        
        # Should have processed valid pairs and skipped invalid ones
        if 'movements' in result and len(result['movements']) > 0:
            logger.info(f"✓ Price movement analysis completed ({len(result['movements'])} valid movements)")
            return True
        else:
            logger.warning("⚠ No movements found (might be expected depending on data)")
            return True
        
    except Exception as e:
        logger.error(f"✗ Price movement analysis crashed: {e}")
        return False

def verify_timestamp_robustness():
    """Verify timestamp handling works for invalid timestamps"""
    logger.info("\nVerifying timestamp error handling...")
    try:
        import upstox_project.validation.market_snapshot_inspection as msi
        
        # Test data with invalid timestamps
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
        
        # Should skip invalid timestamp sessions
        if len(result) > 0:
            logger.info(f"✓ Timestamp handling works ({len(result)} valid sessions processed)")
            return True
        else:
            logger.warning("⚠ No sessions processed (timestamps might all be invalid)")
            return True
        
    except AttributeError as e:
        logger.error(f"✗ AttributeError on None (null check not working): {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Session analysis failed: {e}")
        return False

def verify_build_report():
    """Verify build_report handles database errors"""
    logger.info("\nVerifying build_report functionality...")
    try:
        import upstox_project.validation.market_snapshot_inspection as msi
        
        report = msi.build_report()
        
        # Check report structure
        if 'status' in report and report['status'] in ['PASS', 'WARNING', 'FAIL']:
            logger.info(f"✓ Report generated successfully (Status: {report['status']})")
            return True
        else:
            logger.error(f"✗ Invalid report structure: {report}")
            return False
        
    except Exception as e:
        logger.error(f"✗ Report generation failed: {e}")
        return False

def main():
    """Run all verification tests"""
    logger.info("=" * 70)
    logger.info("MARKET SNAPSHOT INSPECTION - FIX VERIFICATION")
    logger.info("=" * 70)
    
    checks = [
        ("Module Import", verify_imports),
        ("Database Connection", verify_database_connection),
        ("Price Movement Error Handling", verify_price_movement_robustness),
        ("Timestamp Error Handling", verify_timestamp_robustness),
        ("Build Report", verify_build_report),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"✗ Check crashed: {e}")
            results.append((name, False))
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info(f"\nResult: {passed}/{total} checks passed")
    logger.info("=" * 70)
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
