# ============================================================
# MARKET SNAPSHOT STORE
# ============================================================
#
# Stores timestamped NIFTY spot prices.
#
# The Outcome Engine will use this database to determine
# the actual NIFTY price at future horizons:
#
#     +5 minutes
#     +15 minutes
#     +30 minutes
#     +60 minutes
#
# Accuracy rule:
#
# We NEVER use an old snapshot for a future target time.
#
# get_price_at_or_after() only accepts a snapshot that occurs
# AFTER the target time and within the allowed delay.
#
# ============================================================

import sqlite3

from datetime import datetime, timezone


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATABASE_NAME = "nifty_market_data.db"


# ============================================================
# CONNECTION
# ============================================================

def get_connection():
    """
    Create and return a SQLite database connection.
    """

    connection = sqlite3.connect(
        DATABASE_NAME
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# TIMESTAMP VALIDATION
# ============================================================

def parse_timestamp(timestamp):
    """
    Convert an ISO timestamp into a timezone-aware datetime.

    Example:

        2026-08-12T11:03:35.328474+00:00
    """

    if not timestamp:

        raise ValueError(
            "Timestamp cannot be empty."
        )

    try:

        parsed = datetime.fromisoformat(
            timestamp
        )

    except ValueError as error:

        raise ValueError(
            f"Invalid timestamp: {timestamp}"
        ) from error

    # --------------------------------------------------------
    # Require timezone-aware timestamps
    # --------------------------------------------------------

    if parsed.tzinfo is None:

        raise ValueError(
            "Timestamp must contain timezone information."
        )

    return parsed


# ============================================================
# INITIALIZE TABLE
# ============================================================

def initialize_snapshot_table():
    """
    Create the market snapshot table if it does not exist.
    """

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshots (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            timestamp_utc TEXT NOT NULL,

            spot_price REAL NOT NULL

        )
        """
    )

    # --------------------------------------------------------
    # Index for timestamp-based lookup
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_market_snapshot_timestamp

        ON market_snapshots(timestamp_utc)
        """
    )

    connection.commit()

    connection.close()


# ============================================================
# STORE SNAPSHOT
# ============================================================

def store_snapshot(
    spot_price,
    timestamp_utc=None
):
    """
    Store one NIFTY spot observation.

    If timestamp_utc is not supplied, the current UTC time
    will be used.
    """

    # --------------------------------------------------------
    # Validate price
    # --------------------------------------------------------

    if spot_price is None:

        raise ValueError(
            "Spot price cannot be None."
        )

    try:

        spot_price = float(
            spot_price
        )

    except (
        TypeError,
        ValueError
    ) as error:

        raise ValueError(
            "Invalid spot price."
        ) from error

    if spot_price <= 0:

        raise ValueError(
            "Spot price must be greater than zero."
        )

    # --------------------------------------------------------
    # Generate timestamp if required
    # --------------------------------------------------------

    if timestamp_utc is None:

        timestamp_utc = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

    else:

        # Validate supplied timestamp
        parse_timestamp(
            timestamp_utc
        )

    # --------------------------------------------------------
    # Initialize database
    # --------------------------------------------------------

    initialize_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    # --------------------------------------------------------
    # Insert snapshot
    # --------------------------------------------------------

    cursor.execute(
        """
        INSERT INTO market_snapshots (
            timestamp_utc,
            spot_price
        )

        VALUES (?, ?)
        """,

        (
            timestamp_utc,
            spot_price
        )
    )

    connection.commit()

    snapshot_id = cursor.lastrowid

    connection.close()

    return snapshot_id


# ============================================================
# GET PRICE NEAREST TO TARGET TIME
# ============================================================

