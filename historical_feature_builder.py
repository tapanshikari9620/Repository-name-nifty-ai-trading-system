import sqlite3
import math

from datetime import datetime, timezone


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = "nifty_market_data.db"

EXPECTED_OPTIONS_PER_SNAPSHOT = 210

EXPECTED_CE_RECORDS = 105

EXPECTED_PE_RECORDS = 105

MAX_CONTINUITY_GAP_SECONDS = 90.0


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_NAME
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

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

def load_snapshot_data():

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

    market_rows = cursor.fetchall()

    snapshots = []

    for market_row in market_rows:

        snapshot_id = market_row["id"]

        cursor.execute(
            """
            SELECT *

            FROM option_snapshots

            WHERE market_snapshot_id = ?

            ORDER BY
                strike ASC,
                option_type ASC
            """,
            (
                snapshot_id,
            )
        )

        option_rows = cursor.fetchall()

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

        # ----------------------------------------------------
        # Expiry validation
        # ----------------------------------------------------

        expiries = {
            row["expiry"]
            for row in option_rows
            if row["expiry"]
        }

        # ----------------------------------------------------
        # Contract uniqueness
        # ----------------------------------------------------

        contracts = set()

        duplicate_contract = False

        for row in option_rows:

            contract_key = (
                row["expiry"],
                safe_number(
                    row["strike"]
                ),
                row["option_type"]
            )

            if contract_key in contracts:

                duplicate_contract = True

                break

            contracts.add(
                contract_key
            )

        # ----------------------------------------------------
        # CE / PE strike pairing
        # ----------------------------------------------------

        ce_strikes = {
            safe_number(
                row["strike"]
            )
            for row in ce_rows
        }

        pe_strikes = {
            safe_number(
                row["strike"]
            )
            for row in pe_rows
        }

        paired_strikes = (
            ce_strikes == pe_strikes
        )

        # ----------------------------------------------------
        # Completeness
        # ----------------------------------------------------

        complete = (

            len(option_rows)
            == EXPECTED_OPTIONS_PER_SNAPSHOT

            and len(ce_rows)
            == EXPECTED_CE_RECORDS

            and len(pe_rows)
            == EXPECTED_PE_RECORDS

            and len(expiries) == 1

            and timestamp is not None

            and not duplicate_contract

            and paired_strikes
        )

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
                    safe_number(
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

                "complete":
                    complete
            }
        )

    connection.close()

    return snapshots


# ============================================================
# LOAD COLLECTION HEALTH
# ============================================================

def load_collection_health():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            market_snapshot_id,
            status,
            validation_status

        FROM collection_health

        WHERE market_snapshot_id IS NOT NULL
        """
    )

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
    snapshots
):

    previous_valid_snapshot = None

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

        pcr = 0.0

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
    features
):

    connection = get_connection()

    cursor = connection.cursor()

    created_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    cursor.execute(
        """
        INSERT OR REPLACE INTO market_features (

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

    connection.commit()

    connection.close()


# ============================================================
# STORE OPTION FEATURE ROWS
# ============================================================

def store_option_feature_rows(
    snapshot
):

    connection = get_connection()

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
                INSERT OR REPLACE INTO option_features (

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

        connection.commit()

        return inserted

    except Exception:

        connection.rollback()

        raise

    finally:

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

def build_historical_features():

    snapshots = load_snapshot_data()

    health = load_collection_health()

    if not snapshots:

        raise RuntimeError(
            "No market snapshots found."
        )

    calculate_continuity(
        snapshots
    )

    total_snapshots = len(
        snapshots
    )

    complete_snapshots = 0

    skipped_incomplete = 0

    skipped_unhealthy = 0

    continuous_snapshots = 0

    non_continuous_snapshots = 0

    market_features_before = (
        get_feature_count(
            "market_features"
        )
    )

    option_features_before = (
        get_feature_count(
            "option_features"
        )
    )

    for snapshot in snapshots:

        snapshot_id = (
            snapshot[
                "market_snapshot_id"
            ]
        )

        # ====================================================
        # COMPLETENESS
        # ====================================================

        if not snapshot[
            "complete"
        ]:

            skipped_incomplete += 1

            continue

        # ====================================================
        # COLLECTION HEALTH
        # ====================================================

        if not is_snapshot_health_valid(
            snapshot_id,
            health
        ):

            skipped_unhealthy += 1

            continue

        complete_snapshots += 1

        # ====================================================
        # CONTINUITY
        # ====================================================

        if snapshot[
            "continuous"
        ]:

            continuous_snapshots += 1

        else:

            non_continuous_snapshots += 1

        # ====================================================
        # CALCULATE MARKET FEATURES
        # ====================================================

        market_features = (
            calculate_market_features(
                snapshot
            )
        )

        # ====================================================
        # STORE MARKET FEATURES
        # ====================================================

        store_market_feature_row(
            market_features
        )

        # ====================================================
        # STORE OPTION FEATURES
        # ====================================================

        store_option_feature_rows(
            snapshot
        )

    market_features_after = (
        get_feature_count(
            "market_features"
        )
    )

    option_features_after = (
        get_feature_count(
            "option_features"
        )
    )

    return {

        "total_snapshots":
            total_snapshots,

        "complete_snapshots":
            complete_snapshots,

        "skipped_incomplete":
            skipped_incomplete,

        "skipped_unhealthy":
            skipped_unhealthy,

        "continuous_snapshots":
            continuous_snapshots,

        "non_continuous_snapshots":
            non_continuous_snapshots,

        "market_features_created":
            (
                market_features_after
                - market_features_before
            ),

        "option_features_created":
            (
                option_features_after
                - option_features_before
            ),

        "market_feature_total":
            market_features_after,

        "option_feature_total":
            option_features_after
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

    cursor = connection.cursor()

    # --------------------------------------------------------
    # Market feature duplicates
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            market_snapshot_id,
            COUNT(*)

        FROM market_features

        GROUP BY
            market_snapshot_id

        HAVING COUNT(*) > 1
        """
    )

    market_duplicates = (
        cursor.fetchall()
    )

    # --------------------------------------------------------
    # Option feature duplicates
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            market_snapshot_id,
            expiry,
            strike,
            option_type,
            COUNT(*)

        FROM option_features

        GROUP BY
            market_snapshot_id,
            expiry,
            strike,
            option_type

        HAVING COUNT(*) > 1
        """
    )

    option_duplicates = (
        cursor.fetchall()
    )

    # --------------------------------------------------------
    # Option record count per snapshot
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            market_snapshot_id,
            COUNT(*)

        FROM option_features

        GROUP BY
            market_snapshot_id

        HAVING COUNT(*) != ?
        """,
        (
            EXPECTED_OPTIONS_PER_SNAPSHOT,
        )
    )

    incomplete_feature_snapshots = (
        cursor.fetchall()
    )

    connection.close()

    return {

        "market_duplicates":
            len(market_duplicates),

        "option_duplicates":
            len(option_duplicates),

        "incomplete_feature_snapshots":
            len(
                incomplete_feature_snapshots
            )
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
        f"Complete snapshots      : "
        f"{result['complete_snapshots']}"
    )

    print(
        f"Skipped incomplete      : "
        f"{result['skipped_incomplete']}"
    )

    print(
        f"Skipped unhealthy       : "
        f"{result['skipped_unhealthy']}"
    )

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