import sqlite3
import math
import os

from datetime import datetime, timezone, timedelta
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = os.environ.get(
    "NIFTY_MARKET_DATABASE",
    str(Path(__file__).resolve().parent / "nifty_market_data.db"),
)
PRODUCTION_DATABASE_PATH = (
    Path(__file__).resolve().parent / "nifty_market_data.db"
).resolve()

HORIZONS = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60
}

# Maximum allowed delay after the requested target time.
#
# Example:
#
# Source      : 10:00:00
# Target +5m  : 10:05:00
#
# Valid future snapshot:
# 10:05:00 -> 10:06:30
#
# Invalid:
# 10:06:31 or later
#
MAX_FUTURE_DELAY_SECONDS = 90.0

# This is a research label threshold only.
# It is NOT an option-buying threshold and NOT a profit probability.
DIRECTION_THRESHOLD_PERCENT = 0.05


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    database_path = Path(
        DATABASE_NAME
    ).expanduser().resolve()

    if not database_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {database_path}"
        )

    connection = sqlite3.connect(
        database_path
    )

    connection.row_factory = sqlite3.Row

    return connection


def assert_safe_write_target(connection):
    database_path = Path(DATABASE_NAME).expanduser().resolve()

    if database_path == PRODUCTION_DATABASE_PATH:
        raise RuntimeError(
            "Historical outcome writes are disabled for the production "
            f"database: {database_path}"
        )

    connected_paths = {
        Path(row[2]).expanduser().resolve()
        for row in connection.execute("PRAGMA database_list")
        if row[1] == "main" and row[2]
    }

    if connected_paths != {database_path}:
        raise RuntimeError(
            "Database connection does not match the configured isolated "
            f"database path: configured={database_path}, "
            f"connected={sorted(map(str, connected_paths))}"
        )


def get_write_connection():
    connection = get_connection()
    try:
        assert_safe_write_target(connection)
    except BaseException:
        connection.close()
        raise
    return connection


# ============================================================
# SAFE NUMBER
# ============================================================

def safe_number(value):

    if value is None:
        return 0.0

    try:

        number = float(value)

        if not math.isfinite(number):
            return 0.0

        return number

    except (
        TypeError,
        ValueError
    ):

        return 0.0


# ============================================================
# TIMESTAMP PARSER
# ============================================================

def parse_timestamp(timestamp):

    if not timestamp:
        return None

    try:

        parsed = datetime.fromisoformat(
            timestamp
        )

        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    except (
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# INITIALIZE TABLE
# ============================================================

def initialize_outcome_table():

    connection = get_write_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS historical_outcomes (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            market_snapshot_id INTEGER NOT NULL UNIQUE,

            timestamp_utc TEXT NOT NULL,

            spot_price REAL NOT NULL,

            expiry TEXT,

            outcome_5m_price REAL,
            outcome_5m_timestamp TEXT,
            outcome_5m_change_points REAL,
            outcome_5m_return_pct REAL,
            outcome_5m_direction TEXT,
            outcome_5m_delay_seconds REAL,
            outcome_5m_valid INTEGER NOT NULL DEFAULT 0,

            outcome_15m_price REAL,
            outcome_15m_timestamp TEXT,
            outcome_15m_change_points REAL,
            outcome_15m_return_pct REAL,
            outcome_15m_direction TEXT,
            outcome_15m_delay_seconds REAL,
            outcome_15m_valid INTEGER NOT NULL DEFAULT 0,

            outcome_30m_price REAL,
            outcome_30m_timestamp TEXT,
            outcome_30m_change_points REAL,
            outcome_30m_return_pct REAL,
            outcome_30m_direction TEXT,
            outcome_30m_delay_seconds REAL,
            outcome_30m_valid INTEGER NOT NULL DEFAULT 0,

            outcome_60m_price REAL,
            outcome_60m_timestamp TEXT,
            outcome_60m_change_points REAL,
            outcome_60m_return_pct REAL,
            outcome_60m_direction TEXT,
            outcome_60m_delay_seconds REAL,
            outcome_60m_valid INTEGER NOT NULL DEFAULT 0,

            created_at_utc TEXT NOT NULL

        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_historical_outcomes_timestamp

        ON historical_outcomes(timestamp_utc)
        """
    )

    connection.commit()

    connection.close()


# ============================================================
# LOAD MARKET SNAPSHOTS
# ============================================================

def load_market_snapshots():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            timestamp_utc,
            spot_price

        FROM market_snapshots

        ORDER BY
            timestamp_utc ASC,
            id ASC
        """
    )

    rows = cursor.fetchall()

    connection.close()

    snapshots = []

    for row in rows:

        timestamp = parse_timestamp(
            row["timestamp_utc"]
        )

        spot_price = safe_number(
            row["spot_price"]
        )

        if timestamp is None:
            continue

        if spot_price <= 0:
            continue

        snapshots.append(
            {
                "id": row["id"],

                "timestamp_utc":
                    row["timestamp_utc"],

                "timestamp":
                    timestamp,

                "spot_price":
                    spot_price
            }
        )

    return snapshots


# ============================================================
# LOAD VALIDATED FEATURE SNAPSHOTS
# ============================================================

def load_feature_snapshot_ids():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            market_snapshot_id

        FROM market_features
        """
    )

    rows = cursor.fetchall()

    connection.close()

    return {
        row["market_snapshot_id"]
        for row in rows
    }


# ============================================================
# GET EXPIRY
# ============================================================

def get_snapshot_expiry(
    market_snapshot_id
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            expiry

        FROM option_snapshots

        WHERE market_snapshot_id = ?

        ORDER BY id ASC

        LIMIT 1
        """,
        (
            market_snapshot_id,
        )
    )

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None

    return row["expiry"]


