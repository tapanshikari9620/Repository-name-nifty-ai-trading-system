import sqlite3
from datetime import datetime, timezone


DATABASE_NAME = "nifty_market_data.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_NAME
    )

    connection.row_factory = sqlite3.Row

    # Enable foreign-key enforcement
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# ============================================================
# INITIALIZE OPTION SNAPSHOT TABLE
# ============================================================

def initialize_option_snapshot_table():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS option_snapshots (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            market_snapshot_id INTEGER NOT NULL,

            timestamp_utc TEXT NOT NULL,

            expiry TEXT NOT NULL,

            strike REAL NOT NULL,

            option_type TEXT NOT NULL,

            instrument_key TEXT,

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

            FOREIGN KEY (
                market_snapshot_id
            )
            REFERENCES market_snapshots(id)

            ON DELETE CASCADE

        )
        """
    )

    # --------------------------------------------------------
    # Indexes
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_option_snapshot_timestamp

        ON option_snapshots(timestamp_utc)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_option_snapshot_market_id

        ON option_snapshots(
            market_snapshot_id
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_option_snapshot_strike

        ON option_snapshots(
            expiry,
            strike,
            option_type
        )
        """
    )

    # --------------------------------------------------------
    # Prevent duplicate option records for the same
    # market snapshot + contract.
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_option_snapshot_unique_contract

        ON option_snapshots(
            market_snapshot_id,
            instrument_key
        )
        """
    )

    connection.commit()

    connection.close()


# ============================================================
# SAFE NUMBER
# ============================================================

def safe_number(value):

    if value is None:

        return None

    try:

        return float(value)

    except (
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# EXTRACT OPTION DATA
# ============================================================

def extract_option_data(
    option,
    option_type
):
    """
    Convert one Upstox CE/PE option object into
    a normalized database record.
    """

    if option_type not in (
        "CE",
        "PE"
    ):

        raise ValueError(
            "option_type must be CE or PE."
        )

    market_data = option.get(
        "market_data",
        {}
    ) or {}

    greeks = option.get(
        "option_greeks",
        {}
    ) or {}

    strike = safe_number(
        option.get(
            "_strike_price"
        )
    )

    expiry = option.get(
        "_expiry"
    )

    instrument_key = option.get(
        "instrument_key"
    )

    ltp = safe_number(
        market_data.get(
            "ltp"
        )
    )

    close_price = safe_number(
        market_data.get(
            "close_price"
        )
    )

    volume = safe_number(
        market_data.get(
            "volume"
        )
    )

    oi = safe_number(
        market_data.get(
            "oi"
        )
    )

    prev_oi = safe_number(
        market_data.get(
            "prev_oi"
        )
    )

    bid_price = safe_number(
        market_data.get(
            "bid_price"
        )
    )

    bid_qty = safe_number(
        market_data.get(
            "bid_qty"
        )
    )

    ask_price = safe_number(
        market_data.get(
            "ask_price"
        )
    )

    ask_qty = safe_number(
        market_data.get(
            "ask_qty"
        )
    )

    iv = safe_number(
        greeks.get(
            "iv"
        )
    )

    delta = safe_number(
        greeks.get(
            "delta"
        )
    )

    gamma = safe_number(
        greeks.get(
            "gamma"
        )
    )

    theta = safe_number(
        greeks.get(
            "theta"
        )
    )

    vega = safe_number(
        greeks.get(
            "vega"
        )
    )

    pop = safe_number(
        greeks.get(
            "pop"
        )
    )

    # --------------------------------------------------------
    # OI CHANGE
    # --------------------------------------------------------

    oi_change = None

    if (
        oi is not None
        and prev_oi is not None
    ):

        oi_change = (
            oi - prev_oi
        )

    return {

        "strike":
            strike,

        "expiry":
            expiry,

        "option_type":
            option_type,

        "instrument_key":
            instrument_key,

        "ltp":
            ltp,

        "close_price":
            close_price,

        "volume":
            volume,

        "oi":
            oi,

        "prev_oi":
            prev_oi,

        "oi_change":
            oi_change,

        "bid_price":
            bid_price,

        "bid_qty":
            bid_qty,

        "ask_price":
            ask_price,

        "ask_qty":
            ask_qty,

        "iv":
            iv,

        "delta":
            delta,

        "gamma":
            gamma,

        "theta":
            theta,

        "vega":
            vega,

        "pop":
            pop

    }


# ============================================================
# STORE OPTION SNAPSHOT
# ============================================================

def store_option_snapshot(
    market_snapshot_id,
    timestamp_utc,
    option_chain
):
    """
    Store the complete option chain associated with
    one market snapshot.
    """

    if market_snapshot_id is None:

        raise ValueError(
            "market_snapshot_id cannot be None."
        )

    if not timestamp_utc:

        raise ValueError(
            "timestamp_utc cannot be empty."
        )

    if not option_chain:

        raise ValueError(
            "Option chain cannot be empty."
        )

    initialize_option_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    created_at_utc = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    records = []

    for option in option_chain:

        strike = safe_number(
            option.get(
                "strike_price"
            )
        )

        expiry = option.get(
            "expiry"
        )

        if strike is None:

            raise ValueError(
                "Option chain contains "
                "an invalid strike."
            )

        if not expiry:

            raise ValueError(
                "Option chain contains "
                "an invalid expiry."
            )

        # ----------------------------------------------------
        # CALL
        # ----------------------------------------------------

        call_option = (
            option.get(
                "call_options"
            )
            or {}
        )

        if call_option:

            call_record = dict(
                call_option
            )

            call_record[
                "_strike_price"
            ] = strike

            call_record[
                "_expiry"
            ] = expiry

            records.append(
                extract_option_data(
                    call_record,
                    "CE"
                )
            )

        # ----------------------------------------------------
        # PUT
        # ----------------------------------------------------

        put_option = (
            option.get(
                "put_options"
            )
            or {}
        )

        if put_option:

            put_record = dict(
                put_option
            )

            put_record[
                "_strike_price"
            ] = strike

            put_record[
                "_expiry"
            ] = expiry

            records.append(
                extract_option_data(
                    put_record,
                    "PE"
                )
            )

    if not records:

        connection.close()

        raise ValueError(
            "No CE/PE option records found."
        )

    try:

        cursor.executemany(
            """
            INSERT INTO option_snapshots (

                market_snapshot_id,
                timestamp_utc,
                expiry,
                strike,
                option_type,
                instrument_key,
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

                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?

            )
            """,

            [

                (
                    market_snapshot_id,

                    timestamp_utc,

                    record["expiry"],

                    record["strike"],

                    record["option_type"],

                    record["instrument_key"],

                    record["ltp"],

                    record["close_price"],

                    record["volume"],

                    record["oi"],

                    record["prev_oi"],

                    record["oi_change"],

                    record["bid_price"],

                    record["bid_qty"],

                    record["ask_price"],

                    record["ask_qty"],

                    record["iv"],

                    record["delta"],

                    record["gamma"],

                    record["theta"],

                    record["vega"],

                    record["pop"],

                    created_at_utc

                )

                for record in records

            ]

        )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()

    return len(records)


# ============================================================
# COUNT OPTION SNAPSHOTS
# ============================================================

def count_option_snapshots():

    initialize_option_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM option_snapshots
        """
    )

    count = cursor.fetchone()[0]

    connection.close()

    return count


