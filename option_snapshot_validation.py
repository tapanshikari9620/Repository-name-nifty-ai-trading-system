import sqlite3
from datetime import datetime


DATABASE_NAME = "nifty_market_data.db"


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
# GET LATEST OPTION SNAPSHOT
# ============================================================

def get_latest_snapshot_id():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            market_snapshot_id

        FROM option_snapshots

        ORDER BY id DESC

        LIMIT 1
        """
    )

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None

    return row["market_snapshot_id"]


# ============================================================
# LOAD SNAPSHOT RECORDS
# ============================================================

def load_snapshot(
    market_snapshot_id
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *

        FROM option_snapshots

        WHERE market_snapshot_id = ?

        ORDER BY strike, option_type
        """,
        (
            market_snapshot_id,
        )
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


# ============================================================
# VALIDATE BASIC RECORD
# ============================================================

def validate_basic_record(row):

    errors = []

    # --------------------------------------------------------
    # Strike
    # --------------------------------------------------------

    strike = row["strike"]

    if strike is None:

        errors.append(
            "Missing strike."
        )

    elif strike <= 0:

        errors.append(
            f"Invalid strike: {strike}"
        )

    # --------------------------------------------------------
    # Expiry
    # --------------------------------------------------------

    expiry = row["expiry"]

    if not expiry:

        errors.append(
            "Missing expiry."
        )

    else:

        try:

            datetime.strptime(
                expiry,
                "%Y-%m-%d"
            )

        except ValueError:

            errors.append(
                f"Invalid expiry: {expiry}"
            )

    # --------------------------------------------------------
    # Option type
    # --------------------------------------------------------

    option_type = row[
        "option_type"
    ]

    if option_type not in (
        "CE",
        "PE"
    ):

        errors.append(
            f"Invalid option type: "
            f"{option_type}"
        )

    # --------------------------------------------------------
    # Instrument key
    # --------------------------------------------------------

    instrument_key = row[
        "instrument_key"
    ]

    if not instrument_key:

        errors.append(
            "Missing instrument key."
        )

    # --------------------------------------------------------
    # LTP
    # --------------------------------------------------------

    ltp = row["ltp"]

    if ltp is not None and ltp < 0:

        errors.append(
            f"Invalid LTP: {ltp}"
        )

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    volume = row["volume"]

    if volume is not None and volume < 0:

        errors.append(
            f"Invalid volume: {volume}"
        )

    # --------------------------------------------------------
    # OI
    # --------------------------------------------------------

    oi = row["oi"]

    if oi is not None and oi < 0:

        errors.append(
            f"Invalid OI: {oi}"
        )

    # --------------------------------------------------------
    # Previous OI
    # --------------------------------------------------------

    prev_oi = row["prev_oi"]

    if prev_oi is not None and prev_oi < 0:

        errors.append(
            f"Invalid previous OI: "
            f"{prev_oi}"
        )

    # --------------------------------------------------------
    # OI change consistency
    # --------------------------------------------------------

    oi_change = row[
        "oi_change"
    ]

    if (
        oi is not None
        and prev_oi is not None
        and oi_change is not None
    ):

        expected_change = (
            oi - prev_oi
        )

        if abs(
            oi_change - expected_change
        ) > 0.000001:

            errors.append(
                "OI change mismatch."
            )

    # --------------------------------------------------------
    # IV
    # --------------------------------------------------------

    iv = row["iv"]

    if iv is not None and iv < 0:

        errors.append(
            f"Invalid IV: {iv}"
        )

    # --------------------------------------------------------
    # Greeks
    # --------------------------------------------------------

    delta = row["delta"]

    if (
        delta is not None
        and (
            delta < -1
            or delta > 1
        )
    ):

        errors.append(
            f"Invalid delta: {delta}"
        )

    gamma = row["gamma"]

    if gamma is not None and gamma < 0:

        errors.append(
            f"Invalid gamma: {gamma}"
        )

    # Theta can normally be negative,
    # therefore we do not reject negative theta.

    vega = row["vega"]

    if vega is not None and vega < 0:

        errors.append(
            f"Invalid vega: {vega}"
        )

    # --------------------------------------------------------
    # Bid / Ask
    # --------------------------------------------------------

    bid_price = row[
        "bid_price"
    ]

    ask_price = row[
        "ask_price"
    ]

    if (
        bid_price is not None
        and bid_price < 0
    ):

        errors.append(
            f"Invalid bid price: "
            f"{bid_price}"
        )

    if (
        ask_price is not None
        and ask_price < 0
    ):

        errors.append(
            f"Invalid ask price: "
            f"{ask_price}"
        )

    if (
        bid_price is not None
        and ask_price is not None
        and bid_price > ask_price
        and ask_price > 0
    ):

        errors.append(
            "Bid price greater than ask price."
        )

    return errors


# ============================================================
# VALIDATE SNAPSHOT STRUCTURE
# ============================================================

