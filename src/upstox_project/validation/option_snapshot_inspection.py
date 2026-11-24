
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = str(MARKET_DATABASE_PATH)

MARKET_TIMEZONE = ZoneInfo(
    "Asia/Kolkata"
)

MAX_ALLOWED_INTERVAL_SECONDS = 90.0

MAX_REASONABLE_LTP = 100000.0

MAX_REASONABLE_OI = 1000000000.0

MAX_REASONABLE_VOLUME = 10000000000.0


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_NAME,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA busy_timeout = 30000"
    )

    connection.execute(
        "PRAGMA query_only = ON"
    )

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
# UTC -> IST
# ============================================================

def convert_to_ist(timestamp):

    parsed = parse_timestamp(
        timestamp
    )

    if parsed is None:
        return None

    return parsed.astimezone(
        MARKET_TIMEZONE
    )


# ============================================================
# LOAD ALL OPTION RECORDS
# ============================================================

def load_option_records():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *

        FROM option_snapshots

        ORDER BY
            timestamp_utc,
            strike,
            option_type
        """
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


# ============================================================
# LOAD MARKET SNAPSHOT IDS
# ============================================================

def load_market_snapshot_ids():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM market_snapshots
        """
    )

    rows = cursor.fetchall()

    connection.close()

    return {
        row["id"]
        for row in rows
    }


# ============================================================
# GROUP RECORDS BY SNAPSHOT
# ============================================================

def group_by_snapshot(records):

    grouped = {}

    for row in records:

        snapshot_id = (
            row["market_snapshot_id"]
        )

        grouped.setdefault(
            snapshot_id,
            []
        ).append(row)

    return grouped


# ============================================================
# SNAPSHOT METADATA
# ============================================================

def get_snapshot_metadata(records):

    metadata = {}

    grouped = group_by_snapshot(
        records
    )

    for snapshot_id, rows in grouped.items():

        timestamps = {
            row["timestamp_utc"]
            for row in rows
        }

        expiries = {
            row["expiry"]
            for row in rows
        }

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

        ce_strikes = {
            row["strike"]
            for row in ce_rows
        }

        pe_strikes = {
            row["strike"]
            for row in pe_rows
        }

        metadata[snapshot_id] = {

            "record_count":
                len(rows),

            "timestamp_count":
                len(timestamps),

            "timestamps":
                timestamps,

            "expiry_count":
                len(expiries),

            "expiries":
                expiries,

            "ce_count":
                len(ce_rows),

            "pe_count":
                len(pe_rows),

            "ce_strikes":
                ce_strikes,

            "pe_strikes":
                pe_strikes,

            "missing_pe":
                ce_strikes - pe_strikes,

            "missing_ce":
                pe_strikes - ce_strikes
        }

    return metadata


# ============================================================
# DETERMINE EXPECTED RECORD COUNT
# ============================================================

def determine_expected_record_count(metadata):

    counts = [
        value["record_count"]
        for value in metadata.values()
        if value["record_count"] > 0
    ]

    if not counts:
        return None

    counter = Counter(
        counts
    )

    return counter.most_common(1)[0][0]


# ============================================================
# CHECK SNAPSHOT COMPLETENESS
# ============================================================

def check_snapshot_completeness(
    metadata,
    expected_record_count
):

    incomplete = []

    for snapshot_id, data in metadata.items():

        problems = []

        if (
            expected_record_count is not None
            and data["record_count"]
            != expected_record_count
        ):

            problems.append(
                f"record_count="
                f"{data['record_count']}, "
                f"expected="
                f"{expected_record_count}"
            )

        if data["ce_count"] == 0:

            problems.append(
                "no CE records"
            )

        if data["pe_count"] == 0:

            problems.append(
                "no PE records"
            )

        if data["missing_ce"]:

            problems.append(
                "missing CE strikes"
            )

        if data["missing_pe"]:

            problems.append(
                "missing PE strikes"
            )

        if data["timestamp_count"] != 1:

            problems.append(
                "multiple timestamps"
            )

        if data["expiry_count"] != 1:

            problems.append(
                "multiple expiries"
            )

        if problems:

            incomplete.append(
                {
                    "snapshot_id":
                        snapshot_id,

                    "problems":
                        problems
                }
            )

    return incomplete


