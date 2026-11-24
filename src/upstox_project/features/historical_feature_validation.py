
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3
import math
import os
from pathlib import Path

import upstox_project.features.historical_feature_builder as feature_builder


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = str(MARKET_DATABASE_PATH)

FLOAT_TOLERANCE = 1e-6


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    database_uri = Path(DATABASE_NAME).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

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
# FLOAT COMPARISON
# ============================================================

def numbers_match(
    actual,
    expected,
    tolerance=FLOAT_TOLERANCE
):

    actual = safe_number(actual)

    expected = safe_number(expected)

    return (
        abs(
            actual - expected
        )
        <= tolerance
    )


# ============================================================
# LOAD FEATURE SNAPSHOTS
# ============================================================

def load_feature_snapshots():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *

        FROM market_features

        ORDER BY
            timestamp_utc ASC,
            market_snapshot_id ASC
        """
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


# ============================================================
# LOAD RAW OPTION DATA
# ============================================================

def load_option_rows(
    market_snapshot_id
):

    connection = get_connection()

    cursor = connection.cursor()

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
            market_snapshot_id,
        )
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


# ============================================================
# CALCULATE RAW MARKET METRICS
# ============================================================

def calculate_raw_metrics(
    market_snapshot_id,
    spot_price
):

    option_rows = load_option_rows(
        market_snapshot_id
    )

    connection = get_connection()
    market_row = connection.execute(
        """
        SELECT id, timestamp_utc, spot_price
        FROM market_snapshots
        WHERE id = ?
        """,
        (market_snapshot_id,),
    ).fetchone()
    connection.close()

    if market_row is None:
        return {
            "valid": False,
            "reason": "Market snapshot does not exist.",
        }

    structural_errors = feature_builder.validate_snapshot_records(
        market_row,
        option_rows,
    )
    if structural_errors:
        return {
            "valid": False,
            "reason": "; ".join(structural_errors),
        }

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

    # ========================================================
    # STRIKES
    # ========================================================

    strikes = sorted(
        {
            safe_number(
                row["strike"]
            )
            for row in option_rows
        }
    )

    if not strikes:

        return {
            "valid": False,
            "reason": "No strikes found."
        }

    atm_strike = min(
        strikes,
        key=lambda strike:
            abs(
                strike
                - spot_price
            )
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

    pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else None

    # ========================================================
    # OI CHANGE
    # ========================================================

    total_ce_oi_change = sum(
        safe_number(
            row["oi_change"]
        )
        for row in ce_rows
    )

    total_pe_oi_change = sum(
        safe_number(
            row["oi_change"]
        )
        for row in pe_rows
    )

    oi_pressure = (
        total_pe_oi_change
        - total_ce_oi_change
    )

    # ========================================================
    # VOLUME
    # ========================================================

    total_ce_volume = sum(
        safe_number(
            row["volume"]
        )
        for row in ce_rows
    )

    total_pe_volume = sum(
        safe_number(
            row["volume"]
        )
        for row in pe_rows
    )

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

    return {

        "valid": True,

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
# VALIDATE ONE FEATURE SNAPSHOT
# ============================================================

def validate_feature_snapshot(
    feature_row
):

    snapshot_id = (
        feature_row[
            "market_snapshot_id"
        ]
    )

    spot_price = safe_number(
        feature_row[
            "spot_price"
        ]
    )

    raw = calculate_raw_metrics(
        snapshot_id,
        spot_price
    )

    if not raw["valid"]:

        return {
            "valid": False,
            "snapshot_id": snapshot_id,
            "errors": [
                raw["reason"]
            ]
        }

    fields = [

        "spot_price",
        "atm_strike",
        "support",
        "resistance",

        "total_ce_oi",
        "total_pe_oi",
        "pcr",

        "total_ce_oi_change",
        "total_pe_oi_change",
        "oi_pressure",

        "total_ce_volume",
        "total_pe_volume",
        "volume_pressure",

        "highest_ce_oi",
        "highest_pe_oi",

        "highest_ce_oi_change",
        "highest_pe_oi_change"
    ]

    errors = []

    for field in fields:

        stored_value = feature_row[
            field
        ]

        calculated_value = raw[
            field
        ]

        if not numbers_match(
            stored_value,
            calculated_value
        ):

            errors.append(
                {
                    "field": field,

                    "stored":
                        safe_number(
                            stored_value
                        ),

                    "calculated":
                        safe_number(
                            calculated_value
                        )
                }
            )

    return {

        "valid":
            len(errors) == 0,

        "snapshot_id":
            snapshot_id,

        "errors":
            errors
    }


# ============================================================
# VALIDATE ALL FEATURES
# ============================================================

def validate_all_features():

    feature_rows = (
        load_feature_snapshots()
    )

    if not feature_rows:

        raise RuntimeError(
            "No market feature rows found."
        )

    passed = 0

    failed = 0

    invalid_raw_snapshots = 0

    failures = []

    for row in feature_rows:

        result = (
            validate_feature_snapshot(
                row
            )
        )

        if result["valid"]:

            passed += 1

        else:

            failed += 1

            failures.append(
                result
            )

    return {

        "total":
            len(feature_rows),

        "passed":
            passed,

        "failed":
            failed,

        "failures":
            failures
    }


# ============================================================
# OPTION FEATURE COUNT VALIDATION
# ============================================================

def validate_option_feature_counts():

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT DISTINCT market_snapshot_id FROM option_features "
        "ORDER BY market_snapshot_id"
    )
    rows = cursor.fetchall()
    invalid_snapshots = []

    for row in rows:
        snapshot_id = row["market_snapshot_id"]
        raw_rows = connection.execute(
            """
            SELECT expiry, strike, option_type
            FROM option_snapshots
            WHERE market_snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchall()
        feature_rows = connection.execute(
            """
            SELECT expiry, strike, option_type
            FROM option_features
            WHERE market_snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchall()
        raw_contracts = {
            (item["expiry"], item["strike"], item["option_type"])
            for item in raw_rows
        }
        feature_contracts = {
            (item["expiry"], item["strike"], item["option_type"])
            for item in feature_rows
        }
        missing = raw_contracts - feature_contracts
        unexpected = feature_contracts - raw_contracts
        if missing or unexpected or len(raw_rows) != len(feature_rows):
            invalid_snapshots.append(
                {
                    "market_snapshot_id": snapshot_id,
                    "record_count": len(feature_rows),
                    "raw_record_count": len(raw_rows),
                    "missing_contracts": len(missing),
                    "unexpected_contracts": len(unexpected),
                }
            )

    connection.close()

    return {

        "snapshots":
            len(rows),

        "invalid":
            invalid_snapshots
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "HISTORICAL FEATURE VALIDATION"
    )

    print("=" * 70)

    print()

    print(
        "Validating market feature calculations..."
    )

    result = (
        validate_all_features()
    )

    print()

    print(
        "MARKET FEATURE VALIDATION"
    )

    print("-" * 70)

    print(
        f"Total feature snapshots : "
        f"{result['total']}"
    )

    print(
        f"Passed                  : "
        f"{result['passed']}"
    )

    print(
        f"Failed                  : "
        f"{result['failed']}"
    )

    # ========================================================
    # SHOW FAILURES
    # ========================================================

    if result["failures"]:

        print()

        print(
            "VALIDATION FAILURES"
        )

        print("-" * 70)

        for failure in result[
            "failures"
        ]:

            print(
                f"Snapshot ID : "
                f"{failure['snapshot_id']}"
            )

            for error in failure[
                "errors"
            ]:

                # Raw snapshot error

                if isinstance(
                    error,
                    str
                ):

                    print(
                        f"  ERROR: "
                        f"{error}"
                    )

                    continue

                print(
                    f"  {error['field']}: "
                    f"stored="
                    f"{error['stored']} | "
                    f"calculated="
                    f"{error['calculated']}"
                )

            print()

    # ========================================================
    # OPTION FEATURE VALIDATION
    # ========================================================

    option_result = (
        validate_option_feature_counts()
    )

    print(
        "OPTION FEATURE VALIDATION"
    )

    print("-" * 70)

    print(
        f"Feature snapshots       : "
        f"{option_result['snapshots']}"
    )

    print(
        f"Invalid record counts   : "
        f"{len(option_result['invalid'])}"
    )

    if option_result["invalid"]:

        print()

        for invalid in (
            option_result["invalid"]
        ):

            print(
                f"Snapshot {invalid['market_snapshot_id']} has "
                f"{invalid['record_count']} feature rows versus "
                f"{invalid['raw_record_count']} raw contracts "
                f"(missing={invalid['missing_contracts']}, "
                f"unexpected={invalid['unexpected_contracts']})."
            )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    overall_pass = (

        result["failed"] == 0

        and

        len(
            option_result["invalid"]
        ) == 0
    )

    print()

    print("-" * 70)

    if overall_pass:

        print(
            "FEATURE VALIDATION STATUS : PASS"
        )

        print()

        print(
            "All stored historical market "
            "features reproduce the raw "
            "option-chain calculations."
        )

        print(
            "Option feature rows match their raw contracts."
        )

    else:

        print(
            "FEATURE VALIDATION STATUS : FAIL"
        )

        print()

        print(
            "Do not proceed to ML/outcome "
            "dataset generation until the "
            "feature calculation mismatch "
            "is resolved."
        )

    print()

    print("=" * 70)