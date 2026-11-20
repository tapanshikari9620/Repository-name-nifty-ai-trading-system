
import sqlite3
from collections import Counter
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DB_NAME = "nifty_market_data.db"
IST = ZoneInfo("Asia/Kolkata")


def parse_timestamp(value):
    """Parse a UTC timestamp and convert it to IST."""
    if value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            # Support Unix timestamps in seconds or milliseconds.
            epoch = float(value)
            if abs(epoch) > 1e12:
                epoch /= 1000
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        else:
            raw = str(value).strip()
            if not raw:
                return None

            # Support ISO strings ending in Z.
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"

            dt = datetime.fromisoformat(raw)

            # The source column is timestamp_utc, so treat a
            # timezone-naive value as UTC.
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(IST)

    except (ValueError, TypeError, OverflowError, OSError):
        return None


def main():
    db = Path(DB_NAME)

    if not db.exists():
        print(f"ERROR: Database not found: {db.resolve()}")
        return 1

    conn = sqlite3.connect(
        f"file:{db.resolve()}?mode=ro",
        uri=True
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")

    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        required = {
            "market_snapshots",
            "option_snapshots",
            "market_features"
        }

        missing_tables = required - tables
        if missing_tables:
            print("ERROR: Missing tables:", sorted(missing_tables))
            return 1

        market_cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(market_snapshots)"
            )
        }

        option_cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(option_snapshots)"
            )
        }

        feature_cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(market_features)"
            )
        }

        if "timestamp_utc" not in market_cols:
            print(
                "ERROR: market_snapshots has no timestamp_utc column."
            )
            print("Available columns:", sorted(market_cols))
            return 1

        if "id" not in market_cols:
            print("ERROR: market_snapshots has no id column.")
            return 1

        if "market_snapshot_id" not in option_cols:
            print(
                "ERROR: option_snapshots has no market_snapshot_id."
            )
            return 1

        feature_link = next(
            (
                name for name in
                ("market_snapshot_id", "snapshot_id")
                if name in feature_cols
            ),
            None
        )

        if feature_link is None:
            print("ERROR: No recognized feature-to-snapshot link.")
            return 1

        # Load raw snapshot timestamps.
        raw_rows = conn.execute("""
            SELECT id, timestamp_utc
            FROM market_snapshots
            ORDER BY id
        """).fetchall()

        # Count option records per raw snapshot.
        option_counts = {
            row["sid"]: row["record_count"]
            for row in conn.execute("""
                SELECT market_snapshot_id AS sid, COUNT(*) AS record_count
                FROM option_snapshots
                GROUP BY market_snapshot_id
            """)
        }

        # A snapshot is considered featured if it has a market feature row.
        feature_ids = {
            row["sid"]
            for row in conn.execute(
                f"""
                SELECT DISTINCT {feature_link} AS sid
                FROM market_features
                WHERE {feature_link} IS NOT NULL
                """
            )
        }

        print("\n" + "=" * 76)
        print("MISSING FEATURE TIME AUDIT - READ ONLY")
        print("=" * 76)
        print("Regular-session window: 09:15–15:30 IST")
        print("Timestamp assumption: timestamp_utc is UTC")

        buckets = {
            "PRE_MARKET": Counter(),
            "REGULAR_SESSION": Counter(),
            "POST_MARKET": Counter(),
            "UNPARSEABLE_TIMESTAMP": Counter()
        }

        missing_with_options = 0
        missing_without_options = 0
        unparsed_examples = []

        for row in raw_rows:
            sid = row["id"]

            if sid in feature_ids:
                continue

            count = option_counts.get(sid, 0)

            if count == 0:
                missing_without_options += 1
                continue

            missing_with_options += 1
            local_dt = parse_timestamp(row["timestamp_utc"])

            if local_dt is None:
                bucket_name = "UNPARSEABLE_TIMESTAMP"
                if len(unparsed_examples) < 5:
                    unparsed_examples.append(
                        (sid, row["timestamp_utc"])
                    )
            else:
                local_time = local_dt.time().replace(tzinfo=None)

                if local_time < time(9, 15):
                    bucket_name = "PRE_MARKET"
                elif local_time <= time(15, 30):
                    bucket_name = "REGULAR_SESSION"
                else:
                    bucket_name = "POST_MARKET"

            buckets[bucket_name][count] += 1

        print("\nOVERALL")
        print("-" * 76)
        print(f"Raw market snapshots             : {len(raw_rows)}")
        print(f"Existing feature snapshot IDs    : {len(feature_ids)}")
        print(f"Missing snapshots WITH options   : {missing_with_options}")
        print(f"Missing snapshots WITHOUT options: {missing_without_options}")

        print("\nMISSING SNAPSHOTS BY TIME OF DAY")
        print("-" * 76)

        for name in (
            "PRE_MARKET",
            "REGULAR_SESSION",
            "POST_MARKET",
            "UNPARSEABLE_TIMESTAMP"
        ):
            counts = buckets[name]
            total = sum(counts.values())
            print(f"\n{name}: {total} snapshots")

            if counts:
                print("  Option-record count distribution:")
                for record_count, quantity in sorted(counts.items()):
                    print(
                        f"    {record_count:4} records: "
                        f"{quantity:5} snapshots"
                    )

        if unparsed_examples:
            print("\nUNPARSEABLE TIMESTAMP EXAMPLES")
            for sid, timestamp in unparsed_examples:
                print(f"  Snapshot ID {sid}: {timestamp!r}")

        print("\n" + "=" * 76)
        print("AUDIT COMPLETE — DATABASE NOT MODIFIED")
        print("=" * 76)

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
