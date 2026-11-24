
from ..database.paths import MARKET_DATABASE_PATH

import sqlite3
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

# ============================================================
# VARIABLE CHAIN ELIGIBILITY AUDIT
# READ-ONLY: Does NOT modify the database
# ============================================================

DATABASE_NAME = str(MARKET_DATABASE_PATH)


def safe_number(value):
    """Safely convert numeric values, matching the builder's intent."""
    try:
        if value is None or str(value).strip() == "":
            return 0.0

        number = float(value)

        # Reject NaN and infinity.
        if number != number or number in (float("inf"), float("-inf")):
            return 0.0

        return number
    except (TypeError, ValueError):
        return 0.0


def parse_timestamp(value):
    """Use the builder's timestamp interpretation."""
    if not value:
        return None

    try:
        timestamp = datetime.fromisoformat(str(value))
        if timestamp.tzinfo is None:
            # Match the existing builder: naive timestamps are treated as UTC.
            from datetime import timezone
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp
    except (TypeError, ValueError):
        return None


def table_exists(connection, table_name):
    result = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return result is not None


def get_columns(connection, table_name):
    return {
        row[1]
        for row in connection.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()
    }


def main():
    db_path = Path(DATABASE_NAME).resolve()

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return

    # Open SQLite in read-only mode.
    connection = sqlite3.connect(
        f"{db_path.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    try:
        required_tables = ("market_snapshots", "option_snapshots")

        for table in required_tables:
            if not table_exists(connection, table):
                print(f"ERROR: Required table missing: {table}")
                return

        market_columns = get_columns(connection, "market_snapshots")
        option_columns = get_columns(connection, "option_snapshots")

        required_market_columns = {
            "id", "timestamp_utc", "spot_price"
        }
        required_option_columns = {
            "market_snapshot_id", "expiry", "strike", "option_type"
        }

        if not required_market_columns.issubset(market_columns):
            print("ERROR: Unexpected market_snapshots schema.")
            print("Available columns:", sorted(market_columns))
            return

        if not required_option_columns.issubset(option_columns):
            print("ERROR: Unexpected option_snapshots schema.")
            print("Available columns:", sorted(option_columns))
            return

        health_available = table_exists(connection, "collection_health")
        health_columns = (
            get_columns(connection, "collection_health")
            if health_available else set()
        )

        health_schema_ok = (
            health_available
            and {
                "market_snapshot_id",
                "status",
                "validation_status",
            }.issubset(health_columns)
        )

        print("=" * 72)
        print("VARIABLE CHAIN ELIGIBILITY AUDIT")
        print("READ-ONLY — DATABASE WILL NOT BE MODIFIED")
        print("=" * 72)

        feature_table_exists = table_exists(connection, "market_features")

        if feature_table_exists:
            feature_columns = get_columns(connection, "market_features")
            if "market_snapshot_id" not in feature_columns:
                print(
                    "ERROR: market_features has no market_snapshot_id column."
                )
                return

            feature_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT market_snapshot_id FROM market_features"
                ).fetchall()
            }
        else:
            feature_ids = set()
            print("WARNING: market_features table not found.")

        markets = connection.execute(
            """
            SELECT id, timestamp_utc, spot_price
            FROM market_snapshots
            ORDER BY timestamp_utc, id
            """
        ).fetchall()

        options_by_snapshot = {}

        option_rows = connection.execute(
            """
            SELECT market_snapshot_id, expiry, strike, option_type
            FROM option_snapshots
            ORDER BY market_snapshot_id
            """
        ).fetchall()

        for row in option_rows:
            snapshot_id = row["market_snapshot_id"]
            options_by_snapshot.setdefault(snapshot_id, []).append(row)

        health_by_snapshot = {}

        if health_schema_ok:
            health_rows = connection.execute(
                """
                SELECT market_snapshot_id, status, validation_status
                FROM collection_health
                """
            ).fetchall()

            for row in health_rows:
                health_by_snapshot.setdefault(
                    row["market_snapshot_id"], []
                ).append(row)

        # Audit missing feature snapshots that contain at least one option.
        candidates = []

        for market in markets:
            snapshot_id = market["id"]

            if snapshot_id in feature_ids:
                continue

            rows = options_by_snapshot.get(snapshot_id, [])

            if not rows:
                continue

            timestamp = parse_timestamp(market["timestamp_utc"])
            spot = safe_number(market["spot_price"])

            ce_rows = [
                row for row in rows
                if str(row["option_type"]).strip().upper() == "CE"
            ]
            pe_rows = [
                row for row in rows
                if str(row["option_type"]).strip().upper() == "PE"
            ]

            invalid_types = len(rows) - len(ce_rows) - len(pe_rows)

            expiries = {
                str(row["expiry"]).strip()
                for row in rows
                if row["expiry"] is not None
                and str(row["expiry"]).strip()
            }

            all_expiries_present = all(
                row["expiry"] is not None
                and str(row["expiry"]).strip()
                for row in rows
            )

            contract_keys = []
            for row in rows:
                expiry = (
                    str(row["expiry"]).strip()
                    if row["expiry"] is not None else ""
                )
                strike = safe_number(row["strike"])
                option_type = str(row["option_type"]).strip().upper()

                contract_keys.append((expiry, strike, option_type))

            duplicate_contracts = (
                len(contract_keys) != len(set(contract_keys))
            )

            ce_strikes = {
                safe_number(row["strike"]) for row in ce_rows
            }
            pe_strikes = {
                safe_number(row["strike"]) for row in pe_rows
            }

            paired_strikes = (
                bool(ce_strikes)
                and ce_strikes == pe_strikes
            )

            one_expiry = len(expiries) == 1
            valid_timestamp = timestamp is not None
            valid_spot = spot > 0

            # Collection-health behavior:
            # The existing builder accepts snapshots with no health record
            # as legacy data. If a health record exists, it must be SUCCESS;
            # a non-empty validation_status must be PASS.
            health_records = health_by_snapshot.get(snapshot_id, [])
            if not health_schema_ok:
                health_ok = None
            elif not health_records:
                health_ok = True
            else:
                health_ok = all(
                    str(record["status"]).upper() == "SUCCESS"
                    and (
                        not record["validation_status"]
                        or str(record["validation_status"]).upper() == "PASS"
                    )
                    for record in health_records
                )

            # Core structural eligibility, independent of the 210-row rule.
            structural_ok = (
                one_expiry
                and all_expiries_present
                and not duplicate_contracts
                and paired_strikes
                and invalid_types == 0
                and valid_timestamp
                and valid_spot
                and len(ce_rows) > 0
                and len(pe_rows) > 0
            )

            eligible_with_health = (
                structural_ok and health_ok is True
                if health_schema_ok
                else None
            )

            candidates.append({
                "id": snapshot_id,
                "count": len(rows),
                "ce": len(ce_rows),
                "pe": len(pe_rows),
                "one_expiry": one_expiry,
                "all_expiries_present": all_expiries_present,
                "duplicates": duplicate_contracts,
                "paired": paired_strikes,
                "invalid_types": invalid_types,
                "timestamp": valid_timestamp,
                "spot": valid_spot,
                "health_ok": health_ok,
                "structural_ok": structural_ok,
                "eligible_with_health": eligible_with_health,
            })

        total = len(candidates)

        print(f"\nMissing feature snapshots WITH options: {total}")
        print(f"Existing feature snapshot IDs: {len(feature_ids)}")
        print(f"Collection-health schema available: {health_schema_ok}")

        def report(label, predicate):
            passed = sum(1 for item in candidates if predicate(item))
            print(f"{label:<48}: {passed:>7} / {total}")

        print("\n" + "-" * 72)
        print("INDIVIDUAL CHECKS")
        print("-" * 72)

        report("Exactly one non-empty expiry",
               lambda x: x["one_expiry"])
        report("All rows have expiry",
               lambda x: x["all_expiries_present"])
        report("No duplicate contract keys",
               lambda x: not x["duplicates"])
        report("CE/PE strike sets match",
               lambda x: x["paired"])
        report("No invalid option types",
               lambda x: x["invalid_types"] == 0)
        report("Valid timestamp",
               lambda x: x["timestamp"])
        report("Positive spot price",
               lambda x: x["spot"])

        if health_schema_ok:
            report("Collection health accepted",
                   lambda x: x["health_ok"] is True)
            report("Collection health rejected",
                   lambda x: x["health_ok"] is False)
        else:
            print(
                "Collection health check: UNKNOWN "
                "(table/required columns unavailable)"
            )

        print("\n" + "-" * 72)
        print("COMBINED ELIGIBILITY")
        print("-" * 72)

        report(
            "Pass all structural checks (not fixed 210)",
            lambda x: x["structural_ok"],
        )

        if health_schema_ok:
            report(
                "Pass structure + collection health",
                lambda x: x["eligible_with_health"] is True,
            )

        else:
            print(
                "Structure + health eligibility: UNKNOWN; "
                "do not treat structural passes as fully eligible."
            )

        print("\n" + "-" * 72)
        print("OPTION COUNT DISTRIBUTION")
        print("-" * 72)

        counts = Counter(item["count"] for item in candidates)
        for count, frequency in sorted(counts.items()):
            print(f"{count:>5} option records: {frequency:>7} snapshots")

        structural_counts = Counter(
            item["count"]
            for item in candidates
            if item["structural_ok"]
        )

        print("\nOption counts among structurally eligible candidates:")
        if structural_counts:
            for count, frequency in sorted(structural_counts.items()):
                print(f"{count:>5} option records: {frequency:>7} snapshots")
        else:
            print("None")

        print("\n" + "-" * 72)
        print("REJECTION REASONS")
        print("-" * 72)

        checks = [
            ("Expiry missing or not exactly one", lambda x:
             not x["one_expiry"] or not x["all_expiries_present"]),
            ("Duplicate contracts", lambda x: x["duplicates"]),
            ("CE/PE strikes do not match", lambda x: not x["paired"]),
            ("Invalid option types", lambda x: x["invalid_types"] > 0),
            ("Invalid timestamp", lambda x: not x["timestamp"]),
            ("Invalid/non-positive spot", lambda x: not x["spot"]),
            ("No CE or no PE rows", lambda x:
             x["ce"] == 0 or x["pe"] == 0),
        ]

        for label, predicate in checks:
            print(
                f"{label:<48}: "
                f"{sum(1 for x in candidates if predicate(x)):>7}"
            )

        if health_schema_ok:
            print(
                f"{'Collection-health failure':<48}: "
                f"{sum(1 for x in candidates if x['health_ok'] is False):>7}"
            )

        print("\n" + "=" * 72)
        print("AUDIT COMPLETE — DATABASE NOT MODIFIED")
        print("Do not rebuild features based on this report alone.")
        print("=" * 72)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