# ============================================================
# FIND FUTURE SNAPSHOT
# ============================================================

def find_future_snapshot(
    snapshots,
    source_timestamp,
    target_minutes
):

    target_timestamp = (
        source_timestamp
        + timedelta(
            minutes=target_minutes
        )
    )

    # load_market_snapshots() guarantees chronological order. Find the same
    # first observation as the previous scan without rescanning prior rows.
    lower = 0
    upper = len(snapshots)
    while lower < upper:
        middle = (lower + upper) // 2
        if snapshots[middle]["timestamp"] < target_timestamp:
            lower = middle + 1
        else:
            upper = middle

    if lower == len(snapshots):
        return None

    snapshot = snapshots[lower]
    snapshot_timestamp = snapshot["timestamp"]

    # The target is strictly after the source; retain the explicit guard.
    if snapshot_timestamp <= source_timestamp:
        return None

    delay_seconds = (
        snapshot_timestamp - target_timestamp
    ).total_seconds()
    if delay_seconds > MAX_FUTURE_DELAY_SECONDS:
        return None

    return {
        "snapshot": snapshot,
        "target_timestamp": target_timestamp,
        "delay_seconds": delay_seconds,
    }


# ============================================================
# CALCULATE RETURN
# ============================================================

def calculate_return_pct(
    entry_price,
    future_price
):

    if entry_price <= 0:
        return None

    return (
        (
            future_price
            - entry_price
        )
        / entry_price
    ) * 100.0


# ============================================================
# CLASSIFY DIRECTION
# ============================================================

def classify_direction(
    return_pct
):

    if return_pct is None:
        return "INVALID"

    if (
        return_pct
        >= DIRECTION_THRESHOLD_PERCENT
    ):

        return "BULLISH"

    if (
        return_pct
        <= -DIRECTION_THRESHOLD_PERCENT
    ):

        return "BEARISH"

    return "FLAT"


# ============================================================
# BUILD ONE OUTCOME
# ============================================================

