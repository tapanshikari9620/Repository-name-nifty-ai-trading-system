import sqlite3
import math
import os

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = os.environ.get(
    "NIFTY_MARKET_DATABASE",
    str(Path(__file__).resolve().parent / "nifty_market_data.db"),
)

REQUIRED_OPTION_NUMERIC_FIELDS = (
    "oi",
    "oi_change",
    "volume",
)

OPTION_NUMERIC_FIELDS = (
    "ltp",
    "close_price",
    "volume",
    "oi",
    "prev_oi",
    "oi_change",
    "bid_price",
    "bid_qty",
    "ask_price",
    "ask_qty",
    "iv",
    "delta",
    "gamma",
    "theta",
    "vega",
    "pop",
)

MAX_CONTINUITY_GAP_SECONDS = 90.0
DEFAULT_FEATURE_BATCH_SIZE = int(
    os.environ.get("NIFTY_FEATURE_BATCH_SIZE", "100")
)
PRODUCTION_DATABASE_PATH = (
    Path(__file__).resolve().parent / "nifty_market_data.db"
).resolve()


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

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def assert_safe_write_target(connection):
    database_path = Path(DATABASE_NAME).expanduser().resolve()
    production_path = PRODUCTION_DATABASE_PATH

    if database_path == production_path:
        raise RuntimeError(
            "Historical feature writes are disabled for the production "
            f"database: {database_path}"
        )

    database_rows = connection.execute(
        "PRAGMA database_list"
    ).fetchall()
    connected_paths = {
        Path(row[2]).expanduser().resolve()
        for row in database_rows
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


def finite_number(value):
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def validate_snapshot_records(market_row, option_rows):
    errors = []
    market_snapshot_id = market_row["id"]
    market_timestamp = parse_timestamp(market_row["timestamp_utc"])
    spot_price = finite_number(market_row["spot_price"])

    if market_timestamp is None:
        errors.append("Market snapshot timestamp is missing or invalid.")

    if spot_price is None or spot_price <= 0:
        errors.append("Market spot price must be finite and greater than zero.")

    if not option_rows:
        errors.append("Snapshot has no option records.")
        return errors

    expiries = set()
    ce_strikes = set()
    pe_strikes = set()
    contracts = set()
    instrument_keys = set()

    for row in option_rows:
        if row["market_snapshot_id"] != market_snapshot_id:
            errors.append(
                f"Option record {row['id']} links to a different market snapshot."
            )

        expiry_value = row["expiry"]
        expiry = str(expiry_value).strip() if expiry_value is not None else ""
        if not expiry:
            errors.append(f"Option record {row['id']} has no valid expiry.")
        else:
            expiries.add(expiry)

        row_timestamp = parse_timestamp(row["timestamp_utc"])
        if row_timestamp is None:
            errors.append(f"Option record {row['id']} has an invalid timestamp.")
        elif market_timestamp is None or row_timestamp != market_timestamp:
            errors.append(
                f"Option record {row['id']} timestamp does not match "
                "its market snapshot."
            )

        strike = finite_number(row["strike"])
        if strike is None or strike <= 0:
            errors.append(f"Option record {row['id']} has an invalid strike.")

        option_type = row["option_type"]
        if option_type not in ("CE", "PE"):
            errors.append(
                f"Option record {row['id']} has invalid type {option_type!r}."
            )

        for field in OPTION_NUMERIC_FIELDS:
            value = row[field]
            numeric_value = finite_number(value)
            if field in REQUIRED_OPTION_NUMERIC_FIELDS and value is None:
                errors.append(
                    f"Option record {row['id']} is missing required numeric "
                    f"field {field!r}."
                )
            elif value is not None and numeric_value is None:
                errors.append(
                    f"Option record {row['id']} field {field!r} "
                    "is not a finite number."
                )
            elif (
                numeric_value is not None
                and field in ("oi", "volume")
                and numeric_value < 0
            ):
                errors.append(
                    f"Option record {row['id']} field {field!r} cannot be negative."
                )

        if strike is not None and strike > 0 and option_type in ("CE", "PE"):
            contract = (expiry, strike, option_type)
            if contract in contracts:
                errors.append(
                    "Duplicate option contract: "
                    f"expiry={expiry!r}, strike={strike:g}, type={option_type}."
                )
            contracts.add(contract)
            if option_type == "CE":
                ce_strikes.add(strike)
            else:
                pe_strikes.add(strike)

        instrument_key = row["instrument_key"]
        if instrument_key:
            if instrument_key in instrument_keys:
                errors.append(
                    f"Duplicate instrument key {instrument_key!r} in snapshot."
                )
            instrument_keys.add(instrument_key)

    if len(expiries) != 1:
        errors.append(
            "Snapshot must contain exactly one non-empty expiry; "
            f"found {len(expiries)}."
        )

    if not ce_strikes or not pe_strikes or ce_strikes != pe_strikes:
        errors.append("CE and PE contracts do not have matching strike coverage.")

    return errors


# ============================================================
# FIND ATM STRIKE
# ============================================================

def find_atm(
    spot_price,
    strikes
):

    if spot_price is None:
        return None

    if not strikes:
        return None

    return min(
        strikes,
        key=lambda strike:
            abs(
                strike
                - spot_price
            )
    )


# ============================================================
# LOAD MARKET + OPTION SNAPSHOTS
# ============================================================

def load_snapshot_data(limit=None, offset=0):

    connection = get_connection()

    cursor = connection.cursor()

    market_query = """
        SELECT
            id,
            timestamp_utc,
            spot_price

        FROM market_snapshots

        ORDER BY
            timestamp_utc ASC,
            id ASC
    """
    market_parameters = ()
    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            connection.close()
            raise ValueError("Snapshot batch limit must be a positive integer.")
        if not isinstance(offset, int) or offset < 0:
            connection.close()
            raise ValueError("Snapshot batch offset cannot be negative.")
        market_query += " LIMIT ? OFFSET ?"
        market_parameters = (limit, offset)

    cursor.execute(market_query, market_parameters)

    market_rows = cursor.fetchall()

    if not market_rows:
        connection.close()
        return []

    snapshot_ids = [row["id"] for row in market_rows]
    placeholders = ",".join("?" for _ in snapshot_ids)
    cursor.execute(
        f"""
        SELECT *
        FROM option_snapshots
        WHERE market_snapshot_id IN ({placeholders})
        ORDER BY market_snapshot_id, strike ASC, option_type ASC
        """,
        snapshot_ids,
    )
    options_by_snapshot = {}
    for row in cursor.fetchall():
        options_by_snapshot.setdefault(
            row["market_snapshot_id"], []
        ).append(row)

    snapshots = []

    for market_row in market_rows:

        snapshot_id = market_row["id"]
        option_rows = options_by_snapshot.get(snapshot_id, [])

        # ----------------------------------------------------
        # Separate CE / PE
        # ----------------------------------------------------

        ce_rows = [
            row
            for row in option_rows
            if row["option_type"] == "CE"
        ]

        pe_rows = [
            row
            for row in option_rows
            if row["option_type"] == "PE"
        ]

        # ----------------------------------------------------
        # Timestamp
        # ----------------------------------------------------

        timestamp = parse_timestamp(
            market_row[
                "timestamp_utc"
            ]
        )

        validation_errors = validate_snapshot_records(
            market_row,
            option_rows,
        )

        expiries = {
            str(row["expiry"]).strip()
            for row in option_rows
            if row["expiry"] is not None and str(row["expiry"]).strip()
        }

        snapshots.append(
            {
                "market_snapshot_id":
                    snapshot_id,

                "timestamp_utc":
                    market_row[
                        "timestamp_utc"
                    ],

                "timestamp":
                    timestamp,

                "spot_price":
                    finite_number(
                        market_row[
                            "spot_price"
                        ]
                    ),

                "option_rows":
                    option_rows,

                "ce_rows":
                    ce_rows,

                "pe_rows":
                    pe_rows,

                "expiry":
                    next(
                        iter(expiries),
                        None
                    ),

                "validation_errors":
                    validation_errors,

                "complete":
                    not validation_errors
            }
        )

    connection.close()

    return snapshots


# ============================================================
# LOAD COLLECTION HEALTH
# ============================================================

def load_collection_health(snapshot_ids=None):

    connection = get_connection()

    cursor = connection.cursor()

    query = """
        SELECT
            market_snapshot_id,
            status,
            validation_status

        FROM collection_health

        WHERE market_snapshot_id IS NOT NULL
    """
    parameters = ()
    if snapshot_ids is not None:
        if not snapshot_ids:
            connection.close()
            return {}
        placeholders = ",".join("?" for _ in snapshot_ids)
        query += f" AND market_snapshot_id IN ({placeholders})"
        parameters = tuple(snapshot_ids)

    cursor.execute(query, parameters)

    rows = cursor.fetchall()

    connection.close()

    health = {}

    for row in rows:

        health[
            row[
                "market_snapshot_id"
            ]
        ] = {

            "status":
                row["status"],

            "validation_status":
                row["validation_status"]
        }

    return health


# ============================================================
# CHECK COLLECTION HEALTH
# ============================================================

def is_snapshot_health_valid(
    snapshot_id,
    health
):

    # Older historical snapshots may not have
    # collection-health records.

    if snapshot_id not in health:

        return True

    record = health[
        snapshot_id
    ]

    if (
        record["status"]
        != "SUCCESS"
    ):

        return False

    validation_status = (
        record[
            "validation_status"
        ]
    )

    if (
        validation_status
        and validation_status
        != "PASS"
    ):

        return False

    return True


# ============================================================
# CALCULATE SNAPSHOT CONTINUITY
# ============================================================

def calculate_continuity(
    snapshots,
    previous_valid_snapshot=None,
):

    for snapshot in snapshots:

        snapshot[
            "previous_snapshot_id"
        ] = None

        snapshot[
            "snapshot_interval_seconds"
        ] = None

        snapshot[
            "continuous"
        ] = False

        # ----------------------------------------------------
        # Invalid snapshot cannot become the previous
        # reference point.
        # ----------------------------------------------------

        if not snapshot["complete"]:

            continue

        # ----------------------------------------------------
        # First valid snapshot
        # ----------------------------------------------------

        if previous_valid_snapshot is None:

            previous_valid_snapshot = (
                snapshot
            )

            continue

        # ----------------------------------------------------
        # Calculate interval
        # ----------------------------------------------------

        interval = (

            snapshot[
                "timestamp"
            ]

            -

            previous_valid_snapshot[
                "timestamp"
            ]

        ).total_seconds()

        snapshot[
            "previous_snapshot_id"
        ] = (
            previous_valid_snapshot[
                "market_snapshot_id"
            ]
        )

        snapshot[
            "snapshot_interval_seconds"
        ] = interval

        snapshot[
            "continuous"
        ] = (

            interval
            <= MAX_CONTINUITY_GAP_SECONDS
        )

        previous_valid_snapshot = (
            snapshot
        )

    return previous_valid_snapshot


# ============================================================
# CALCULATE MARKET FEATURES
# ============================================================

def calculate_market_features(
    snapshot
):

    spot_price = snapshot[
        "spot_price"
    ]

    ce_rows = snapshot[
        "ce_rows"
    ]

    pe_rows = snapshot[
        "pe_rows"
    ]

    # ========================================================
    # STRIKES
    # ========================================================

    strikes = sorted(
        {
            safe_number(
                row["strike"]
            )

            for row in snapshot[
                "option_rows"
            ]
        }
    )

    atm_strike = find_atm(
        spot_price,
        strikes
    )

    # ========================================================
    # TOTAL CE OI
    # ========================================================

    total_ce_oi = sum(
        safe_number(
            row["oi"]
        )
        for row in ce_rows
    )

    # ========================================================
    # TOTAL PE OI
    # ========================================================

    total_pe_oi = sum(
        safe_number(
            row["oi"]
        )
        for row in pe_rows
    )

    # ========================================================
    # PCR
    # ========================================================

    if total_ce_oi > 0:

        pcr = (
            total_pe_oi
            / total_ce_oi
        )

    else:

        pcr = None

    # ========================================================
    # TOTAL CE OI CHANGE
    # ========================================================

    total_ce_oi_change = sum(
        safe_number(
            row["oi_change"]
        )
        for row in ce_rows
    )

    # ========================================================
    # TOTAL PE OI CHANGE
    # ========================================================

    total_pe_oi_change = sum(
        safe_number(
            row["oi_change"]
        )
        for row in pe_rows
    )

    # ========================================================
    # OI PRESSURE
    # ========================================================

    oi_pressure = (
        total_pe_oi_change
        - total_ce_oi_change
    )

    # ========================================================
    # TOTAL CE VOLUME
    # ========================================================

    total_ce_volume = sum(
        safe_number(
            row["volume"]
        )
        for row in ce_rows
    )

    # ========================================================
    # TOTAL PE VOLUME
    # ========================================================

    total_pe_volume = sum(
        safe_number(
            row["volume"]
        )
        for row in pe_rows
    )

    # ========================================================
    # VOLUME PRESSURE
    # ========================================================

    volume_pressure = (
        total_pe_volume
        - total_ce_volume
    )

    # ========================================================
    # HIGHEST CE OI
    # ========================================================

    highest_ce_oi_row = max(
        ce_rows,
        key=lambda row:
            safe_number(
                row["oi"]
            )
    )

    highest_ce_oi = safe_number(
        highest_ce_oi_row["oi"]
    )

    resistance = safe_number(
        highest_ce_oi_row["strike"]
    )

    # ========================================================
    # HIGHEST PE OI
    # ========================================================

    highest_pe_oi_row = max(
        pe_rows,
        key=lambda row:
            safe_number(
                row["oi"]
            )
    )

    highest_pe_oi = safe_number(
        highest_pe_oi_row["oi"]
    )

    support = safe_number(
        highest_pe_oi_row["strike"]
    )

    # ========================================================
    # HIGHEST CE OI CHANGE
    # ========================================================

    highest_ce_oi_change_row = max(
        ce_rows,
        key=lambda row:
            safe_number(
                row["oi_change"]
            )
    )

    highest_ce_oi_change = (
        safe_number(
            highest_ce_oi_change_row[
                "oi_change"
            ]
        )
    )

    # ========================================================
    # HIGHEST PE OI CHANGE
    # ========================================================

    highest_pe_oi_change_row = max(
        pe_rows,
        key=lambda row:
            safe_number(
                row["oi_change"]
            )
    )

    highest_pe_oi_change = (
        safe_number(
            highest_pe_oi_change_row[
                "oi_change"
            ]
        )
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {

        "market_snapshot_id":
            snapshot[
                "market_snapshot_id"
            ],

        "timestamp_utc":
            snapshot[
                "timestamp_utc"
            ],

        "spot_price":
            spot_price,

        "atm_strike":
            atm_strike,

        "support":
            support,

        "resistance":
            resistance,

        "total_ce_oi":
            total_ce_oi,

        "total_pe_oi":
            total_pe_oi,

        "pcr":
            pcr,

        "total_ce_oi_change":
            total_ce_oi_change,

        "total_pe_oi_change":
            total_pe_oi_change,

        "oi_pressure":
            oi_pressure,

        "total_ce_volume":
            total_ce_volume,

        "total_pe_volume":
            total_pe_volume,

        "volume_pressure":
            volume_pressure,

        "highest_ce_oi":
            highest_ce_oi,

        "highest_pe_oi":
            highest_pe_oi,

        "highest_ce_oi_change":
            highest_ce_oi_change,

        "highest_pe_oi_change":
            highest_pe_oi_change
    }


# ============================================================
# STORE MARKET FEATURE
# ============================================================

def store_market_feature_row(
    features,
    connection=None,
):

    owns_connection = connection is None
    if owns_connection:
        connection = get_write_connection()
    else:
        assert_safe_write_target(connection)

    cursor = connection.cursor()

    created_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO market_features (

            market_snapshot_id,
            timestamp_utc,
            spot_price,
            atm_strike,
            support,
            resistance,
            total_ce_oi,
            total_pe_oi,
            pcr,
            total_ce_oi_change,
            total_pe_oi_change,
            oi_pressure,
            total_ce_volume,
            total_pe_volume,
            volume_pressure,
            highest_ce_oi,
            highest_pe_oi,
            highest_ce_oi_change,
            highest_pe_oi_change,
            created_at_utc

        )

        VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,

        (
            features[
                "market_snapshot_id"
            ],

            features[
                "timestamp_utc"
            ],

            features[
                "spot_price"
            ],

            features[
                "atm_strike"
            ],

            features[
                "support"
            ],

            features[
                "resistance"
            ],

            features[
                "total_ce_oi"
            ],

            features[
                "total_pe_oi"
            ],

            features[
                "pcr"
            ],

            features[
                "total_ce_oi_change"
            ],

            features[
                "total_pe_oi_change"
            ],

            features[
                "oi_pressure"
            ],

            features[
                "total_ce_volume"
            ],

            features[
                "total_pe_volume"
            ],

            features[
                "volume_pressure"
            ],

            features[
                "highest_ce_oi"
            ],

            features[
                "highest_pe_oi"
            ],

            features[
                "highest_ce_oi_change"
            ],

            features[
                "highest_pe_oi_change"
            ],

            created_at
        )
    )

    inserted = cursor.rowcount
    if owns_connection:
        connection.commit()
        connection.close()
    return inserted


# ============================================================
# STORE OPTION FEATURE ROWS
# ============================================================

def store_option_feature_rows(
    snapshot,
    connection=None,
):

    owns_connection = connection is None
    if owns_connection:
        connection = get_write_connection()
    else:
        assert_safe_write_target(connection)

    cursor = connection.cursor()

    created_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    inserted = 0

    try:

        for row in snapshot[
            "option_rows"
        ]:

            cursor.execute(
                """
                INSERT OR IGNORE INTO option_features (

                    market_snapshot_id,
                    timestamp_utc,
                    expiry,
                    strike,
                    option_type,
                    ltp,
                    close_price,
                    volume,
                    oi,
                    prev_oi,
                    oi_change,
                    bid_price,
                    bid_qty,
                    ask_price,
                    ask_qty,
                    iv,
                    delta,
                    gamma,
                    theta,
                    vega,
                    pop,
                    created_at_utc

                )

                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,

                (
                    snapshot[
                        "market_snapshot_id"
                    ],

                    snapshot[
                        "timestamp_utc"
                    ],

                    row[
                        "expiry"
                    ],

                    safe_number(
                        row[
                            "strike"
                        ]
                    ),

                    row[
                        "option_type"
                    ],

                    row[
                        "ltp"
                    ],

                    row[
                        "close_price"
                    ],

                    row[
                        "volume"
                    ],

                    row[
                        "oi"
                    ],

                    row[
                        "prev_oi"
                    ],

                    row[
                        "oi_change"
                    ],

                    row[
                        "bid_price"
                    ],

                    row[
                        "bid_qty"
                    ],

                    row[
                        "ask_price"
                    ],

                    row[
                        "ask_qty"
                    ],

                    row[
                        "iv"
                    ],

                    row[
                        "delta"
                    ],

                    row[
                        "gamma"
                    ],

                    row[
                        "theta"
                    ],

                    row[
                        "vega"
                    ],

                    row[
                        "pop"
                    ],

                    created_at
                )
            )

            inserted += 1

        if owns_connection:
            connection.commit()

        return inserted

    except Exception:

        if owns_connection:
            connection.rollback()

        raise

    finally:

        if owns_connection:
            connection.close()


# ============================================================
# FEATURE COUNT
# ============================================================

def get_feature_count(
    table_name
):

    allowed_tables = {
        "market_features",
        "option_features"
    }

    if table_name not in allowed_tables:

        raise ValueError(
            f"Invalid feature table: "
            f"{table_name}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name}
        """
    )

    count = cursor.fetchone()[0]

    connection.close()

    return count


# ============================================================
# BUILD HISTORICAL FEATURES
# ============================================================

def build_historical_features(
    batch_size=DEFAULT_FEATURE_BATCH_SIZE,
    progress_callback=None,
):
    if not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer.")

    read_connection = get_connection()
    total_snapshots = read_connection.execute(
        "SELECT COUNT(*) FROM market_snapshots"
    ).fetchone()[0]
    read_connection.close()
    if not total_snapshots:
        raise RuntimeError("No market snapshots found.")

    market_features_before = get_feature_count("market_features")
    option_features_before = get_feature_count("option_features")
    counts = {
        "processed_snapshots": 0,
        "complete_snapshots": 0,
        "skipped_incomplete": 0,
        "skipped_unhealthy": 0,
        "rejected_snapshots": 0,
        "failed_snapshots": 0,
        "continuous_snapshots": 0,
        "non_continuous_snapshots": 0,
        "batches_processed": 0,
    }
    rejection_reasons = {}
    failure_reasons = {}
    previous_valid_snapshot = None

    def add_reason(reason_counts, reason):
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    for offset in range(0, total_snapshots, batch_size):
        snapshots = load_snapshot_data(
            limit=batch_size,
            offset=offset,
        )
        if not snapshots:
            break

        snapshot_ids = [
            snapshot["market_snapshot_id"]
            for snapshot in snapshots
        ]
        health = load_collection_health(snapshot_ids)
        previous_valid_snapshot = calculate_continuity(
            snapshots,
            previous_valid_snapshot,
        )
        batch_processed = 0
        batch_rejected = 0
        batch_failed = 0

        write_connection = get_connection()
        try:
            assert_safe_write_target(write_connection)
            for snapshot in snapshots:
                snapshot_id = snapshot["market_snapshot_id"]

                if not snapshot["complete"]:
                    counts["skipped_incomplete"] += 1
                    counts["rejected_snapshots"] += 1
                    batch_rejected += 1
                    for reason in snapshot["validation_errors"]:
                        add_reason(rejection_reasons, reason)
                    continue

                if not is_snapshot_health_valid(snapshot_id, health):
                    counts["skipped_unhealthy"] += 1
                    add_reason(
                        rejection_reasons,
                        "Collection health rejected snapshot.",
                    )
                    continue

                if snapshot["continuous"]:
                    counts["continuous_snapshots"] += 1
                else:
                    counts["non_continuous_snapshots"] += 1

                counts["complete_snapshots"] += 1
                try:
                    market_features = calculate_market_features(snapshot)
                except Exception as error:
                    counts["failed_snapshots"] += 1
                    batch_failed += 1
                    add_reason(
                        failure_reasons,
                        f"{type(error).__name__}: {error}",
                    )
                    continue

                store_market_feature_row(
                    market_features,
                    connection=write_connection,
                )
                store_option_feature_rows(
                    snapshot,
                    connection=write_connection,
                )
                counts["processed_snapshots"] += 1
                batch_processed += 1

            write_connection.commit()
        except BaseException:
            write_connection.rollback()
            raise
        finally:
            write_connection.close()

        counts["batches_processed"] += 1
        processed_through = min(offset + len(snapshots), total_snapshots)
        progress = {
            "batch": counts["batches_processed"],
            "batch_size": batch_size,
            "processed_through": processed_through,
            "total_snapshots": total_snapshots,
            "processed_snapshots": counts["processed_snapshots"],
            "rejected_snapshots": counts["rejected_snapshots"],
            "failed_snapshots": counts["failed_snapshots"],
        }
        if progress_callback is not None:
            progress_callback(progress)
        else:
            print(
                f"Batch {progress['batch']}: "
                f"{processed_through}/{total_snapshots} scanned; "
                f"processed={batch_processed}, "
                f"rejected={batch_rejected}, failed={batch_failed}"
            )

        if previous_valid_snapshot is not None:
            previous_valid_snapshot = {
                "market_snapshot_id":
                    previous_valid_snapshot["market_snapshot_id"],
                "timestamp":
                    previous_valid_snapshot["timestamp"],
                "complete": True,
            }
        del snapshots

    market_features_after = get_feature_count("market_features")
    option_features_after = get_feature_count("option_features")
    return {
        "total_snapshots": total_snapshots,
        **counts,
        "skipped_validation_reasons": rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "failure_reasons": failure_reasons,
        "market_features_created":
            market_features_after - market_features_before,
        "option_features_created":
            option_features_after - option_features_before,
        "market_feature_total": market_features_after,
        "option_feature_total": option_features_after,
    }


# ============================================================
# VERIFY FEATURE DATA
# ============================================================

def verify_feature_data():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            COUNT(*),
            COUNT(
                DISTINCT market_snapshot_id
            )

        FROM market_features
        """
    )

    market_count, market_snapshots = (
        cursor.fetchone()
    )

    cursor.execute(
        """
        SELECT
            COUNT(*),
            COUNT(
                DISTINCT market_snapshot_id
            )

        FROM option_features
        """
    )

    option_count, option_snapshots = (
        cursor.fetchone()
    )

    connection.close()

    return {

        "market_feature_rows":
            market_count,

        "market_feature_snapshots":
            market_snapshots,

        "option_feature_rows":
            option_count,

        "option_feature_snapshots":
            option_snapshots
    }


# ============================================================
# VERIFY FEATURE INTEGRITY
# ============================================================

def verify_feature_integrity():
    connection = get_connection()
    invalid_feature_snapshots = set()
    missing_option_features = 0
    cursor = connection.cursor()
    market_feature_timestamps = {
        row["market_snapshot_id"]: row["timestamp_utc"]
        for row in cursor.execute(
            "SELECT market_snapshot_id, timestamp_utc FROM market_features"
        )
    }
    market_feature_ids = set(market_feature_timestamps)
    option_duplicate_groups = 0
    market_duplicate_groups = cursor.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT market_snapshot_id
            FROM market_features
            GROUP BY market_snapshot_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    orphan_option_features = cursor.execute(
        """
        SELECT COUNT(*)
        FROM option_features AS feature
        LEFT JOIN market_features AS market_feature
          ON market_feature.market_snapshot_id = feature.market_snapshot_id
        LEFT JOIN market_snapshots AS market
          ON market.id = feature.market_snapshot_id
        WHERE market_feature.market_snapshot_id IS NULL
           OR market.id IS NULL
        """
    ).fetchone()[0]
    total_market_snapshots = cursor.execute(
        "SELECT COUNT(*) FROM market_snapshots"
    ).fetchone()[0]
    connection.close()

    seen_market_feature_ids = set()
    for offset in range(0, total_market_snapshots, DEFAULT_FEATURE_BATCH_SIZE):
        snapshots = load_snapshot_data(
            limit=DEFAULT_FEATURE_BATCH_SIZE,
            offset=offset,
        )
        snapshot_ids = [
            snapshot["market_snapshot_id"]
            for snapshot in snapshots
            if snapshot["market_snapshot_id"] in market_feature_ids
        ]
        if not snapshot_ids:
            continue

        seen_market_feature_ids.update(snapshot_ids)
        placeholders = ",".join("?" for _ in snapshot_ids)
        feature_connection = get_connection()
        feature_rows = feature_connection.execute(
            f"""
            SELECT market_snapshot_id, timestamp_utc, expiry, strike, option_type
            FROM option_features
            WHERE market_snapshot_id IN ({placeholders})
            """,
            snapshot_ids,
        ).fetchall()
        option_duplicate_groups += feature_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT market_snapshot_id, expiry, strike, option_type
                FROM option_features
                WHERE market_snapshot_id IN ({placeholders})
                GROUP BY market_snapshot_id, expiry, strike, option_type
                HAVING COUNT(*) > 1
            )
            """,
            snapshot_ids,
        ).fetchone()[0]
        feature_connection.close()
        feature_rows_by_snapshot = {}
        for row in feature_rows:
            feature_rows_by_snapshot.setdefault(
                row["market_snapshot_id"], []
            ).append(row)

        for snapshot in snapshots:
            snapshot_id = snapshot["market_snapshot_id"]
            if snapshot_id not in market_feature_ids:
                continue
            rows = feature_rows_by_snapshot.get(snapshot_id, [])
            if not snapshot["complete"]:
                invalid_feature_snapshots.add(snapshot_id)
                orphan_option_features += len(rows)
                continue

            expected_timestamp = snapshot["timestamp"]
            if (
                parse_timestamp(market_feature_timestamps[snapshot_id])
                != expected_timestamp
            ):
                invalid_feature_snapshots.add(snapshot_id)

            raw_contracts = {
                (
                    str(row["expiry"]).strip(),
                    finite_number(row["strike"]),
                    row["option_type"],
                )
                for row in snapshot["option_rows"]
            }
            stored_contracts = set()
            for row in rows:
                strike = finite_number(row["strike"])
                contract = (
                    str(row["expiry"]).strip()
                    if row["expiry"] is not None else "",
                    strike,
                    row["option_type"],
                )
                if (
                    parse_timestamp(row["timestamp_utc"]) != expected_timestamp
                    or strike is None
                    or contract not in raw_contracts
                ):
                    orphan_option_features += 1
                    invalid_feature_snapshots.add(snapshot_id)
                    continue
                stored_contracts.add(contract)

            missing = raw_contracts - stored_contracts
            missing_option_features += len(missing)
            if missing:
                invalid_feature_snapshots.add(snapshot_id)

        del snapshots

    for snapshot_id in market_feature_ids - seen_market_feature_ids:
        invalid_feature_snapshots.add(snapshot_id)

    return {
        "market_duplicates": market_duplicate_groups,

        "option_duplicates": option_duplicate_groups,

        "orphan_option_features":
            orphan_option_features,

        "missing_option_features":
            missing_option_features,

        "incomplete_feature_snapshots":
            len(invalid_feature_snapshots),
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "HISTORICAL FEATURE BUILDER"
    )

    print("=" * 70)

    print()

    print(
        "Loading historical snapshots..."
    )

    try:

        result = (
            build_historical_features()
        )

    except Exception as error:

        print()

        print(
            "FEATURE BUILD FAILED"
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

    print()

    print(
        "BUILD RESULT"
    )

    print("-" * 70)

    print(
        f"Total snapshots         : "
        f"{result['total_snapshots']}"
    )

    print(
        f"Batch size              : "
        f"{DEFAULT_FEATURE_BATCH_SIZE}"
    )

    print(
        f"Processed snapshots     : "
        f"{result['processed_snapshots']}"
    )

    print(
        f"Complete snapshots      : "
        f"{result['complete_snapshots']}"
    )

    print(
        f"Skipped incomplete      : "
        f"{result['skipped_incomplete']}"
    )

    validation_reason_counts = result["skipped_validation_reasons"]
    if isinstance(validation_reason_counts, dict):
        for validation_reason, skipped_count in sorted(
            validation_reason_counts.items()
        ):
            print(f"  {skipped_count} snapshot(s): {validation_reason}")

    print(
        f"Skipped unhealthy       : "
        f"{result['skipped_unhealthy']}"
    )

    print(
        f"Rejected snapshots      : "
        f"{result['rejected_snapshots']}"
    )

    print(
        f"Failed snapshots        : "
        f"{result['failed_snapshots']}"
    )

    for failure_reason, failed_count in sorted(
        result["failure_reasons"].items()
    ):
        print(f"  {failed_count} snapshot(s): {failure_reason}")

    print(
        f"Continuous snapshots    : "
        f"{result['continuous_snapshots']}"
    )

    print(
        f"Non-continuous snapshots: "
        f"{result['non_continuous_snapshots']}"
    )

    print(
        f"Market features created : "
        f"{result['market_features_created']}"
    )

    print(
        f"Option features created : "
        f"{result['option_features_created']}"
    )

    # ========================================================
    # DATABASE VERIFICATION
    # ========================================================

    verification = (
        verify_feature_data()
    )

    print()

    print(
        "FEATURE DATABASE"
    )

    print("-" * 70)

    print(
        f"Market feature rows     : "
        f"{verification['market_feature_rows']}"
    )

    print(
        f"Market feature snapshots: "
        f"{verification['market_feature_snapshots']}"
    )

    print(
        f"Option feature rows     : "
        f"{verification['option_feature_rows']}"
    )

    print(
        f"Option feature snapshots: "
        f"{verification['option_feature_snapshots']}"
    )

    # ========================================================
    # INTEGRITY VERIFICATION
    # ========================================================

    integrity = (
        verify_feature_integrity()
    )

    print()

    print(
        "FEATURE INTEGRITY"
    )

    print("-" * 70)

    print(
        f"Market duplicates       : "
        f"{integrity['market_duplicates']}"
    )

    print(
        f"Option duplicates       : "
        f"{integrity['option_duplicates']}"
    )

    print(
        f"Orphan option features   : "
        f"{integrity['orphan_option_features']}"
    )

    print(
        f"Missing option features  : "
        f"{integrity['missing_option_features']}"
    )

    print(
        f"Incomplete feature snaps: "
        f"{integrity['incomplete_feature_snapshots']}"
    )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    if (
        integrity["market_duplicates"] == 0
        and
        integrity["option_duplicates"] == 0
        and
        integrity[
            "incomplete_feature_snapshots"
        ] == 0
    ):

        print()

        print(
            "FEATURE BUILD STATUS : PASS"
        )

    else:

        print()

        print(
            "FEATURE BUILD STATUS : WARNING"
        )

    print()

    print("=" * 70)