# ============================================================
# COUNT BY OPTION TYPE
# ============================================================

def count_by_option_type():

    initialize_option_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            option_type,
            COUNT(*) AS total

        FROM option_snapshots

        GROUP BY option_type

        ORDER BY option_type
        """
    )

    rows = cursor.fetchall()

    connection.close()

    return {
        row["option_type"]:
            row["total"]
        for row in rows
    }


# ============================================================
# GET SNAPSHOT DETAILS
# ============================================================

def get_snapshot_summary(
    market_snapshot_id
):

    initialize_option_snapshot_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT

            market_snapshot_id,

            timestamp_utc,

            expiry,

            COUNT(*) AS total_options,

            COUNT(
                CASE
                    WHEN option_type = 'CE'
                    THEN 1
                END
            ) AS ce_count,

            COUNT(
                CASE
                    WHEN option_type = 'PE'
                    THEN 1
                END
            ) AS pe_count

        FROM option_snapshots

        WHERE market_snapshot_id = ?

        GROUP BY
            market_snapshot_id,
            timestamp_utc,
            expiry
        """,

        (
            market_snapshot_id,
        )
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "OPTION SNAPSHOT STORE"
    )

    print("=" * 70)

    initialize_option_snapshot_table()

    print()

    print(
        "Option snapshot table initialized."
    )

    print()

    print(
        f"Stored option records : "
        f"{count_option_snapshots()}"
    )

    print()

    counts = count_by_option_type()

    print(
        f"CE records            : "
        f"{counts.get('CE', 0)}"
    )

    print(
        f"PE records            : "
        f"{counts.get('PE', 0)}"
    )

    print()

    print(
        "Available functions:"
    )

    print(
        "- initialize_option_snapshot_table()"
    )

    print(
        "- store_option_snapshot()"
    )

    print(
        "- count_option_snapshots()"
    )

    print(
        "- count_by_option_type()"
    )

    print(
        "- get_snapshot_summary()"
    )

    print()

    print("=" * 70)