def build_horizon_outcome(
    snapshots,
    source_timestamp,
    source_price,
    minutes
):

    future_result = find_future_snapshot(
        snapshots=snapshots,

        source_timestamp=
            source_timestamp,

        target_minutes=
            minutes
    )

    if future_result is None:

        return {
            "valid": False,

            "price": None,

            "timestamp": None,

            "change_points": None,

            "return_pct": None,

            "direction": "UNAVAILABLE",

            "delay_seconds": None
        }

    future_snapshot = (
        future_result["snapshot"]
    )

    future_price = (
        future_snapshot[
            "spot_price"
        ]
    )

    change_points = (
        future_price
        - source_price
    )

    return_pct = (
        calculate_return_pct(
            entry_price=source_price,
            future_price=future_price
        )
    )

    direction = (
        classify_direction(
            return_pct
        )
    )

    return {
        "valid": True,

        "price":
            future_price,

        "timestamp":
            future_snapshot[
                "timestamp_utc"
            ],

        "change_points":
            change_points,

        "return_pct":
            return_pct,

        "direction":
            direction,

        "delay_seconds":
            future_result[
                "delay_seconds"
            ]
    }


# ============================================================
# STORE OUTCOME
# ============================================================

def store_outcome(
    source,
    expiry,
    outcomes
):

    connection = get_write_connection()

    cursor = connection.cursor()

    created_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    o5 = outcomes["5m"]
    o15 = outcomes["15m"]
    o30 = outcomes["30m"]
    o60 = outcomes["60m"]

    try:

        cursor.execute(
            """
            INSERT OR IGNORE INTO historical_outcomes (

                market_snapshot_id,
                timestamp_utc,
                spot_price,
                expiry,

                outcome_5m_price,
                outcome_5m_timestamp,
                outcome_5m_change_points,
                outcome_5m_return_pct,
                outcome_5m_direction,
                outcome_5m_delay_seconds,
                outcome_5m_valid,

                outcome_15m_price,
                outcome_15m_timestamp,
                outcome_15m_change_points,
                outcome_15m_return_pct,
                outcome_15m_direction,
                outcome_15m_delay_seconds,
                outcome_15m_valid,

                outcome_30m_price,
                outcome_30m_timestamp,
                outcome_30m_change_points,
                outcome_30m_return_pct,
                outcome_30m_direction,
                outcome_30m_delay_seconds,
                outcome_30m_valid,

                outcome_60m_price,
                outcome_60m_timestamp,
                outcome_60m_change_points,
                outcome_60m_return_pct,
                outcome_60m_direction,
                outcome_60m_delay_seconds,
                outcome_60m_valid,

                created_at_utc

            )

            VALUES (

                ?, ?, ?, ?,

                ?, ?, ?, ?, ?, ?, ?,

                ?, ?, ?, ?, ?, ?, ?,

                ?, ?, ?, ?, ?, ?, ?,

                ?, ?, ?, ?, ?, ?, ?,

                ?

            )
            """,

            (

                source["id"],

                source[
                    "timestamp_utc"
                ],

                source[
                    "spot_price"
                ],

                expiry,

                # ==================================================
                # 5 MINUTES
                # ==================================================

                o5["price"],
                o5["timestamp"],
                o5["change_points"],
                o5["return_pct"],
                o5["direction"],
                o5["delay_seconds"],
                int(o5["valid"]),

                # ==================================================
                # 15 MINUTES
                # ==================================================

                o15["price"],
                o15["timestamp"],
                o15["change_points"],
                o15["return_pct"],
                o15["direction"],
                o15["delay_seconds"],
                int(o15["valid"]),

                # ==================================================
                # 30 MINUTES
                # ==================================================

                o30["price"],
                o30["timestamp"],
                o30["change_points"],
                o30["return_pct"],
                o30["direction"],
                o30["delay_seconds"],
                int(o30["valid"]),

                # ==================================================
                # 60 MINUTES
                # ==================================================

                o60["price"],
                o60["timestamp"],
                o60["change_points"],
                o60["return_pct"],
                o60["direction"],
                o60["delay_seconds"],
                int(o60["valid"]),

                created_at
            )
        )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# BUILD ALL HISTORICAL OUTCOMES
# ============================================================

