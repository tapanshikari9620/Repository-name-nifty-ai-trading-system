# ============================================================
# SIGNAL LOGGER
# ============================================================
#
# Purpose:
#
# Persist every generated market signal and its feature
# snapshot into a local SQLite database.
#
# IMPORTANT:
#
# This module DOES NOT:
#
# - place orders
# - modify signals
# - predict future prices
# - calculate trading performance
#
# It only records observations.
#
# This is the foundation for:
#
#     Backtesting
#     Statistical validation
#     Feature analysis
#     ML training
#
# ============================================================

import json
import sqlite3
import uuid

from datetime import datetime, timezone


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATABASE_NAME = "nifty_signal_history.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    """
    Create a connection to the SQLite database.
    """

    connection = sqlite3.connect(
        DATABASE_NAME
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():
    """
    Create required database tables if they do not exist.
    """

    connection = get_connection()

    cursor = connection.cursor()

    # --------------------------------------------------------
    # SIGNAL SNAPSHOT TABLE
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_snapshots (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            signal_id TEXT UNIQUE NOT NULL,

            timestamp_utc TEXT NOT NULL,

            instrument TEXT NOT NULL,

            expiry_date TEXT,

            spot_price REAL NOT NULL,

            atm_strike REAL NOT NULL,

            support REAL,

            resistance REAL,

            pcr REAL,

            total_ce_oi REAL,

            total_pe_oi REAL,

            total_ce_oi_change REAL,

            total_pe_oi_change REAL,

            oi_pressure REAL,

            total_ce_volume REAL,

            total_pe_volume REAL,

            volume_pressure REAL,

            market_structure TEXT,

            bullish_score REAL,

            bearish_score REAL,

            net_score REAL,

            confidence REAL,

            bias TEXT,

            action TEXT,

            bullish_evidence INTEGER,

            bearish_evidence INTEGER,

            neutral_evidence INTEGER,

            total_evidence INTEGER,

            evidence_json TEXT,

            features_json TEXT,

            raw_chain_json TEXT,

            outcome_5m REAL,

            outcome_15m REAL,

            outcome_30m REAL,

            outcome_60m REAL,

            max_favorable_move REAL,

            max_adverse_move REAL,

            outcome_status TEXT DEFAULT 'PENDING'

        )
        """
    )

    # --------------------------------------------------------
    # INDEXES
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_signal_timestamp
        ON signal_snapshots(timestamp_utc)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_signal_bias
        ON signal_snapshots(bias)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_signal_action
        ON signal_snapshots(action)
        """
    )

    connection.commit()

    connection.close()


# ============================================================
# SAFE NUMBER
# ============================================================

def safe_number(value):
    """
    Convert a value safely into float.
    """

    if value is None:

        return None

    try:

        return float(value)

    except (TypeError, ValueError):

        return None


# ============================================================
# SAFE JSON
# ============================================================

def serialize_json(data):
    """
    Convert Python data into JSON safely.
    """

    try:

        return json.dumps(
            data,
            separators=(",", ":"),
            default=str
        )

    except (TypeError, ValueError):

        return "{}"


# ============================================================
# EXTRACT SUPPORT
# ============================================================

def extract_support(analysis):
    """
    Extract support strike regardless of whether the analyzer
    returns a dictionary or a numeric value.
    """

    support = analysis.get(
        "support"
    )

    if isinstance(
        support,
        dict
    ):

        return safe_number(
            support.get("strike")
        )

    return safe_number(
        support
    )


# ============================================================
# EXTRACT RESISTANCE
# ============================================================

def extract_resistance(analysis):
    """
    Extract resistance strike.
    """

    resistance = analysis.get(
        "resistance"
    )

    if isinstance(
        resistance,
        dict
    ):

        return safe_number(
            resistance.get("strike")
        )

    return safe_number(
        resistance
    )


# ============================================================
# LOG SIGNAL
# ============================================================

def log_signal(
    spot_price,
    atm_strike,
    analysis,
    evidence,
    signal,
    option_features=None,
    raw_option_chain=None,
    instrument="NSE_INDEX|Nifty 50",
    expiry_date=None
):
    """
    Store one complete signal observation.

    Returns:
        signal_id
    """

    initialize_database()

    signal_id = str(
        uuid.uuid4()
    )

    timestamp_utc = (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )

    connection = get_connection()

    cursor = connection.cursor()

    # --------------------------------------------------------
    # Extract analysis values
    # --------------------------------------------------------

    total_ce_oi = safe_number(
        analysis.get(
            "total_ce_oi"
        )
    )

    total_pe_oi = safe_number(
        analysis.get(
            "total_pe_oi"
        )
    )

    total_ce_oi_change = safe_number(
        analysis.get(
            "total_ce_oi_change"
        )
    )

    total_pe_oi_change = safe_number(
        analysis.get(
            "total_pe_oi_change"
        )
    )

    oi_pressure = safe_number(
        analysis.get(
            "oi_pressure"
        )
    )

    total_ce_volume = safe_number(
        analysis.get(
            "total_ce_volume"
        )
    )

    total_pe_volume = safe_number(
        analysis.get(
            "total_pe_volume"
        )
    )

    volume_pressure = safe_number(
        analysis.get(
            "volume_pressure"
        )
    )

    pcr = safe_number(
        analysis.get(
            "pcr"
        )
    )

    market_structure = analysis.get(
        "market_structure"
    )

    # --------------------------------------------------------
    # Extract signal values
    # --------------------------------------------------------

    bullish_score = safe_number(
        signal.get(
            "bullish_score"
        )
    )

    bearish_score = safe_number(
        signal.get(
            "bearish_score"
        )
    )

    net_score = safe_number(
        signal.get(
            "net_score"
        )
    )

    confidence = safe_number(
        signal.get(
            "confidence"
        )
    )

    bias = signal.get(
        "bias"
    )

    action = signal.get(
        "action"
    )

    bullish_evidence = signal.get(
        "bullish_evidence",
        0
    )

    bearish_evidence = signal.get(
        "bearish_evidence",
        0
    )

    neutral_evidence = signal.get(
        "neutral_evidence",
        0
    )

    total_evidence = signal.get(
        "total_evidence",
        0
    )

    # --------------------------------------------------------
    # Insert snapshot
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO signal_snapshots (

            signal_id,
            timestamp_utc,
            instrument,
            expiry_date,

            spot_price,
            atm_strike,

            support,
            resistance,

            pcr,

            total_ce_oi,
            total_pe_oi,

            total_ce_oi_change,
            total_pe_oi_change,

            oi_pressure,

            total_ce_volume,
            total_pe_volume,

            volume_pressure,

            market_structure,

            bullish_score,
            bearish_score,
            net_score,

            confidence,

            bias,
            action,

            bullish_evidence,
            bearish_evidence,
            neutral_evidence,
            total_evidence,

            evidence_json,
            features_json,
            raw_chain_json

        )

        VALUES (

            ?, ?, ?, ?,

            ?, ?,

            ?, ?,

            ?,

            ?, ?,

            ?, ?,

            ?,

            ?, ?,

            ?,

            ?,

            ?, ?, ?,

            ?,

            ?, ?,

            ?, ?, ?, ?,

            ?, ?, ?

        )
        """,

        (

            signal_id,
            timestamp_utc,
            instrument,
            expiry_date,

            safe_number(spot_price),
            safe_number(atm_strike),

            extract_support(
                analysis
            ),

            extract_resistance(
                analysis
            ),

            pcr,

            total_ce_oi,
            total_pe_oi,

            total_ce_oi_change,
            total_pe_oi_change,

            oi_pressure,

            total_ce_volume,
            total_pe_volume,

            volume_pressure,

            market_structure,

            bullish_score,
            bearish_score,
            net_score,

            confidence,

            bias,
            action,

            bullish_evidence,
            bearish_evidence,
            neutral_evidence,
            total_evidence,

            serialize_json(
                evidence
            ),

            serialize_json(
                option_features
            ),

            serialize_json(
                raw_option_chain
            )
        )
    )

    connection.commit()

    connection.close()

    return signal_id


