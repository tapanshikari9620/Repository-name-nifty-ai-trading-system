#!/usr/bin/env python3
"""
Daily Data Quality Report
Run this every market day to track data collection progress
"""

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

DATABASE_NAME = "nifty_market_data.db"
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

def get_connection():
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_today_ist_start():
    """Get start of today in IST (00:00)"""
    now = datetime.now(timezone.utc).astimezone(MARKET_TIMEZONE)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def count_snapshots_today():
    """Count snapshots collected today"""
    connection = get_connection()
    cursor = connection.cursor()
    
    today_start = get_today_ist_start()
    
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM market_snapshots
        WHERE datetime(timestamp_utc) >= datetime(?)
    """, (today_start.isoformat(),))
    
    result = cursor.fetchone()
    connection.close()
    
    return result['count'] if result else 0


def count_total_snapshots():
    """Count all snapshots ever collected"""
    connection = get_connection()
    cursor = connection.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM market_snapshots")
    result = cursor.fetchone()
    connection.close()
    
    return result['count'] if result else 0


def count_validation_errors_today():
    """Count validation errors from today"""
    connection = get_connection()
    cursor = connection.cursor()
    
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT ms.id) as error_count
        FROM market_snapshots ms
        LEFT JOIN option_snapshots os ON ms.id = os.market_snapshot_id
        WHERE datetime(ms.timestamp_utc) >= datetime(?)
        AND (
            -- Basic field validations
            os.strike IS NULL
            OR os.strike <= 0
            OR os.option_type NOT IN ('CE', 'PE')
            OR os.expiry IS NULL
            OR (os.bid_price IS NOT NULL AND os.bid_price < 0)
            OR (os.ask_price IS NOT NULL AND os.ask_price < 0)
            OR (os.bid_price IS NOT NULL AND os.ask_price IS NOT NULL 
                AND os.bid_price > os.ask_price AND os.ask_price > 0)
        )
    """, (get_today_ist_start().isoformat(),))
    
    result = cursor.fetchone()
    connection.close()
    
    return result['error_count'] if result else 0


def get_data_completeness():
    """Check completeness of critical fields (all-time)"""
    connection = get_connection()
    cursor = connection.cursor()
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(ltp) as ltp_count,
            COUNT(iv) as iv_count,
            COUNT(delta) as delta_count,
            COUNT(gamma) as gamma_count,
            COUNT(bid_price) as bid_count,
            COUNT(ask_price) as ask_count
        FROM option_snapshots
    """)
    
    row = cursor.fetchone()
    connection.close()
    
    if not row or row['total'] == 0:
        return {}
    
    total = row['total']
    return {
        'ltp': (row['ltp_count'] / total) * 100,
        'iv': (row['iv_count'] / total) * 100,
        'delta': (row['delta_count'] / total) * 100,
        'gamma': (row['gamma_count'] / total) * 100,
        'bid_price': (row['bid_count'] / total) * 100,
        'ask_price': (row['ask_count'] / total) * 100,
    }


def get_iv_stats():
    """Get IV statistics"""
    connection = get_connection()
    cursor = connection.cursor()
    
    cursor.execute("""
        SELECT 
            MIN(iv) as min_iv,
            MAX(iv) as max_iv,
            AVG(iv) as avg_iv,
            COUNT(*) as count
        FROM option_snapshots
        WHERE iv IS NOT NULL AND iv > 0
    """)
    
    row = cursor.fetchone()
    connection.close()
    
    if not row:
        return {}
    
    return {
        'min': round(row['min_iv'], 2) if row['min_iv'] else None,
        'max': round(row['max_iv'], 2) if row['max_iv'] else None,
        'avg': round(row['avg_iv'], 2) if row['avg_iv'] else None,
        'count': row['count']
    }


def get_bid_ask_spread_stats():
    """Get bid-ask spread statistics"""
    connection = get_connection()
    cursor = connection.cursor()
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN bid_price <= ask_price THEN 1 ELSE 0 END) as valid_spreads,
            SUM(CASE WHEN bid_price > ask_price THEN 1 ELSE 0 END) as inverted_spreads,
            AVG(CASE WHEN ask_price > 0 THEN (ask_price - bid_price) / ask_price * 100 
                ELSE NULL END) as avg_spread_percent
        FROM option_snapshots
        WHERE bid_price IS NOT NULL AND ask_price IS NOT NULL
    """)
    
    row = cursor.fetchone()
    connection.close()
    
    if not row or row['total'] == 0:
        return {}
    
    return {
        'total': row['total'],
        'valid_spreads': row['valid_spreads'],
        'inverted_spreads': row['inverted_spreads'],
        'avg_spread_percent': round(row['avg_spread_percent'], 2) if row['avg_spread_percent'] else None
    }


