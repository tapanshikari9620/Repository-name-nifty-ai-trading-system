import sqlite3
from datetime import datetime, timezone

DATABASE_NAME = "nifty_market_data.db"
EXPECTED_INTERVAL_SECONDS = 90.0
REQUIRED_TABLES = {
    "market_snapshots",
    "option_snapshots",
    "market_features",
    "option_features",
    "historical_outcomes",
}


def get_connection():
    conn = sqlite3.connect(
        f"file:{DATABASE_NAME}?mode=ro",
        uri=True,
        timeout=5
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def parse_timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def age_seconds(timestamp):
    dt = parse_timestamp(timestamp)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def table_exists(conn, table_name):
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,)
    ).fetchone()
    return row is not None


def print_check(name, status, detail=""):
    print(f"{name:<34} : {status}")
    if detail:
        print(f"{'':<34}   {detail}")


def main():
    print()
    print("=" * 70)
    print("NIFTY AI/ML APPLICATION HEALTH CHECK")
    print("=" * 70)
    print()
    print("Database mode : READ-ONLY")
    print("No database changes will be made.")
    print()

    failures = []
    warnings = []

    # ------------------------------------------------------------
    # DATABASE
    # ------------------------------------------------------------
    print("DATABASE HEALTH")
    print("-" * 70)

    try:
        conn = get_connection()
        print_check("SQLite database accessible", "PASS")

        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity == "ok":
            print_check("SQLite integrity check", "PASS")
        else:
            print_check("SQLite integrity check", "FAIL", integrity)
            failures.append("SQLite integrity check failed")

        missing_tables = [
            table for table in REQUIRED_TABLES
            if not table_exists(conn, table)
        ]

        if not missing_tables:
            print_check("Required tables", "PASS")
        else:
            print_check(
                "Required tables",
                "FAIL",
                ", ".join(missing_tables)
            )
            failures.append("Required database tables are missing")

    except Exception as exc:
        print_check(
            "SQLite database accessible",
            "FAIL",
            f"{type(exc).__name__}: {exc}"
        )
        print()
        print("OVERALL APPLICATION HEALTH : FAIL")
        raise SystemExit(1)

    # ------------------------------------------------------------
    # DATABASE COUNTS
    # ------------------------------------------------------------
    print()
    print("DATABASE COUNTS")
    print("-" * 70)

    counts = {}
    for table in [
        "market_snapshots",
        "option_snapshots",
        "market_features",
        "option_features",
        "historical_outcomes",
    ]:
        try:
            counts[table] = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            print(f"{table:<30} : {counts[table]}")
        except Exception as exc:
            print_check(
                f"{table} count",
                "FAIL",
                str(exc)
            )
            failures.append(f"Could not read {table}")

    # ------------------------------------------------------------
    # RAW COLLECTOR HEALTH
    # ------------------------------------------------------------
    print()
    print("COLLECTOR / RAW DATA HEALTH")
    print("-" * 70)

    latest_market = conn.execute("""
        SELECT id, timestamp_utc, spot_price
        FROM market_snapshots
        ORDER BY timestamp_utc DESC, id DESC
        LIMIT 1
    """).fetchone()

    if latest_market is None:
        print_check("Latest market snapshot", "FAIL", "No market snapshots")
        failures.append("No market snapshots available")
    else:
        latest_age = age_seconds(latest_market["timestamp_utc"])

        if latest_age is None:
            print_check(
                "Latest market timestamp",
                "FAIL",
                "Invalid timestamp"
            )
            failures.append("Latest market timestamp is invalid")
        else:
            print(f"Latest market snapshot ID     : {latest_market['id']}")
            print(f"Latest market timestamp       : {latest_market['timestamp_utc']}")
            print(f"Latest spot price             : {latest_market['spot_price']}")
            print(f"Snapshot age                  : {latest_age:.1f} seconds")

            # This is a live-health check, so outside-market-hours data
            # may naturally be older. We warn instead of failing.
            if latest_age <= EXPECTED_INTERVAL_SECONDS:
                print_check("Latest collector snapshot", "PASS")
            else:
                print_check(
                    "Latest collector snapshot",
                    "WARNING",
                    f"Older than {EXPECTED_INTERVAL_SECONDS:.0f} seconds"
                )
                warnings.append("Latest collector snapshot is older than expected")

    latest_options = conn.execute("""
        SELECT
            market_snapshot_id,
            COUNT(*) AS option_count,
            COUNT(DISTINCT option_type) AS option_types,
            COUNT(DISTINCT expiry) AS expiries
        FROM option_snapshots
        GROUP BY market_snapshot_id
        ORDER BY market_snapshot_id DESC
        LIMIT 1
    """).fetchone()

    if latest_options is None:
        print_check("Latest option snapshot", "FAIL", "No option snapshots")
        failures.append("No option snapshots available")
    else:
        print(f"Latest option snapshot ID    : {latest_options['market_snapshot_id']}")
        print(f"Latest option record count    : {latest_options['option_count']}")
        print(f"Option types in snapshot      : {latest_options['option_types']}")
        print(f"Expiries in snapshot          : {latest_options['expiries']}")

        if latest_options["option_count"] > 0:
            print_check("Latest option snapshot", "PASS")
        else:
            print_check("Latest option snapshot", "FAIL")
            failures.append("Latest option snapshot contains no records")

    # ------------------------------------------------------------
    # LATEST FEATURE HEALTH
    # ------------------------------------------------------------
    print()
    print("FEATURE PIPELINE HEALTH")
    print("-" * 70)

    latest_feature = conn.execute("""
        SELECT market_snapshot_id, timestamp_utc
        FROM market_features
        ORDER BY timestamp_utc DESC, id DESC
        LIMIT 1
    """).fetchone()

    if latest_feature is None:
        print_check("Latest market feature", "FAIL")
        failures.append("No market features available")
    else:
        print(f"Latest feature snapshot ID   : {latest_feature['market_snapshot_id']}")
        print(f"Latest feature timestamp     : {latest_feature['timestamp_utc']}")
        print_check("Latest market feature", "PASS")

        if latest_market is not None:
            if latest_feature["market_snapshot_id"] <= latest_market["id"]:
                print_check("Feature source linkage", "PASS")
            else:
                print_check("Feature source linkage", "FAIL")
                failures.append("Latest feature points beyond latest market snapshot")

    latest_option_feature = conn.execute("""
        SELECT market_snapshot_id, timestamp_utc, COUNT(*) AS option_rows
        FROM option_features
        GROUP BY market_snapshot_id, timestamp_utc
        ORDER BY timestamp_utc DESC, market_snapshot_id DESC
        LIMIT 1
    """).fetchone()

    if latest_option_feature is None:
        print_check("Latest option features", "FAIL")
        failures.append("No option features available")
    else:
        print(f"Latest option feature ID     : {latest_option_feature['market_snapshot_id']}")
        print(f"Latest option feature rows   : {latest_option_feature['option_rows']}")
        if latest_option_feature["option_rows"] > 0:
            print_check("Latest option features", "PASS")
        else:
            print_check("Latest option features", "FAIL")
            failures.append("Latest option feature snapshot has no rows")

    # ------------------------------------------------------------
    # OUTCOME HEALTH
    # ------------------------------------------------------------
    print()
    print("OUTCOME PIPELINE HEALTH")
    print("-" * 70)

    latest_outcome = conn.execute("""
        SELECT market_snapshot_id, timestamp_utc
        FROM historical_outcomes
        ORDER BY timestamp_utc DESC, market_snapshot_id DESC
        LIMIT 1
    """).fetchone()

    if latest_outcome is None:
        print_check("Latest historical outcome", "FAIL")
        failures.append("No historical outcomes available")
    else:
        print(f"Latest outcome snapshot ID   : {latest_outcome['market_snapshot_id']}")
        print(f"Latest outcome timestamp     : {latest_outcome['timestamp_utc']}")
        print_check("Latest historical outcome", "PASS")

    # ------------------------------------------------------------
    # FEATURE / OUTCOME ALIGNMENT
    # ------------------------------------------------------------
    print()
    print("PIPELINE LINKAGE HEALTH")
    print("-" * 70)

    missing_outcomes = conn.execute("""
        SELECT COUNT(*)
        FROM market_features mf
        LEFT JOIN historical_outcomes ho
          ON ho.market_snapshot_id = mf.market_snapshot_id
        WHERE ho.market_snapshot_id IS NULL
    """).fetchone()[0]

    feature_outcome_mismatch = conn.execute("""
        SELECT COUNT(*)
        FROM market_features mf
        JOIN historical_outcomes ho
          ON ho.market_snapshot_id = mf.market_snapshot_id
        WHERE mf.timestamp_utc != ho.timestamp_utc
    """).fetchone()[0]

    print(f"Features without outcomes      : {missing_outcomes}")
    print(f"Feature/outcome timestamp diff : {feature_outcome_mismatch}")

    if missing_outcomes == 0 and feature_outcome_mismatch == 0:
        print_check("Feature to outcome linkage", "PASS")
    else:
        print_check("Feature to outcome linkage", "FAIL")
        failures.append("Feature/outcome linkage problems detected")

    # ------------------------------------------------------------
    # RAW DATA DUPLICATE HEALTH
    # ------------------------------------------------------------
    print()
    print("RAW DATA INTEGRITY HEALTH")
    print("-" * 70)

    duplicate_market_timestamps = conn.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT timestamp_utc
            FROM market_snapshots
            GROUP BY timestamp_utc
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    orphan_options = conn.execute("""
        SELECT COUNT(*)
        FROM option_snapshots os
        LEFT JOIN market_snapshots ms
          ON ms.id = os.market_snapshot_id
        WHERE ms.id IS NULL
    """).fetchone()[0]

    print(f"Duplicate market timestamps   : {duplicate_market_timestamps}")
    print(f"Orphan option records         : {orphan_options}")

    if duplicate_market_timestamps == 0 and orphan_options == 0:
        print_check("Raw database integrity", "PASS")
    else:
        print_check("Raw database integrity", "FAIL")
        failures.append("Raw database integrity problems detected")

    # ------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------
    print()
    print("OVERALL HEALTH SUMMARY")
    print("-" * 70)
    print(f"Failures  : {len(failures)}")
    print(f"Warnings  : {len(warnings)}")

    if failures:
        print()
        for item in failures:
            print(f"FAIL : {item}")
        print()
        print("OVERALL APPLICATION HEALTH : FAIL")
        raise SystemExit(1)

    if warnings:
        print()
        for item in warnings:
            print(f"WARNING : {item}")
        print()
        print("OVERALL APPLICATION HEALTH : HEALTHY WITH WARNINGS")
    else:
        print()
        print("OVERALL APPLICATION HEALTH : HEALTHY")

    print()
    print("=" * 70)
    print()
    print("Note: This is a database/pipeline health check.")
    print("It does not prove Upstox authentication is currently valid")
    print("because this script intentionally does not make API calls.")
    print()


if __name__ == "__main__":
    main()
