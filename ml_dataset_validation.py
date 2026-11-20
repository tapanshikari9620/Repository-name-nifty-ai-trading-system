import sqlite3
import os
from pathlib import Path

from datetime import datetime, timezone

DATABASE_NAME = os.environ.get(
    "NIFTY_MARKET_DATABASE",
    str(Path(__file__).resolve().parent / "nifty_market_data.db"),
)

HORIZONS = {
    "5m": "outcome_5m_direction",
    "15m": "outcome_15m_direction",
    "30m": "outcome_30m_direction",
    "60m": "outcome_60m_direction",
}

FORBIDDEN_FEATURE_TERMS = (
    "outcome",
    "future",
    "target",
    "label",
    "direction",
)

ALLOWED_LABELS = {"BULLISH", "BEARISH", "FLAT"}


def get_connection():
    conn = sqlite3.connect(
        Path(DATABASE_NAME).resolve().as_uri() + "?mode=ro",
        uri=True
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def table_columns(conn, table_name):
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return [row["name"] for row in rows]


def parse_timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def select_candidate_features(market_columns):
    excluded = {
        "id",
        "market_snapshot_id",
        "timestamp_utc",
        "created_at_utc",
    }
    return [
        column for column in market_columns
        if column not in excluded
    ]


def main():
    print()
    print("=" * 70)
    print("TEMPORARY ML DATASET VALIDATION")
    print("=" * 70)
    print()
    print("Database mode : READ-ONLY")
    print("No database changes will be made.")
    print("This test does NOT train an ML model.")
    print()

    conn = get_connection()
    failures = []

    try:
        # ------------------------------------------------------------
        # TEST 1 - TABLE / COLUMN DISCOVERY
        # ------------------------------------------------------------
        print("TEST 1 - DATASET STRUCTURE")
        print("-" * 70)

        market_columns = table_columns(conn, "market_features")
        outcome_columns = table_columns(conn, "historical_outcomes")

        print(f"Market feature columns : {len(market_columns)}")
        print(f"Outcome columns        : {len(outcome_columns)}")

        if not market_columns:
            failures.append("market_features has no columns")

        if not outcome_columns:
            failures.append("historical_outcomes has no columns")

        print()
        print("Market feature columns:")
        for col in market_columns:
            print(f"  - {col}")

        print()
        print("Outcome columns:")
        for col in outcome_columns:
            print(f"  - {col}")

        # ------------------------------------------------------------
        # TEST 2 - FEATURE COLUMN SAFETY
        # ------------------------------------------------------------
        print()
        print("TEST 2 - FEATURE COLUMN SAFETY")
        print("-" * 70)

        candidate_features = select_candidate_features(
            market_columns
        )

        unsafe_features = []
        for col in candidate_features:
            lower = col.lower()
            if any(term in lower for term in FORBIDDEN_FEATURE_TERMS):
                unsafe_features.append(col)

        print(f"Candidate ML feature columns : {len(candidate_features)}")
        print(f"Potential future/label columns: {len(unsafe_features)}")

        if unsafe_features:
            for col in unsafe_features:
                print(f"  FAIL : {col}")
            failures.append(
                "Potential future/label columns found in market_features"
            )
        else:
            print("No outcome/future/target/label/direction columns found in market_features.")

        # ------------------------------------------------------------
        # TEST 3 - SOURCE ROW ALIGNMENT
        # ------------------------------------------------------------
        print()
        print("TEST 3 - FEATURE / OUTCOME ALIGNMENT")
        print("-" * 70)

        rows = conn.execute("""
            SELECT
                mf.market_snapshot_id,
                mf.timestamp_utc AS feature_timestamp,
                ho.timestamp_utc AS outcome_timestamp
            FROM market_features mf
            LEFT JOIN historical_outcomes ho
              ON ho.market_snapshot_id = mf.market_snapshot_id
            ORDER BY mf.timestamp_utc, mf.market_snapshot_id
        """).fetchall()

        missing_outcomes = 0
        timestamp_mismatches = 0

        for row in rows:
            if row["outcome_timestamp"] is None:
                missing_outcomes += 1
                continue

            feature_ts = parse_timestamp(row["feature_timestamp"])
            outcome_ts = parse_timestamp(row["outcome_timestamp"])

            if feature_ts is None or outcome_ts is None:
                timestamp_mismatches += 1
            elif feature_ts != outcome_ts:
                timestamp_mismatches += 1

        print(f"Feature snapshots checked : {len(rows)}")
        print(f"Missing outcome source rows: {missing_outcomes}")
        print(f"Timestamp mismatches       : {timestamp_mismatches}")

        if missing_outcomes:
            failures.append(
                f"{missing_outcomes} feature snapshots have no outcome source row"
            )

        if timestamp_mismatches:
            failures.append(
                f"{timestamp_mismatches} feature/outcome source timestamp mismatches"
            )

        # ------------------------------------------------------------
        # TEST 4 - DUPLICATE SOURCE SAMPLES
        # ------------------------------------------------------------
        print()
        print("TEST 4 - DUPLICATE SOURCE SAMPLES")
        print("-" * 70)

        duplicate_ids = conn.execute("""
            SELECT market_snapshot_id, COUNT(*) AS cnt
            FROM market_features
            GROUP BY market_snapshot_id
            HAVING COUNT(*) > 1
        """).fetchall()

        duplicate_timestamps = conn.execute("""
            SELECT timestamp_utc, COUNT(*) AS cnt
            FROM market_features
            GROUP BY timestamp_utc
            HAVING COUNT(*) > 1
        """).fetchall()

        print(f"Duplicate market_snapshot_id groups : {len(duplicate_ids)}")
        print(f"Duplicate feature timestamp groups   : {len(duplicate_timestamps)}")

        if duplicate_ids:
            failures.append("Duplicate market_snapshot_id samples found")

        # Duplicate timestamps are reported separately because timestamp
        # uniqueness is not necessarily guaranteed by the source schema.
        # They are suspicious for an ML dataset and therefore fail validation.
        if duplicate_timestamps:
            failures.append("Duplicate feature timestamps found")

        # ------------------------------------------------------------
        # TEST 5 - FEATURE NULL / NON-FINITE CHECK
        # ------------------------------------------------------------
        print()
        print("TEST 5 - FEATURE VALUE CHECK")
        print("-" * 70)

        numeric_features = [
            col for col in candidate_features
            if col not in unsafe_features
        ]

        null_counts = {}
        nonfinite_count = 0

        for col in numeric_features:
            # SQLite can store NULL. Non-finite values are checked in Python.
            count = conn.execute(
                f"SELECT COUNT(*) FROM market_features WHERE {col} IS NULL"
            ).fetchone()[0]

            if count:
                null_counts[col] = count

            values = conn.execute(
                f"SELECT {col} FROM market_features"
            ).fetchall()

            for value_row in values:
                value = value_row[0]
                if isinstance(value, float):
                    if value != value or value in (float("inf"), float("-inf")):
                        nonfinite_count += 1

        print(f"Feature columns checked : {len(numeric_features)}")
        print(f"Columns containing NULL : {len(null_counts)}")
        print(f"Non-finite numeric values: {nonfinite_count}")

        if null_counts:
            for col, count in null_counts.items():
                print(f"  NULL : {col} -> {count}")
            failures.append("NULL values found in candidate ML features")

        if nonfinite_count:
            failures.append("Non-finite numeric values found in features")

        # ------------------------------------------------------------
        # TEST 6 - VALID LABEL AVAILABILITY
        # ------------------------------------------------------------
        print()
        print("TEST 6 - LABEL AVAILABILITY")
        print("-" * 70)

        for horizon, label_col in HORIZONS.items():
            valid_col = f"outcome_{horizon}_valid"

            total = conn.execute(
                "SELECT COUNT(*) FROM historical_outcomes"
            ).fetchone()[0]

            valid = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM historical_outcomes
                WHERE {valid_col} = 1
                  AND {label_col} IN ('BULLISH', 'BEARISH', 'FLAT')
                """
            ).fetchone()[0]

            invalid_label_rows = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM historical_outcomes
                WHERE {valid_col} = 1
                  AND (
                      {label_col} IS NULL
                      OR {label_col} NOT IN ('BULLISH', 'BEARISH', 'FLAT')
                  )
                """
            ).fetchone()[0]

            print(
                f"{horizon:>3} : valid ML labels = {valid}, "
                f"invalid valid-label rows = {invalid_label_rows}"
            )

            if invalid_label_rows:
                failures.append(
                    f"{horizon}: valid outcome rows contain invalid labels"
                )

            if valid == 0:
                failures.append(
                    f"{horizon}: no valid ML labels available"
                )

        # ------------------------------------------------------------
        # TEST 7 - UNAVAILABLE LABELS EXCLUDED
        # ------------------------------------------------------------
        print()
        print("TEST 7 - UNAVAILABLE LABEL PROTECTION")
        print("-" * 70)

        for horizon, label_col in HORIZONS.items():
            valid_col = f"outcome_{horizon}_valid"

            bad = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM historical_outcomes
                WHERE {valid_col} = 0
                  AND {label_col} IS NOT NULL
                  AND {label_col} NOT IN ('UNAVAILABLE', '')
                """
            ).fetchone()[0]

            unavailable = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM historical_outcomes
                WHERE {valid_col} = 0
                """
            ).fetchone()[0]

            print(
                f"{horizon:>3} : unavailable rows = {unavailable}, "
                f"unexpected labels = {bad}"
            )

            if bad:
                failures.append(
                    f"{horizon}: unavailable rows contain unexpected labels"
                )

        # ------------------------------------------------------------
        # TEST 8 - TEMPORARY DATASET CONSTRUCTION
        # ------------------------------------------------------------
        print()
        print("TEST 8 - TEMPORARY ML DATASET CONSTRUCTION")
        print("-" * 70)

        for horizon, label_col in HORIZONS.items():
            valid_col = f"outcome_{horizon}_valid"

            # Deliberately select only market_features columns plus the
            # requested label. Outcome price/return/timestamp columns are
            # never selected as features.
            feature_select = ", ".join(
                f"mf.{col}" for col in candidate_features
            )

            query = f"""
                SELECT
                    mf.market_snapshot_id,
                    mf.timestamp_utc,
                    {feature_select},
                    ho.{label_col} AS target
                FROM market_features mf
                JOIN historical_outcomes ho
                  ON ho.market_snapshot_id = mf.market_snapshot_id
                WHERE ho.{valid_col} = 1
                  AND ho.{label_col} IN ('BULLISH', 'BEARISH', 'FLAT')
                ORDER BY mf.timestamp_utc, mf.market_snapshot_id
            """

            dataset_rows = conn.execute(query).fetchall()

            print(f"{horizon:>3} : temporary ML rows = {len(dataset_rows)}")

            if not dataset_rows:
                failures.append(
                    f"{horizon}: temporary ML dataset is empty"
                )
                continue

            # Verify the selected target is one of the allowed labels.
            bad_targets = sum(
                1 for row in dataset_rows
                if row["target"] not in ALLOWED_LABELS
            )

            if bad_targets:
                failures.append(
                    f"{horizon}: {bad_targets} invalid target values"
                )

        # ------------------------------------------------------------
        # TEST 9 - NO FUTURE OUTCOME COLUMNS IN DATASET
        # ------------------------------------------------------------
        print()
        print("TEST 9 - TARGET/FUTURE COLUMN EXCLUSION")
        print("-" * 70)

        dataset_column_names = (
            ["market_snapshot_id", "timestamp_utc"]
            + candidate_features
            + ["target"]
        )

        leaked_columns = []
        for col in dataset_column_names:
            lower = col.lower()
            if col == "target":
                continue
            if any(term in lower for term in FORBIDDEN_FEATURE_TERMS):
                leaked_columns.append(col)

        print(f"Temporary dataset columns checked : {len(dataset_column_names)}")
        print(f"Potential leaked columns           : {len(leaked_columns)}")

        if leaked_columns:
            for col in leaked_columns:
                print(f"  FAIL : {col}")
            failures.append(
                "Potential future/label columns present in temporary dataset"
            )
        else:
            print("No future/outcome/target/label/direction columns present in X.")

        # ------------------------------------------------------------
        # FINAL
        # ------------------------------------------------------------
        print()
        print("RESULT SUMMARY")
        print("-" * 70)
        print(f"Total validation failures : {len(failures)}")

        if failures:
            print()
            print("FAILURE DETAILS")
            print("-" * 70)
            for failure in failures:
                print(f"FAIL : {failure}")

            print()
            print("ML DATASET VALIDATION STATUS : FAIL")
            print("Do not proceed to ML training.")
            raise SystemExit(1)

        print()
        print("ML DATASET VALIDATION STATUS : PASS")
        print()
        print("Temporary datasets are structurally valid.")
        print("Future outcome fields are excluded from model features.")
        print("No ML model was trained.")
        print()
        print("=" * 70)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
