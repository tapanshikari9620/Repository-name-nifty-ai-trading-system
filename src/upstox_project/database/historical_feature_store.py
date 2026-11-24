
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3

from datetime import datetime, timezone


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = str(MARKET_DATABASE_PATH)


# ============================================================
# CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_NAME
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# INITIALIZE FEATURE TABLES
# ============================================================

def initialize_feature_tables():

    connection = get_connection()

    cursor = connection.cursor()

    # ========================================================
    # MARKET FEATURES
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS market_features (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            market_snapshot_id INTEGER NOT NULL,

            timestamp_utc TEXT NOT NULL,

            spot_price REAL NOT NULL,

            atm_strike REAL,

            support REAL,

            resistance REAL,

            total_ce_oi REAL,

            total_pe_oi REAL,

            pcr REAL,

            total_ce_oi_change REAL,

            total_pe_oi_change REAL,

            oi_pressure REAL,

            total_ce_volume REAL,

            total_pe_volume REAL,

            volume_pressure REAL,

            highest_ce_oi REAL,

            highest_pe_oi REAL,

            highest_ce_oi_change REAL,

            highest_pe_oi_change REAL,

            created_at_utc TEXT NOT NULL,

            UNIQUE(market_snapshot_id)

        )
        """
    )

    # ========================================================
    # OPTION FEATURES
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS option_features (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            market_snapshot_id INTEGER NOT NULL,

            timestamp_utc TEXT NOT NULL,

            expiry TEXT NOT NULL,

            strike REAL NOT NULL,

            option_type TEXT NOT NULL,

            ltp REAL,

            close_price REAL,

            volume REAL,

            oi REAL,

            prev_oi REAL,

            oi_change REAL,

            bid_price REAL,

            bid_qty REAL,

            ask_price REAL,

            ask_qty REAL,

            iv REAL,

            delta REAL,

            gamma REAL,

            theta REAL,

            vega REAL,

            pop REAL,

            created_at_utc TEXT NOT NULL,

            UNIQUE(
                market_snapshot_id,
                expiry,
                strike,
                option_type
            )

        )
        """
    )

    # ========================================================
    # INDEXES
    # ========================================================

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_market_features_timestamp

        ON market_features(timestamp_utc)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_option_features_timestamp

        ON option_features(timestamp_utc)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_option_features_contract

        ON option_features(
            expiry,
            strike,
            option_type
        )
        """
    )

    connection.commit()

    connection.close()


# ============================================================
# STORE MARKET FEATURES
# ============================================================

def store_market_features(
    features
):

    required_fields = [
        "market_snapshot_id",
        "timestamp_utc",
        "spot_price"
    ]

    for field in required_fields:

        if field not in features:

            raise ValueError(
                f"Missing required field: {field}"
            )

    initialize_feature_tables()

    connection = get_connection()

    cursor = connection.cursor()

    created_at_utc = (
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

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

            features.get(
                "atm_strike"
            ),

            features.get(
                "support"
            ),

            features.get(
                "resistance"
            ),

            features.get(
                "total_ce_oi"
            ),

            features.get(
                "total_pe_oi"
            ),

            features.get(
                "pcr"
            ),

            features.get(
                "total_ce_oi_change"
            ),

            features.get(
                "total_pe_oi_change"
            ),

            features.get(
                "oi_pressure"
            ),

            features.get(
                "total_ce_volume"
            ),

            features.get(
                "total_pe_volume"
            ),

            features.get(
                "volume_pressure"
            ),

            features.get(
                "highest_ce_oi"
            ),

            features.get(
                "highest_pe_oi"
            ),

            features.get(
                "highest_ce_oi_change"
            ),

            features.get(
                "highest_pe_oi_change"
            ),

            created_at_utc
        )
    )

    connection.commit()

    feature_id = (
        cursor.lastrowid
    )

    connection.close()

    return feature_id


# ============================================================
# STORE OPTION FEATURES
# ============================================================

def store_option_features(
    features
):

    required_fields = [
        "market_snapshot_id",
        "timestamp_utc",
        "expiry",
        "strike",
        "option_type"
    ]

    for field in required_fields:

        if field not in features:

            raise ValueError(
                f"Missing required field: {field}"
            )

    initialize_feature_tables()

    connection = get_connection()

    cursor = connection.cursor()

    created_at_utc = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

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

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,

        (
            features[
                "market_snapshot_id"
            ],

            features[
                "timestamp_utc"
            ],

            features[
                "expiry"
            ],

            features[
                "strike"
            ],

            features[
                "option_type"
            ],

            features.get(
                "ltp"
            ),

            features.get(
                "close_price"
            ),

            features.get(
                "volume"
            ),

            features.get(
                "oi"
            ),

            features.get(
                "prev_oi"
            ),

            features.get(
                "oi_change"
            ),

            features.get(
                "bid_price"
            ),

            features.get(
                "bid_qty"
            ),

            features.get(
                "ask_price"
            ),

            features.get(
                "ask_qty"
            ),

            features.get(
                "iv"
            ),

            features.get(
                "delta"
            ),

            features.get(
                "gamma"
            ),

            features.get(
                "theta"
            ),

            features.get(
                "vega"
            ),

            features.get(
                "pop"
            ),

            created_at_utc
        )
    )

    connection.commit()

    feature_id = (
        cursor.lastrowid
    )

    connection.close()

    return feature_id


# ============================================================
# COUNT MARKET FEATURES
# ============================================================

def count_market_features():

    initialize_feature_tables()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM market_features
        """
    )

    count = cursor.fetchone()[0]

    connection.close()

    return count


# ============================================================
# COUNT OPTION FEATURES
# ============================================================

def count_option_features():

    initialize_feature_tables()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM option_features
        """
    )

    count = cursor.fetchone()[0]

    connection.close()

    return count


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "HISTORICAL FEATURE STORE"
    )

    print("=" * 70)

    initialize_feature_tables()

    print()

    print(
        "Feature tables initialized."
    )

    print()

    print(
        f"Market feature records : "
        f"{count_market_features()}"
    )

    print(
        f"Option feature records : "
        f"{count_option_features()}"
    )

    print()

    print(
        "Available functions:"
    )

    print(
        "- initialize_feature_tables()"
    )

    print(
        "- store_market_features()"
    )

    print(
        "- store_option_features()"
    )

    print(
        "- count_market_features()"
    )

    print(
        "- count_option_features()"
    )

    print()

    print("=" * 70)