# ============================================================
# CHECK DUPLICATE CONTRACTS
# ============================================================

def check_duplicate_contracts(records):

    contracts = {}

    for row in records:

        key = (
            row["market_snapshot_id"],
            row["expiry"],
            row["strike"],
            row["option_type"]
        )

        contracts.setdefault(
            key,
            []
        ).append(
            row["id"]
        )

    duplicates = {

        key: ids

        for key, ids
        in contracts.items()

        if len(ids) > 1
    }

    return duplicates


# ============================================================
# CHECK SNAPSHOT TIMESTAMP CONSISTENCY
# ============================================================

def check_duplicate_snapshot_timestamps(
    records
):

    snapshot_timestamps = {}

    for row in records:

        snapshot_id = (
            row["market_snapshot_id"]
        )

        timestamp = (
            row["timestamp_utc"]
        )

        snapshot_timestamps.setdefault(
            snapshot_id,
            set()
        ).add(
            timestamp
        )

    invalid_snapshots = []

    for (
        snapshot_id,
        timestamps
    ) in snapshot_timestamps.items():

        if len(timestamps) > 1:

            invalid_snapshots.append(
                snapshot_id
            )

    return invalid_snapshots


# ============================================================
# CHECK SNAPSHOT INTERVALS
# ============================================================

def check_snapshot_intervals(records):

    grouped = group_by_snapshot(
        records
    )

    snapshot_times = []

    invalid_timestamp_snapshots = []

    for snapshot_id, rows in grouped.items():

        timestamps = {
            row["timestamp_utc"]
            for row in rows
        }

        if len(timestamps) != 1:

            invalid_timestamp_snapshots.append(
                snapshot_id
            )

            continue

        timestamp = next(
            iter(timestamps)
        )

        parsed = parse_timestamp(
            timestamp
        )

        if parsed is None:

            invalid_timestamp_snapshots.append(
                snapshot_id
            )

            continue

        snapshot_times.append(
            (
                parsed,
                snapshot_id
            )
        )

    snapshot_times.sort(
        key=lambda item: item[0]
    )

    intervals = []

    large_gaps = []

    for previous, current in zip(
        snapshot_times,
        snapshot_times[1:]
    ):

        previous_time, previous_id = (
            previous
        )

        current_time, current_id = (
            current
        )

        interval = (
            current_time
            - previous_time
        ).total_seconds()

        intervals.append(
            interval
        )

        if (
            interval
            > MAX_ALLOWED_INTERVAL_SECONDS
        ):

            large_gaps.append(
                {
                    "previous_id":
                        previous_id,

                    "current_id":
                        current_id,

                    "previous_timestamp":
                        previous_time.isoformat(),

                    "current_timestamp":
                        current_time.isoformat(),

                    "interval":
                        interval
                }
            )

    if intervals:

        average_interval = (
            sum(intervals)
            / len(intervals)
        )

        minimum_interval = min(
            intervals
        )

        maximum_interval = max(
            intervals
        )

    else:

        average_interval = None

        minimum_interval = None

        maximum_interval = None

    return {

        "intervals":
            intervals,

        "average":
            average_interval,

        "minimum":
            minimum_interval,

        "maximum":
            maximum_interval,

        "large_gaps":
            large_gaps,

        "invalid_timestamp_snapshots":
            invalid_timestamp_snapshots
    }


# ============================================================
# CHECK NUMERIC DATA
# ============================================================