# ============================================================
# UPDATE OUTCOME
# ============================================================

# ============================================================
# UPDATE OUTCOME
# ============================================================

def update_outcome(
    signal_id,
    outcome_5m=None,
    outcome_15m=None,
    outcome_30m=None,
    outcome_60m=None,
    max_favorable_move=None,
    max_adverse_move=None,
    status=None
):
    """
    Safely update future outcomes for an existing signal.

    Existing values are preserved when a new value is None.
    """

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE signal_snapshots

        SET

            outcome_5m =
                COALESCE(?, outcome_5m),

            outcome_15m =
                COALESCE(?, outcome_15m),

            outcome_30m =
                COALESCE(?, outcome_30m),

            outcome_60m =
                COALESCE(?, outcome_60m),

            max_favorable_move =
                COALESCE(?, max_favorable_move),

            max_adverse_move =
                COALESCE(?, max_adverse_move),

            outcome_status =
                COALESCE(?, outcome_status)

        WHERE signal_id = ?

        """,

        (

            safe_number(
                outcome_5m
            ),

            safe_number(
                outcome_15m
            ),

            safe_number(
                outcome_30m
            ),

            safe_number(
                outcome_60m
            ),

            safe_number(
                max_favorable_move
            ),

            safe_number(
                max_adverse_move
            ),

            status,

            signal_id
        )
    )

    connection.commit()

    rows_updated = cursor.rowcount

    connection.close()

    return rows_updated


# ============================================================
# GET PENDING SIGNALS
# ============================================================

def get_pending_signals():
    """
    Return signals whose future outcomes have not yet been
    completed.
    """

    initialize_database()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *

        FROM signal_snapshots

        WHERE outcome_status = 'PENDING'

        ORDER BY timestamp_utc ASC
        """
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


# ============================================================
# COUNT SIGNALS
# ============================================================

def count_signals():
    """
    Return total number of stored signals.
    """

    initialize_database()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM signal_snapshots
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
    print("SIGNAL LOGGER")
    print("=" * 70)

    initialize_database()

    print()
    print(
        "Signal logger initialized successfully."
    )

    print()
    print(
        f"Database : {DATABASE_NAME}"
    )

    print(
        f"Stored signals : {count_signals()}"
    )

    print()
    print("Available functions:")

    print(
        "- initialize_database()"
    )

    print(
        "- log_signal()"
    )

    print(
        "- update_outcome()"
    )

    print(
        "- get_pending_signals()"
    )

    print(
        "- count_signals()"
    )

    print()
    print("=" * 70)