def build_historical_outcomes():

    initialize_outcome_table()

    snapshots = (
        load_market_snapshots()
    )

    feature_snapshot_ids = (
        load_feature_snapshot_ids()
    )

    if not snapshots:

        raise RuntimeError(
            "No valid market snapshots found."
        )

    if not feature_snapshot_ids:

        raise RuntimeError(
            "No validated market features found."
        )

    processed = 0

    skipped_no_features = 0

    valid_counts = {
        "5m": 0,
        "15m": 0,
        "30m": 0,
        "60m": 0
    }

    unavailable_counts = {
        "5m": 0,
        "15m": 0,
        "30m": 0,
        "60m": 0
    }

    for source in snapshots:

        source_id = source["id"]

        # ----------------------------------------------------
        # Only feature snapshots become ML samples.
        # ----------------------------------------------------

        if (
            source_id
            not in feature_snapshot_ids
        ):

            skipped_no_features += 1

            continue

        outcomes = {}

        for horizon_name, minutes in HORIZONS.items():

            outcome = (
                build_horizon_outcome(
                    snapshots=
                        snapshots,

                    source_timestamp=
                        source[
                            "timestamp"
                        ],

                    source_price=
                        source[
                            "spot_price"
                        ],

                    minutes=minutes
                )
            )

            outcomes[
                horizon_name
            ] = outcome

            if outcome["valid"]:

                valid_counts[
                    horizon_name
                ] += 1

            else:

                unavailable_counts[
                    horizon_name
                ] += 1

        expiry = (
            get_snapshot_expiry(
                source_id
            )
        )

        store_outcome(
            source=
                source,

            expiry=
                expiry,

            outcomes=
                outcomes
        )

        processed += 1

    return {

        "processed":
            processed,

        "skipped_no_features":
            skipped_no_features,

        "valid_counts":
            valid_counts,

        "unavailable_counts":
            unavailable_counts
    }


# ============================================================
# DATABASE SUMMARY
# ============================================================