def check_numeric_data(records):

    invalid_ltp = []

    invalid_oi = []

    invalid_volume = []

    invalid_iv = []

    invalid_delta = []

    invalid_gamma = []

    invalid_vega = []

    invalid_bid_ask = []

    oi_mismatches = []

    for row in records:

        record_id = row["id"]

        # ----------------------------------------------------
        # LTP
        # ----------------------------------------------------

        ltp = row["ltp"]

        if (
            ltp is not None
            and (
                ltp < 0
                or ltp > MAX_REASONABLE_LTP
            )
        ):

            invalid_ltp.append(
                record_id
            )

        # ----------------------------------------------------
        # OI
        # ----------------------------------------------------

        oi = row["oi"]

        if (
            oi is not None
            and (
                oi < 0
                or oi > MAX_REASONABLE_OI
            )
        ):

            invalid_oi.append(
                record_id
            )

        # ----------------------------------------------------
        # VOLUME
        # ----------------------------------------------------

        volume = row["volume"]

        if (
            volume is not None
            and (
                volume < 0
                or volume > MAX_REASONABLE_VOLUME
            )
        ):

            invalid_volume.append(
                record_id
            )

        # ----------------------------------------------------
        # IV
        # ----------------------------------------------------

        iv = row["iv"]

        if (
            iv is not None
            and iv < 0
        ):

            invalid_iv.append(
                record_id
            )

        # ----------------------------------------------------
        # DELTA
        # ----------------------------------------------------

        delta = row["delta"]

        if (
            delta is not None
            and (
                delta < -1
                or delta > 1
            )
        ):

            invalid_delta.append(
                record_id
            )

        # ----------------------------------------------------
        # GAMMA
        # ----------------------------------------------------

        gamma = row["gamma"]

        if (
            gamma is not None
            and gamma < 0
        ):

            invalid_gamma.append(
                record_id
            )

        # ----------------------------------------------------
        # VEGA
        # ----------------------------------------------------

        vega = row["vega"]

        if (
            vega is not None
            and vega < 0
        ):

            invalid_vega.append(
                record_id
            )

        # ----------------------------------------------------
        # BID / ASK
        # ----------------------------------------------------

        bid = row["bid_price"]

        ask = row["ask_price"]

        if (
            bid is not None
            and bid < 0
        ):

            invalid_bid_ask.append(
                record_id
            )

        if (
            ask is not None
            and ask < 0
        ):

            invalid_bid_ask.append(
                record_id
            )

        if (
            bid is not None
            and ask is not None
            and ask > 0
            and bid > ask
        ):

            invalid_bid_ask.append(
                record_id
            )

        # ----------------------------------------------------
        # OI CHANGE
        # ----------------------------------------------------

        prev_oi = row["prev_oi"]

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
                oi_change
                - expected_change
            ) > 0.000001:

                oi_mismatches.append(
                    record_id
                )

    return {

        "invalid_ltp":
            invalid_ltp,

        "invalid_oi":
            invalid_oi,

        "invalid_volume":
            invalid_volume,

        "invalid_iv":
            invalid_iv,

        "invalid_delta":
            invalid_delta,

        "invalid_gamma":
            invalid_gamma,

        "invalid_vega":
            invalid_vega,

        "invalid_bid_ask":
            invalid_bid_ask,

        "oi_mismatches":
            oi_mismatches
    }


# ============================================================
# CHECK MARKET SNAPSHOT LINKS
# ============================================================

def check_market_links(records):

    market_ids = (
        load_market_snapshot_ids()
    )

    missing_links = []

    for row in records:

        snapshot_id = (
            row["market_snapshot_id"]
        )

        if snapshot_id not in market_ids:

            missing_links.append(
                {
                    "option_record_id":
                        row["id"],

                    "market_snapshot_id":
                        snapshot_id
                }
            )

    return missing_links


# ============================================================
# CHECK CONTRACT IDENTITY
# ============================================================