def get_collection_progress():
    """Calculate progress towards 12,000 snapshots"""
    total = count_total_snapshots()
    milestone_dates = {
        'phase1_1500': 5,
        'phase2_3000': 10,
        'phase3_4500': 15,
        'phase4_6000': 20,
        'phase5_7500': 25,
        'phase6_9000': 30,
        'phase7_12000': 40,
    }
    
    return {
        'total_snapshots': total,
        'progress_to_ml': f"{total} / 12,000 ({(total/12000)*100:.1f}%)",
        'milestones': {
            'phase1_1500': '✓' if total >= 1500 else '✗',
            'phase2_3000': '✓' if total >= 3000 else '✗',
            'phase3_4500': '✓' if total >= 4500 else '✗',
            'phase4_6000': '✓' if total >= 6000 else '✗',
            'phase5_7500': '✓' if total >= 7500 else '✗',
            'phase6_9000': '✓' if total >= 9000 else '✗',
            'phase7_12000': '✓' if total >= 12000 else '✗',
        }
    }


def generate_report():
    """Generate daily data quality report"""
    
    print("\n" + "="*70)
    print("DAILY DATA QUALITY REPORT")
    print("="*70)
    
    today = datetime.now(timezone.utc).astimezone(MARKET_TIMEZONE)
    print(f"\nReport Date: {today.strftime('%Y-%m-%d %H:%M:%S IST')}")
    
    # === TODAY'S COLLECTION ===
    print("\n" + "-"*70)
    print("TODAY'S COLLECTION")
    print("-"*70)
    
    snapshots_today = count_snapshots_today()
    print(f"Snapshots collected today: {snapshots_today}")
    
    # Expected: 390-400 per full market day (9:15-15:30 = 375 min)
    expected_today = 400
    collection_rate = (snapshots_today / expected_today * 100) if expected_today > 0 else 0
    print(f"Expected today: ~{expected_today}")
    print(f"Collection rate: {collection_rate:.1f}%")
    
    if collection_rate > 90:
        print("✓ EXCELLENT - On track for full day collection")
    elif collection_rate > 70:
        print("⚠ WARNING - Below expected collection rate")
    else:
        print("✗ CRITICAL - Significant gaps in collection")
    
    # === VALIDATION STATUS ===
    print("\n" + "-"*70)
    print("VALIDATION STATUS")
    print("-"*70)
    
    errors_today = count_validation_errors_today()
    print(f"Validation errors today: {errors_today}")
    
    if errors_today == 0:
        print("✓ EXCELLENT - All data passed validation!")
    elif errors_today < snapshots_today * 0.01:  # <1% errors
        print(f"✓ GOOD - Error rate <1%")
    elif errors_today < snapshots_today * 0.05:  # <5% errors
        print(f"⚠ WARNING - Error rate >1%, investigate")
    else:
        print(f"✗ CRITICAL - Error rate >5%, stop collection and debug")
    
    # === OVERALL PROGRESS ===
    print("\n" + "-"*70)
    print("OVERALL COLLECTION PROGRESS")
    print("-"*70)
    
    progress = get_collection_progress()
    print(f"Total snapshots collected: {progress['total_snapshots']}")
    print(f"Progress to ML-ready: {progress['progress_to_ml']}")
    
    print("\nPhase Completion Status:")
    for phase, status in progress['milestones'].items():
        snapshot_count = int(phase.split('_')[1])
        print(f"  {phase:20} {snapshot_count:5} snapshots  {status}")
    
    # === DATA COMPLETENESS ===
    print("\n" + "-"*70)
    print("DATA FIELD COMPLETENESS")
    print("-"*70)
    
    completeness = get_data_completeness()
    for field, percent in completeness.items():
        status = "✓" if percent > 99 else "⚠" if percent > 95 else "✗"
        print(f"  {field:12}: {percent:6.2f}%  {status}")
    
    # === IV STATISTICS ===
    print("\n" + "-"*70)
    print("IMPLIED VOLATILITY (IV) STATISTICS")
    print("-"*70)
    
    iv_stats = get_iv_stats()
    if iv_stats:
        print(f"  Min IV: {iv_stats['min']:.2f}%")
        print(f"  Max IV: {iv_stats['max']:.2f}%")
        print(f"  Avg IV: {iv_stats['avg']:.2f}%")
        print(f"  Data points: {iv_stats['count']}")
        
        if iv_stats['min'] >= 5 and iv_stats['max'] <= 150:
            print("  ✓ IV range normal (5%-150%)")
        else:
            print("  ⚠ IV range outside expected bounds")
    
    # === BID-ASK SPREADS ===
    print("\n" + "-"*70)
    print("BID-ASK SPREAD ANALYSIS")
    print("-"*70)
    
    spread_stats = get_bid_ask_spread_stats()
    if spread_stats:
        total_spreads = spread_stats['total']
        valid = spread_stats['valid_spreads']
        inverted = spread_stats['inverted_spreads']
        avg_spread = spread_stats['avg_spread_percent']
        
        print(f"  Total bid-ask pairs: {total_spreads}")
        print(f"  Valid spreads (bid < ask): {valid} ({(valid/total_spreads)*100:.1f}%)")
        print(f"  Inverted spreads (bid > ask): {inverted} ({(inverted/total_spreads)*100:.1f}%)")
        print(f"  Average spread: {avg_spread:.2f}% of ask price")
        
        if inverted == 0:
            print("  ✓ No inverted spreads (excellent)")
        elif (inverted/total_spreads) < 0.01:
            print("  ✓ <1% inverted spreads (acceptable)")
        else:
            print("  ✗ >1% inverted spreads (data quality issue)")
    
    # === SUMMARY & RECOMMENDATIONS ===
    print("\n" + "-"*70)
    print("SUMMARY & RECOMMENDATIONS")
    print("-"*70)
    
    status_checks = {
        'Collection Rate': collection_rate > 90,
        'No Validation Errors': errors_today == 0,
        'Field Completeness': all(v > 95 for v in completeness.values()),
        'IV Range Normal': iv_stats.get('min', 0) >= 5 and iv_stats.get('max', 0) <= 150,
        'No Inverted Spreads': spread_stats.get('inverted_spreads', 0) == 0,
    }
    
    passed_checks = sum(1 for v in status_checks.values() if v)
    total_checks = len(status_checks)
    
    print(f"\nQuality Score: {passed_checks}/{total_checks}")
    
    for check_name, passed in status_checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {check_name:25} {status}")
    
    if passed_checks == total_checks:
        print("\n🟢 OVERALL STATUS: DATA QUALITY EXCELLENT")
        print("   Continue collection → Phase 1 on track")
    elif passed_checks >= total_checks - 1:
        print("\n🟡 OVERALL STATUS: DATA QUALITY GOOD")
        print("   Continue collection with monitoring")
    else:
        print("\n🔴 OVERALL STATUS: DATA QUALITY ISSUES")
        print("   INVESTIGATE AND FIX before continuing")
    
    print("\n" + "="*70)
    print()


if __name__ == "__main__":
    generate_report()