def get_outcome_summary():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM historical_outcomes
        """
    )

    total = cursor.fetchone()[0]

    summary = {
        "total": total
    }

    for horizon in HORIZONS:

        cursor.execute(
            f"""
            SELECT COUNT(*)

            FROM historical_outcomes

            WHERE outcome_{horizon}_valid = 1
            """
        )

        summary[
            f"valid_{horizon}"
        ] = cursor.fetchone()[0]

    connection.close()

    return summary


# ============================================================
# DIRECTION DISTRIBUTION
# ============================================================

def get_direction_distribution(
    column
):

    allowed_columns = {

        "outcome_5m_direction",

        "outcome_15m_direction",

        "outcome_30m_direction",

        "outcome_60m_direction"
    }

    if column not in allowed_columns:

        raise ValueError(
            f"Invalid outcome column: "
            f"{column}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        f"""
        SELECT
            {column} AS direction,
            COUNT(*) AS count

        FROM historical_outcomes

        WHERE
            {column} IS NOT NULL

        GROUP BY
            {column}

        ORDER BY
            count DESC
        """
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


# ============================================================
# DATA INTEGRITY CHECK
# ============================================================

def validate_outcome_integrity():

    connection = get_connection()

    cursor = connection.cursor()

    # --------------------------------------------------------
    # Duplicate source snapshots
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            market_snapshot_id,
            COUNT(*) AS count

        FROM historical_outcomes

        GROUP BY
            market_snapshot_id

        HAVING COUNT(*) > 1
        """
    )

    duplicate_rows = cursor.fetchall()

    # --------------------------------------------------------
    # Invalid outcome flags
    # --------------------------------------------------------

    invalid_flags = 0

    for horizon in HORIZONS:

        cursor.execute(
            f"""
            SELECT COUNT(*)

            FROM historical_outcomes

            WHERE outcome_{horizon}_valid
            NOT IN (0, 1)
            """
        )

        invalid_flags += (
            cursor.fetchone()[0]
        )

    # --------------------------------------------------------
    # Valid outcomes with missing price
    # --------------------------------------------------------

    invalid_valid_rows = 0

    for horizon in HORIZONS:

        cursor.execute(
            f"""
            SELECT COUNT(*)

            FROM historical_outcomes

            WHERE
                outcome_{horizon}_valid = 1

                AND

                outcome_{horizon}_price IS NULL
            """
        )

        invalid_valid_rows += (
            cursor.fetchone()[0]
        )

    connection.close()

    return {

        "duplicate_sources":
            len(duplicate_rows),

        "invalid_flags":
            invalid_flags,

        "valid_rows_missing_price":
            invalid_valid_rows
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "HISTORICAL OUTCOME BUILDER"
    )

    print("=" * 70)

    print()

    print(
        "Building future NIFTY outcomes..."
    )

    print(
        "Future prices are used ONLY "
        "as outcome labels."
    )

    print(
        "They are NOT used as model features."
    )

    print()

    try:

        result = (
            build_historical_outcomes()
        )

    except Exception as error:

        print()

        print(
            "OUTCOME BUILD FAILED"
        )

        print("-" * 70)

        print(
            f"Error type    : "
            f"{type(error).__name__}"
        )

        print(
            f"Error message : "
            f"{error}"
        )

        print()

        print("=" * 70)

        raise SystemExit(1)

    # ========================================================
    # BUILD RESULT
    # ========================================================

    print(
        "BUILD RESULT"
    )

    print("-" * 70)

    print(
        f"Processed feature snapshots : "
        f"{result['processed']}"
    )

    print(
        f"Skipped without features    : "
        f"{result['skipped_no_features']}"
    )

    # ========================================================
    # VALID OUTCOMES
    # ========================================================

    print()

    print(
        "VALID OUTCOMES"
    )

    print("-" * 70)

    for horizon in HORIZONS:

        print(
            f"{horizon:>3} : "
            f"{result['valid_counts'][horizon]}"
        )

    # ========================================================
    # UNAVAILABLE OUTCOMES
    # ========================================================

    print()

    print(
        "UNAVAILABLE OUTCOMES"
    )

    print("-" * 70)

    for horizon in HORIZONS:

        print(
            f"{horizon:>3} : "
            f"{result['unavailable_counts'][horizon]}"
        )

    # ========================================================
    # DATABASE SUMMARY
    # ========================================================

    summary = (
        get_outcome_summary()
    )

    print()

    print(
        "DATABASE SUMMARY"
    )

    print("-" * 70)

    print(
        f"Total outcome rows : "
        f"{summary['total']}"
    )

    for horizon in HORIZONS:

        print(
            f"Valid +{horizon:<3}        : "
            f"{summary[f'valid_{horizon}']}"
        )

    # ========================================================
    # DIRECTION DISTRIBUTION
    # ========================================================

    print()

    print(
        "OUTCOME DISTRIBUTION"
    )

    print("-" * 70)

    for horizon in HORIZONS:

        column = (
            f"outcome_{horizon}_direction"
        )

        rows = (
            get_direction_distribution(
                column
            )
        )

        print()

        print(
            horizon.upper()
        )

        if not rows:

            print(
                "  No outcomes available."
            )

            continue

        for row in rows:

            print(
                f"  {row['direction']:12s}"
                f" : {row['count']}"
            )

    # ========================================================
    # INTEGRITY
    # ========================================================

    integrity = (
        validate_outcome_integrity()
    )

    print()

    print(
        "OUTCOME INTEGRITY"
    )

    print("-" * 70)

    print(
        f"Duplicate source rows    : "
        f"{integrity['duplicate_sources']}"
    )

    print(
        f"Invalid validity flags   : "
        f"{integrity['invalid_flags']}"
    )

    print(
        f"Valid rows missing price : "
        f"{integrity['valid_rows_missing_price']}"
    )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    passed = (

        integrity[
            "duplicate_sources"
        ] == 0

        and

        integrity[
            "invalid_flags"
        ] == 0

        and

        integrity[
            "valid_rows_missing_price"
        ] == 0
    )

    print()

    print("-" * 70)

    if passed:

        print(
            "OUTCOME BUILD STATUS : PASS"
        )

    else:

        print(
            "OUTCOME BUILD STATUS : FAIL"
        )

    print()

    print("=" * 70)

    print(
        "HISTORICAL OUTCOME BUILD COMPLETED"
    )

    print("=" * 70)