def validate_snapshot_structure(
    rows
):

    errors = []

    if not rows:

        errors.append(
            "Snapshot contains no records."
        )

        return errors

    # --------------------------------------------------------
    # CE / PE counts
    # --------------------------------------------------------

    ce_rows = [
        row
        for row in rows
        if row["option_type"] == "CE"
    ]

    pe_rows = [
        row
        for row in rows
        if row["option_type"] == "PE"
    ]

    if len(ce_rows) == 0:

        errors.append(
            "No CE records found."
        )

    if len(pe_rows) == 0:

        errors.append(
            "No PE records found."
        )

    # --------------------------------------------------------
    # Strike consistency
    # --------------------------------------------------------

    ce_strikes = {
        row["strike"]
        for row in ce_rows
    }

    pe_strikes = {
        row["strike"]
        for row in pe_rows
    }

    missing_pe = (
        ce_strikes - pe_strikes
    )

    missing_ce = (
        pe_strikes - ce_strikes
    )

    if missing_pe:

        errors.append(
            f"Missing PE strikes: "
            f"{sorted(missing_pe)}"
        )

    if missing_ce:

        errors.append(
            f"Missing CE strikes: "
            f"{sorted(missing_ce)}"
        )

    # --------------------------------------------------------
    # Duplicate contracts
    # --------------------------------------------------------

    contracts = set()

    duplicates = []

    for row in rows:

        key = (
            row["strike"],
            row["option_type"],
            row["expiry"]
        )

        if key in contracts:

            duplicates.append(
                key
            )

        contracts.add(key)

    if duplicates:

        errors.append(
            f"Duplicate contracts: "
            f"{duplicates[:10]}"
        )

    # --------------------------------------------------------
    # Timestamp consistency
    # --------------------------------------------------------

    timestamps = {
        row["timestamp_utc"]
        for row in rows
    }

    if len(timestamps) != 1:

        errors.append(
            "Records in one snapshot "
            "have different timestamps."
        )

    # --------------------------------------------------------
    # Market snapshot ID consistency
    # --------------------------------------------------------

    snapshot_ids = {
        row["market_snapshot_id"]
        for row in rows
    }

    if len(snapshot_ids) != 1:

        errors.append(
            "Records belong to "
            "multiple market snapshots."
        )

    # --------------------------------------------------------
    # Expiry consistency
    # --------------------------------------------------------

    expiries = {
        row["expiry"]
        for row in rows
    }

    if len(expiries) != 1:

        errors.append(
            f"Multiple expiries found: "
            f"{sorted(expiries)}"
        )

    return errors


# ============================================================
# VALIDATE MARKET SNAPSHOT LINK
# ============================================================

def validate_market_snapshot_link(
    market_snapshot_id
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            timestamp_utc,
            spot_price

        FROM market_snapshots

        WHERE id = ?
        """,
        (
            market_snapshot_id,
        )
    )

    row = cursor.fetchone()

    connection.close()

    errors = []

    if row is None:

        errors.append(
            "Referenced market snapshot "
            "does not exist."
        )

        return errors

    if (
        row["spot_price"] is None
        or row["spot_price"] <= 0
    ):

        errors.append(
            "Linked market snapshot "
            "has invalid spot price."
        )

    return errors


# ============================================================
# VALIDATE COMPLETE SNAPSHOT
# ============================================================

def validate_snapshot(
    market_snapshot_id
):

    rows = load_snapshot(
        market_snapshot_id
    )

    errors = []

    # --------------------------------------------------------
    # Structure
    # --------------------------------------------------------

    errors.extend(
        validate_snapshot_structure(
            rows
        )
    )

    # --------------------------------------------------------
    # Individual records
    # --------------------------------------------------------

    for row in rows:

        record_errors = (
            validate_basic_record(
                row
            )
        )

        if record_errors:

            errors.append(
                {
                    "record_id":
                        row["id"],

                    "strike":
                        row["strike"],

                    "option_type":
                        row["option_type"],

                    "errors":
                        record_errors
                }
            )

    # --------------------------------------------------------
    # Market snapshot
    # --------------------------------------------------------

    errors.extend(
        validate_market_snapshot_link(
            market_snapshot_id
        )
    )

    return {
        "market_snapshot_id":
            market_snapshot_id,

        "total_records":
            len(rows),

        "valid":
            len(errors) == 0,

        "errors":
            errors
    }


# ============================================================
# DISPLAY RESULT
# ============================================================

def display_result(
    result
):

    print()
    print("=" * 70)
    print("OPTION SNAPSHOT VALIDATION")
    print("=" * 70)

    print()

    print(
        f"Market Snapshot ID : "
        f"{result['market_snapshot_id']}"
    )

    print(
        f"Total option records : "
        f"{result['total_records']}"
    )

    print()

    if result["valid"]:

        print(
            "VALIDATION STATUS : PASS"
        )

        print()
        print(
            "The complete option snapshot "
            "passed validation."
        )

    else:

        print(
            "VALIDATION STATUS : FAIL"
        )

        print()

        print(
            f"Errors found : "
            f"{len(result['errors'])}"
        )

        print()

        for error in result[
            "errors"
        ][:20]:

            print(
                "ERROR:",
                error
            )

    print()
    print("=" * 70)


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    latest_snapshot_id = (
        get_latest_snapshot_id()
    )

    if latest_snapshot_id is None:

        print(
            "No option snapshot found."
        )

    else:

        result = validate_snapshot(
            latest_snapshot_id
        )

        display_result(
            result
        )