def check_contract_identity(records):

    invalid_option_types = []

    missing_instrument_keys = []

    for row in records:

        if row[
            "option_type"
        ] not in (
            "CE",
            "PE"
        ):

            invalid_option_types.append(
                row["id"]
            )

        if not row[
            "instrument_key"
        ]:

            missing_instrument_keys.append(
                row["id"]
            )

    return {

        "invalid_option_types":
            invalid_option_types,

        "missing_instrument_keys":
            missing_instrument_keys
    }


# ============================================================
# GROUP SNAPSHOTS BY TRADING DATE
# ============================================================

def group_snapshots_by_trading_date(
    records
):

    grouped = {}

    snapshot_timestamps = {}

    for row in records:

        snapshot_id = (
            row["market_snapshot_id"]
        )

        snapshot_timestamps.setdefault(
            snapshot_id,
            row["timestamp_utc"]
        )

    for (
        snapshot_id,
        timestamp
    ) in snapshot_timestamps.items():

        timestamp_ist = convert_to_ist(
            timestamp
        )

        if timestamp_ist is None:

            continue

        trading_date = (
            timestamp_ist
            .date()
            .isoformat()
        )

        grouped.setdefault(
            trading_date,
            []
        ).append(
            snapshot_id
        )

    return grouped


# ============================================================
# BUILD COMPLETE REPORT
# ============================================================

def build_report():

    records = load_option_records()

    if not records:

        return {

            "status":
                "FAIL",

            "reason":
                "No option snapshot records found."
        }

    metadata = get_snapshot_metadata(
        records
    )

    expected_record_count = (
        determine_expected_record_count(
            metadata
        )
    )

    incomplete_snapshots = (
        check_snapshot_completeness(
            metadata,
            expected_record_count
        )
    )

    duplicate_contracts = (
        check_duplicate_contracts(
            records
        )
    )

    duplicate_timestamp_snapshots = (
        check_duplicate_snapshot_timestamps(
            records
        )
    )

    interval_analysis = (
        check_snapshot_intervals(
            records
        )
    )

    numeric_analysis = (
        check_numeric_data(
            records
        )
    )

    market_link_errors = (
        check_market_links(
            records
        )
    )

    identity_analysis = (
        check_contract_identity(
            records
        )
    )

    trading_sessions = (
        group_snapshots_by_trading_date(
            records
        )
    )

    # ========================================================
    # DETERMINE STATUS
    # ========================================================

    problems = []

    if incomplete_snapshots:

        problems.append(
            "incomplete snapshots"
        )

    if duplicate_contracts:

        problems.append(
            "duplicate contracts"
        )

    if duplicate_timestamp_snapshots:

        problems.append(
            "duplicate snapshot timestamps"
        )

    if interval_analysis[
        "invalid_timestamp_snapshots"
    ]:

        problems.append(
            "invalid timestamps"
        )

    if interval_analysis[
        "large_gaps"
    ]:

        problems.append(
            "large collection gaps"
        )

    if numeric_analysis[
        "invalid_ltp"
    ]:

        problems.append(
            "invalid LTP"
        )

    if numeric_analysis[
        "invalid_oi"
    ]:

        problems.append(
            "invalid OI"
        )

    if numeric_analysis[
        "invalid_volume"
    ]:

        problems.append(
            "invalid volume"
        )

    if numeric_analysis[
        "invalid_iv"
    ]:

        problems.append(
            "invalid IV"
        )

    if numeric_analysis[
        "invalid_delta"
    ]:

        problems.append(
            "invalid delta"
        )

    if numeric_analysis[
        "invalid_gamma"
    ]:

        problems.append(
            "invalid gamma"
        )

    if numeric_analysis[
        "invalid_vega"
    ]:

        problems.append(
            "invalid vega"
        )

    if numeric_analysis[
        "invalid_bid_ask"
    ]:

        problems.append(
            "invalid bid/ask"
        )

    if numeric_analysis[
        "oi_mismatches"
    ]:

        problems.append(
            "OI calculation mismatch"
        )

    if market_link_errors:

        problems.append(
            "broken market snapshot links"
        )

    if identity_analysis[
        "invalid_option_types"
    ]:

        problems.append(
            "invalid option types"
        )

    if identity_analysis[
        "missing_instrument_keys"
    ]:

        problems.append(
            "missing instrument keys"
        )

    if problems:

        status = "WARNING"

    else:

        status = "PASS"

    return {

        "status":
            status,

        "total_records":
            len(records),

        "total_snapshots":
            len(metadata),

        "trading_sessions":
            trading_sessions,

        "expected_record_count":
            expected_record_count,

        "incomplete_snapshots":
            incomplete_snapshots,

        "duplicate_contracts":
            duplicate_contracts,

        "duplicate_timestamp_snapshots":
            duplicate_timestamp_snapshots,

        "interval_analysis":
            interval_analysis,

        "numeric_analysis":
            numeric_analysis,

        "market_link_errors":
            market_link_errors,

        "identity_analysis":
            identity_analysis,

        "problems":
            problems
    }