def get_nearest_price(
    target_timestamp
):
    """
    Return the snapshot closest to the requested timestamp.

    IMPORTANT:
    This function is mainly useful for diagnostic/testing
    purposes.

    For actual outcome calculation, use:

        get_price_at_or_after()

    because future outcome measurement should not accidentally
    use a snapshot from before the target time.
    """

    target_time = parse_timestamp(
        target_timestamp
    )

    initialize_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            timestamp_utc,
            spot_price

        FROM market_snapshots
        """
    )

    rows = cursor.fetchall()

    connection.close()

    if not rows:

        return None

    closest_row = None

    closest_difference = None

    # --------------------------------------------------------
    # Find mathematically closest snapshot
    # --------------------------------------------------------

    for row in rows:

        snapshot_time = parse_timestamp(
            row["timestamp_utc"]
        )

        difference = abs(
            (
                snapshot_time -
                target_time
            ).total_seconds()
        )

        if (
            closest_difference is None
            or
            difference < closest_difference
        ):

            closest_difference = (
                difference
            )

            closest_row = row

    if closest_row is None:

        return None

    return {

        "timestamp_utc":
            closest_row["timestamp_utc"],

        "spot_price":
            closest_row["spot_price"],

        "difference_seconds":
            closest_difference

    }


# ============================================================
# GET PRICE AT OR AFTER TARGET TIME
# ============================================================

def get_price_at_or_after(
    target_timestamp,
    max_delay_seconds=30
):
    """
    Find the first market snapshot at or after the target time.

    Example:

        Target:
            11:05:00

        Snapshots:
            11:04:50  -> ignored
            11:05:08  -> accepted
            11:05:40  -> not needed

    The accepted snapshot must not be more than
    max_delay_seconds after the target.

    Returns:

        {
            "timestamp_utc": "...",
            "spot_price": 24435.95,
            "delay_seconds": 8.0
        }

    Returns None when a valid snapshot is unavailable.
    """

    # --------------------------------------------------------
    # Validate target timestamp
    # --------------------------------------------------------

    target_time = parse_timestamp(
        target_timestamp
    )

    # --------------------------------------------------------
    # Validate delay
    # --------------------------------------------------------

    if max_delay_seconds < 0:

        raise ValueError(
            "max_delay_seconds cannot be negative."
        )

    initialize_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    # --------------------------------------------------------
    # Get snapshots at or after target
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            timestamp_utc,
            spot_price

        FROM market_snapshots

        WHERE timestamp_utc >= ?

        ORDER BY timestamp_utc ASC
        """,

        (
            target_timestamp,
        )
    )

    rows = cursor.fetchall()

    connection.close()

    if not rows:

        return None

    # --------------------------------------------------------
    # Find first valid snapshot
    # --------------------------------------------------------

    for row in rows:

        snapshot_time = parse_timestamp(
            row["timestamp_utc"]
        )

        delay_seconds = (
            snapshot_time -
            target_time
        ).total_seconds()

        # Safety check
        if delay_seconds < 0:

            continue

        # ----------------------------------------------------
        # Reject snapshot if too late
        # ----------------------------------------------------

        if (
            delay_seconds >
            max_delay_seconds
        ):

            return None

        return {

            "timestamp_utc":
                row["timestamp_utc"],

            "spot_price":
                row["spot_price"],

            "delay_seconds":
                delay_seconds

        }

    return None


# ============================================================
# COUNT SNAPSHOTS
# ============================================================

def count_snapshots():
    """
    Return total number of stored market snapshots.
    """

    initialize_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM market_snapshots
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

    print(
        "=" * 70
    )

    print(
        "MARKET SNAPSHOT STORE"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Initialize database
    # --------------------------------------------------------

    initialize_snapshot_table()

    print()

    print(
        "Market snapshot table initialized."
    )

    # --------------------------------------------------------
    # Snapshot count
    # --------------------------------------------------------

    print()

    print(
        f"Stored snapshots : "
        f"{count_snapshots()}"
    )

    # --------------------------------------------------------
    # Available functions
    # --------------------------------------------------------

    print()

    print(
        "Available functions:"
    )

    print(
        "- get_connection()"
    )

    print(
        "- parse_timestamp()"
    )

    print(
        "- initialize_snapshot_table()"
    )

    print(
        "- store_snapshot()"
    )

    print(
        "- get_nearest_price()"
    )

    print(
        "- get_price_at_or_after()"
    )

    print(
        "- count_snapshots()"
    )

    print()

    print(
        "=" * 70
    )