# ============================================================
# DISPLAY REPORT
# ============================================================

def display_report(report):

    print()

    print("=" * 70)

    print(
        "NIFTY OPTION DATA QUALITY REPORT"
    )

    print("=" * 70)

    # ========================================================
    # FAIL WITH NO DATA
    # ========================================================

    if report["status"] == "FAIL":

        print()

        print(
            "DATA QUALITY STATUS : FAIL"
        )

        print()

        print(
            report.get(
                "reason",
                "Unknown error."
            )
        )

        print()

        print("=" * 70)

        return

    # ========================================================
    # GENERAL SUMMARY
    # ========================================================

    print()

    print(
        f"Total option records  : "
        f"{report['total_records']}"
    )

    print(
        f"Option snapshots      : "
        f"{report['total_snapshots']}"
    )

    print(
        f"Trading sessions      : "
        f"{len(report['trading_sessions'])}"
    )

    # ========================================================
    # SNAPSHOT ANALYSIS
    # ========================================================

    print()

    print(
        "SNAPSHOT ANALYSIS"
    )

    print("-" * 70)

    print(
        f"Expected records/snapshot : "
        f"{report['expected_record_count']}"
    )

    print(
        f"Incomplete snapshots      : "
        f"{len(report['incomplete_snapshots'])}"
    )

    print(
        f"Duplicate contracts       : "
        f"{len(report['duplicate_contracts'])}"
    )

    print(
        f"Duplicate timestamps      : "
        f"{len(report['duplicate_timestamp_snapshots'])}"
    )

    # ========================================================
    # TIMESTAMP ANALYSIS
    # ========================================================

    print()

    print(
        "TIMESTAMP ANALYSIS"
    )

    print("-" * 70)

    interval = (
        report["interval_analysis"]
    )

    if interval["average"] is not None:

        print(
            f"Average interval          : "
            f"{interval['average']:.2f} sec"
        )

        print(
            f"Minimum interval          : "
            f"{interval['minimum']:.2f} sec"
        )

        print(
            f"Maximum interval          : "
            f"{interval['maximum']:.2f} sec"
        )

    else:

        print(
            "Not enough snapshots "
            "to calculate intervals."
        )

    print(
        f"Large gaps                : "
        f"{len(interval['large_gaps'])}"
    )

    print(
        f"Invalid timestamps        : "
        f"{len(interval['invalid_timestamp_snapshots'])}"
    )

    # ========================================================
    # NUMERIC VALIDATION
    # ========================================================

    print()

    print(
        "NUMERIC DATA VALIDATION"
    )

    print("-" * 70)

    numeric = (
        report["numeric_analysis"]
    )

    print(
        f"Invalid LTP               : "
        f"{len(numeric['invalid_ltp'])}"
    )

    print(
        f"Invalid OI                : "
        f"{len(numeric['invalid_oi'])}"
    )

    print(
        f"Invalid volume            : "
        f"{len(numeric['invalid_volume'])}"
    )

    print(
        f"Invalid IV                : "
        f"{len(numeric['invalid_iv'])}"
    )

    print(
        f"Invalid delta             : "
        f"{len(numeric['invalid_delta'])}"
    )

    print(
        f"Invalid gamma             : "
        f"{len(numeric['invalid_gamma'])}"
    )

    print(
        f"Invalid vega              : "
        f"{len(numeric['invalid_vega'])}"
    )

    print(
        f"Invalid bid/ask           : "
        f"{len(numeric['invalid_bid_ask'])}"
    )

    print(
        f"OI mismatches             : "
        f"{len(numeric['oi_mismatches'])}"
    )

    # ========================================================
    # DATABASE INTEGRITY
    # ========================================================

    print()

    print(
        "DATABASE INTEGRITY"
    )

    print("-" * 70)

    print(
        f"Broken market links       : "
        f"{len(report['market_link_errors'])}"
    )

    print(
        f"Invalid option types      : "
        f"{len(report['identity_analysis']['invalid_option_types'])}"
    )

    print(
        f"Missing instrument keys   : "
        f"{len(report['identity_analysis']['missing_instrument_keys'])}"
    )

    # ========================================================
    # TRADING SESSIONS
    # ========================================================

    print()

    print(
        "TRADING SESSIONS"
    )

    print("-" * 70)

    for (
        trading_date,
        snapshot_ids
    ) in report[
        "trading_sessions"
    ].items():

        print(
            f"{trading_date} : "
            f"{len(snapshot_ids)} snapshots"
        )

    # ========================================================
    # OVERALL STATUS
    # ========================================================

    print()

    print("-" * 70)

    print(
        f"DATA QUALITY STATUS : "
        f"{report['status']}"
    )

    print("-" * 70)

    # ========================================================
    # PROBLEM SUMMARY
    # ========================================================

    if report["problems"]:

        print()

        print(
            "Detected issues:"
        )

        for problem in report[
            "problems"
        ]:

            print(
                f"  - {problem}"
            )

        # ====================================================
        # DETAILED COLLECTION GAP INFORMATION
        # ====================================================

        large_gaps = (
            report[
                "interval_analysis"
            ][
                "large_gaps"
            ]
        )

        if large_gaps:

            print()

            print(
                "COLLECTION GAP DETAILS"
            )

            print(
                "-" * 70
            )

            for gap in large_gaps:

                previous_id = gap[
                    "previous_id"
                ]

                current_id = gap[
                    "current_id"
                ]

                previous_timestamp = gap[
                    "previous_timestamp"
                ]

                current_timestamp = gap[
                    "current_timestamp"
                ]

                interval = gap[
                    "interval"
                ]

                previous_ist = (
                    convert_to_ist(
                        previous_timestamp
                    )
                )

                current_ist = (
                    convert_to_ist(
                        current_timestamp
                    )
                )

                print()

                print(
                    f"Previous snapshot ID : "
                    f"{previous_id}"
                )

                print(
                    f"Previous timestamp   : "
                    f"{previous_timestamp}"
                )

                print(
                    f"Previous timestamp IST : "
                    f"{previous_ist}"
                )

                print()

                print(
                    f"Current snapshot ID  : "
                    f"{current_id}"
                )

                print(
                    f"Current timestamp    : "
                    f"{current_timestamp}"
                )

                print(
                    f"Current timestamp IST: "
                    f"{current_ist}"
                )

                print()

                print(
                    f"Gap                  : "
                    f"{interval:.2f} seconds"
                )

                print(
                    f"Gap                  : "
                    f"{interval / 60:.2f} minutes"
                )

                print(
                    f"Gap                  : "
                    f"{interval / 3600:.2f} hours"
                )

                print()

                print("-" * 70)

    else:

        print()

        print(
            "No data-quality problems detected."
        )

    # ========================================================
    # FINAL LINE
    # ========================================================

    print()

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    report = build_report()

    display_report(
        report
    )