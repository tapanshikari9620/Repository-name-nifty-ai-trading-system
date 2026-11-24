
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ============================================================
# NIFTY OPTION SNAPSHOT INSPECTION - READ ONLY
# ============================================================
# This script ONLY reads nifty_market_data.db.
# It never INSERTs, UPDATEs or DELETEs data.
#
# IMPORTANT FIX:
# Do NOT use a fixed "expected records/snapshot" such as 210.
# The collector itself calculates the expected count dynamically:
#     len(option_chain) * 2
# Therefore, different snapshots can legitimately contain different
# numbers of strikes/records.
#
# A snapshot is structurally complete when:
#   1. It has CE and PE records.
#   2. CE and PE strike sets are identical.
#   3. It has exactly one timestamp.
#   4. It has exactly one expiry.
#   5. Every record is CE or PE.
#   6. There are no duplicate contracts.
#   7. There are no missing instrument keys.
#   8. Record count = CE count + PE count.
# ============================================================

DATABASE_NAME = str(MARKET_DATABASE_PATH)
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

# Collector interval is 60 sec. We allow some execution/network delay.
MAX_ALLOWED_INTERVAL_SECONDS = 90.0

MAX_REASONABLE_LTP = 100000.0
MAX_REASONABLE_OI = 1_000_000_000.0
MAX_REASONABLE_VOLUME = 10_000_000_000.0

REQUIRED_OPTION_COLUMNS = {
    "id",
    "market_snapshot_id",
    "timestamp_utc",
    "expiry",
    "strike",
    "option_type",
    "instrument_key",
    "ltp",
    "oi",
    "volume",
    "iv",
    "delta",
    "gamma",
    "vega",
    "bid_price",
    "ask_price",
    "prev_oi",
    "oi_change",
}


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    """Open SQLite strictly in read-only mode."""
    db_path = Path(DATABASE_NAME).resolve()

    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}"
        )

    connection = sqlite3.connect(
        f"file:{db_path.as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def table_exists(connection, table_name):
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def get_columns(connection, table_name):
    return {
        row["name"]
        for row in connection.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()
    }


def validate_schema(connection):
    required_tables = {
        "market_snapshots",
        "option_snapshots",
    }

    missing_tables = [
        table
        for table in required_tables
        if not table_exists(connection, table)
    ]

    if missing_tables:
        raise RuntimeError(
            "Missing required table(s): "
            + ", ".join(sorted(missing_tables))
        )

    option_columns = get_columns(
        connection,
        "option_snapshots",
    )

    missing_columns = sorted(
        REQUIRED_OPTION_COLUMNS - option_columns
    )

    if missing_columns:
        raise RuntimeError(
            "option_snapshots is missing required column(s): "
            + ", ".join(missing_columns)
        )

    market_columns = get_columns(
        connection,
        "market_snapshots",
    )

    if "id" not in market_columns:
        raise RuntimeError(
            "market_snapshots is missing required column: id"
        )

    return option_columns, market_columns


# ============================================================
# TIME
# ============================================================

def parse_timestamp(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


def to_ist(value):
    parsed = parse_timestamp(value)

    if parsed is None:
        return None

    return parsed.astimezone(
        MARKET_TIMEZONE
    )


# ============================================================
# LOAD DATA
# ============================================================

def load_option_records(connection):
    return connection.execute(
        """
        SELECT
            id,
            market_snapshot_id,
            timestamp_utc,
            expiry,
            strike,
            option_type,
            instrument_key,
            ltp,
            oi,
            volume,
            iv,
            delta,
            gamma,
            vega,
            bid_price,
            ask_price,
            prev_oi,
            oi_change
        FROM option_snapshots
        ORDER BY
            timestamp_utc,
            market_snapshot_id,
            strike,
            option_type
        """
    ).fetchall()


# ============================================================
# SNAPSHOT METADATA
# ============================================================

def build_snapshot_metadata(records):
    metadata = {}

    for row in records:
        snapshot_id = row["market_snapshot_id"]

        data = metadata.setdefault(
            snapshot_id,
            {
                "record_count": 0,
                "timestamps": set(),
                "expiries": set(),
                "ce_count": 0,
                "pe_count": 0,
                "ce_strikes": set(),
                "pe_strikes": set(),
                "contract_keys": set(),
                "duplicate_contracts": [],
                "invalid_option_types": [],
                "missing_instrument_keys": [],
                "invalid_strikes": [],
            },
        )

        data["record_count"] += 1

        data["timestamps"].add(
            row["timestamp_utc"]
        )

        data["expiries"].add(
            row["expiry"]
        )

        option_type = row["option_type"]

        if option_type == "CE":
            data["ce_count"] += 1
            data["ce_strikes"].add(
                row["strike"]
            )

        elif option_type == "PE":
            data["pe_count"] += 1
            data["pe_strikes"].add(
                row["strike"]
            )

        else:
            data["invalid_option_types"].append(
                row["id"]
            )

        if not row["instrument_key"]:
            data["missing_instrument_keys"].append(
                row["id"]
            )

        strike = row["strike"]

        try:
            strike_value = float(strike)
        except (TypeError, ValueError):
            strike_value = None

        if strike_value is None or strike_value <= 0:
            data["invalid_strikes"].append(
                row["id"]
            )

        contract_key = (
            row["expiry"],
            row["strike"],
            row["option_type"],
        )

        if contract_key in data["contract_keys"]:
            data["duplicate_contracts"].append(
                row["id"]
            )
        else:
            data["contract_keys"].add(
                contract_key
            )

    return metadata


# ============================================================
# STRUCTURAL COMPLETENESS
# ============================================================

def analyze_snapshot_completeness(metadata):
    """
    NO FIXED RECORD COUNT IS USED.

    Example:
        105 strikes -> 210 records
        110 strikes -> 220 records
        121 strikes -> 242 records

    All can be complete if CE and PE strike sets match.
    """

    incomplete = []

    for snapshot_id, data in metadata.items():
        problems = []

        ce_strikes = data["ce_strikes"]
        pe_strikes = data["pe_strikes"]

        missing_pe = ce_strikes - pe_strikes
        missing_ce = pe_strikes - ce_strikes

        if data["record_count"] <= 0:
            problems.append("no option records")

        if data["ce_count"] == 0:
            problems.append("no CE records")

        if data["pe_count"] == 0:
            problems.append("no PE records")

        if missing_pe:
            problems.append(
                f"missing PE for {len(missing_pe)} strike(s)"
            )

        if missing_ce:
            problems.append(
                f"missing CE for {len(missing_ce)} strike(s)"
            )

        if len(data["timestamps"]) != 1:
            problems.append(
                f"timestamp_count={len(data['timestamps'])}"
            )

        if len(data["expiries"]) != 1:
            problems.append(
                f"expiry_count={len(data['expiries'])}"
            )

        if (
            data["record_count"]
            != data["ce_count"] + data["pe_count"]
        ):
            problems.append(
                "record count != CE count + PE count"
            )

        if data["duplicate_contracts"]:
            problems.append(
                "duplicate contracts"
            )

        if data["invalid_option_types"]:
            problems.append(
                "invalid option types"
            )

        if data["missing_instrument_keys"]:
            problems.append(
                "missing instrument keys"
            )

        if data["invalid_strikes"]:
            problems.append(
                "invalid strike values"
            )

        if problems:
            incomplete.append(
                {
                    "snapshot_id": snapshot_id,
                    "record_count": data["record_count"],
                    "ce_count": data["ce_count"],
                    "pe_count": data["pe_count"],
                    "strike_count": len(
                        ce_strikes | pe_strikes
                    ),
                    "problems": problems,
                }
            )

    return incomplete


# ============================================================
# DUPLICATE CHECKS
# ============================================================

def check_duplicate_contracts(records):
    """
    Duplicate contract key:
        snapshot + expiry + strike + option_type
    """

    seen = {}
    duplicates = {}

    for row in records:
        key = (
            row["market_snapshot_id"],
            row["expiry"],
            row["strike"],
            row["option_type"],
        )

        if key in seen:
            duplicates.setdefault(
                key,
                [seen[key]],
            ).append(
                row["id"]
            )
        else:
            seen[key] = row["id"]

    return duplicates


def check_snapshot_timestamp_consistency(records):
    """
    Detect a single snapshot containing more than one timestamp.
    """

    timestamps = {}

    for row in records:
        snapshot_id = row[
            "market_snapshot_id"
        ]

        timestamps.setdefault(
            snapshot_id,
            set(),
        ).add(
            row["timestamp_utc"]
        )

    return {
        snapshot_id: values
        for snapshot_id, values
        in timestamps.items()
        if len(values) != 1
    }


def check_duplicate_snapshot_timestamps(records):
    """
    Detect two different snapshot IDs using the same timestamp.
    """

    timestamp_to_snapshots = {}

    for row in records:
        timestamp = row["timestamp_utc"]
        snapshot_id = row[
            "market_snapshot_id"
        ]

        if timestamp is None:
            continue

        timestamp_to_snapshots.setdefault(
            timestamp,
            set(),
        ).add(
            snapshot_id
        )

    return {
        timestamp: snapshot_ids
        for timestamp, snapshot_ids
        in timestamp_to_snapshots.items()
        if len(snapshot_ids) > 1
    }


# ============================================================
# NUMERIC VALIDATION
# ============================================================

def check_numeric_data(records):
    result = {
        "invalid_ltp": [],
        "invalid_oi": [],
        "invalid_volume": [],
        "invalid_iv": [],
        "invalid_delta": [],
        "invalid_gamma": [],
        "invalid_vega": [],
        "invalid_bid_ask": [],
        "oi_mismatches": [],
    }

    for row in records:
        record_id = row["id"]

        ltp = row["ltp"]

        if ltp is not None and (
            ltp < 0
            or ltp > MAX_REASONABLE_LTP
        ):
            result["invalid_ltp"].append(
                record_id
            )

        oi = row["oi"]

        if oi is not None and (
            oi < 0
            or oi > MAX_REASONABLE_OI
        ):
            result["invalid_oi"].append(
                record_id
            )

        volume = row["volume"]

        if volume is not None and (
            volume < 0
            or volume > MAX_REASONABLE_VOLUME
        ):
            result["invalid_volume"].append(
                record_id
            )

        iv = row["iv"]

        if iv is not None and iv < 0:
            result["invalid_iv"].append(
                record_id
            )

        delta = row["delta"]

        if delta is not None and (
            delta < -1
            or delta > 1
        ):
            result["invalid_delta"].append(
                record_id
            )

        gamma = row["gamma"]

        if gamma is not None and gamma < 0:
            result["invalid_gamma"].append(
                record_id
            )

        vega = row["vega"]

        if vega is not None and vega < 0:
            result["invalid_vega"].append(
                record_id
            )

        bid = row["bid_price"]
        ask = row["ask_price"]

        if bid is not None and bid < 0:
            result["invalid_bid_ask"].append(
                record_id
            )

        if ask is not None and ask < 0:
            result["invalid_bid_ask"].append(
                record_id
            )

        if (
            bid is not None
            and ask is not None
            and ask > 0
            and bid > ask
        ):
            result["invalid_bid_ask"].append(
                record_id
            )

        # Informational only.
        # We do NOT automatically reject data because broker/API
        # OI-change semantics should be reviewed separately.
        prev_oi = row["prev_oi"]
        oi_change = row["oi_change"]

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
                result[
                    "oi_mismatches"
                ].append(
                    record_id
                )

    return result


# ============================================================
# DATABASE LINK INTEGRITY
# ============================================================

def check_market_links(
    connection,
    records,
):
    market_ids = {
        row["id"]
        for row in connection.execute(
            "SELECT id FROM market_snapshots"
        ).fetchall()
    }

    option_snapshot_ids = {
        row["market_snapshot_id"]
        for row in records
    }

    orphan_option_records = [
        row["id"]
        for row in records
        if row["market_snapshot_id"]
        not in market_ids
    ]

    market_snapshots_without_options = sorted(
        market_ids - option_snapshot_ids
    )

    return (
        orphan_option_records,
        market_snapshots_without_options,
    )


# ============================================================
# SNAPSHOT SIZE DISTRIBUTION
# ============================================================

def get_record_count_distribution(
    metadata,
):
    return Counter(
        data["record_count"]
        for data in metadata.values()
    )


# ============================================================
# TRADING SESSION ANALYSIS
# ============================================================

def get_sessions(metadata):
    """
    Group by IST calendar date.

    This intentionally uses only the snapshot's own timestamp.
    """

    sessions = {}

    for snapshot_id, data in metadata.items():

        if len(data["timestamps"]) != 1:
            continue

        timestamp = next(
            iter(data["timestamps"])
        )

        timestamp_ist = to_ist(
            timestamp
        )

        if timestamp_ist is None:
            continue

        trading_date = (
            timestamp_ist
            .date()
            .isoformat()
        )

        sessions.setdefault(
            trading_date,
            [],
        ).append(
            {
                "snapshot_id": snapshot_id,
                "timestamp": timestamp_ist,
                "record_count": data[
                    "record_count"
                ],
                "strike_count": len(
                    data["ce_strikes"]
                    | data["pe_strikes"]
                ),
            }
        )

    for snapshots in sessions.values():
        snapshots.sort(
            key=lambda item: item["timestamp"]
        )

    return sessions


def analyze_intervals(sessions):
    """
    IMPORTANT:
    Calculate gaps only INSIDE each trading session.

    This avoids treating:
        previous day 15:30 -> next day 09:15
    as a collection failure.
    """

    intervals = []
    large_gaps = []

    for trading_date, snapshots in sessions.items():

        for previous, current in zip(
            snapshots,
            snapshots[1:],
        ):
            gap_seconds = (
                current["timestamp"]
                - previous["timestamp"]
            ).total_seconds()

            intervals.append(
                gap_seconds
            )

            if (
                gap_seconds
                > MAX_ALLOWED_INTERVAL_SECONDS
            ):
                large_gaps.append(
                    {
                        "trading_date": trading_date,
                        "previous_id":
                            previous["snapshot_id"],
                        "current_id":
                            current["snapshot_id"],
                        "previous_timestamp":
                            previous["timestamp"],
                        "current_timestamp":
                            current["timestamp"],
                        "gap_seconds":
                            gap_seconds,
                    }
                )

    if not intervals:
        return {
            "average": None,
            "minimum": None,
            "maximum": None,
            "large_gaps": [],
        }

    return {
        "average": (
            sum(intervals)
            / len(intervals)
        ),
        "minimum": min(intervals),
        "maximum": max(intervals),
        "large_gaps": large_gaps,
    }


# ============================================================
# BUILD REPORT
# ============================================================

def build_report():

    connection = get_connection()

    try:

        option_columns, market_columns = (
            validate_schema(connection)
        )

        records = load_option_records(
            connection
        )

        if not records:
            return {
                "status": "FAIL",
                "reason":
                    "No option snapshot records found.",
            }

        metadata = (
            build_snapshot_metadata(
                records
            )
        )

        incomplete_snapshots = (
            analyze_snapshot_completeness(
                metadata
            )
        )

        duplicate_contracts = (
            check_duplicate_contracts(
                records
            )
        )

        snapshots_with_multiple_timestamps = (
            check_snapshot_timestamp_consistency(
                records
            )
        )

        duplicate_snapshot_timestamps = (
            check_duplicate_snapshot_timestamps(
                records
            )
        )

        numeric_analysis = (
            check_numeric_data(
                records
            )
        )

        (
            orphan_option_records,
            market_snapshots_without_options,
        ) = check_market_links(
            connection,
            records,
        )

        sessions = get_sessions(
            metadata
        )

        interval_analysis = (
            analyze_intervals(
                sessions
            )
        )

        record_distribution = (
            get_record_count_distribution(
                metadata
            )
        )

        market_snapshot_count = (
            connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM market_snapshots
                """
            ).fetchone()["count"]
        )

        option_snapshot_count = len(
            metadata
        )

        problems = []

        if incomplete_snapshots:
            problems.append(
                "structurally incomplete snapshots"
            )

        if duplicate_contracts:
            problems.append(
                "duplicate contracts"
            )

        if snapshots_with_multiple_timestamps:
            problems.append(
                "multiple timestamps within a snapshot"
            )

        if duplicate_snapshot_timestamps:
            problems.append(
                "same timestamp used by multiple snapshot IDs"
            )

        if interval_analysis[
            "large_gaps"
        ]:
            problems.append(
                "large intraday collection gaps"
            )

        if numeric_analysis[
            "invalid_ltp"
        ]:
            problems.append("invalid LTP")

        if numeric_analysis[
            "invalid_oi"
        ]:
            problems.append("invalid OI")

        if numeric_analysis[
            "invalid_volume"
        ]:
            problems.append("invalid volume")

        if numeric_analysis[
            "invalid_iv"
        ]:
            problems.append("invalid IV")

        if numeric_analysis[
            "invalid_delta"
        ]:
            problems.append("invalid delta")

        if numeric_analysis[
            "invalid_gamma"
        ]:
            problems.append("invalid gamma")

        if numeric_analysis[
            "invalid_vega"
        ]:
            problems.append("invalid vega")

        if numeric_analysis[
            "invalid_bid_ask"
        ]:
            problems.append("invalid bid/ask")

        if orphan_option_records:
            problems.append(
                "orphan option records"
            )

        if market_snapshots_without_options:
            problems.append(
                "market snapshots without option records"
            )

        # OI mismatches are intentionally informational.
        if numeric_analysis[
            "oi_mismatches"
        ]:
            problems.append(
                "OI change mismatches (review separately)"
            )

        status = (
            "WARNING"
            if problems
            else "PASS"
        )

        return {
            "status": status,
            "option_columns":
                option_columns,
            "market_columns":
                market_columns,
            "total_records":
                len(records),
            "market_snapshot_count":
                market_snapshot_count,
            "option_snapshot_count":
                option_snapshot_count,
            "trading_sessions":
                sessions,
            "incomplete_snapshots":
                incomplete_snapshots,
            "duplicate_contracts":
                duplicate_contracts,
            "snapshots_with_multiple_timestamps":
                snapshots_with_multiple_timestamps,
            "duplicate_snapshot_timestamps":
                duplicate_snapshot_timestamps,
            "numeric_analysis":
                numeric_analysis,
            "orphan_option_records":
                orphan_option_records,
            "market_snapshots_without_options":
                market_snapshots_without_options,
            "interval_analysis":
                interval_analysis,
            "record_distribution":
                record_distribution,
            "problems":
                problems,
        }

    finally:
        connection.close()


# ============================================================
# DISPLAY
# ============================================================

def display_report(report):

    print()
    print("=" * 78)
    print(
        "NIFTY OPTION DATA QUALITY REPORT - READ ONLY"
    )
    print("=" * 78)

    if report["status"] == "FAIL":

        print()
        print(
            "DATA QUALITY STATUS : FAIL"
        )
        print()
        print(
            report["reason"]
        )
        print()
        print("=" * 78)
        return

    print()
    print("GENERAL SUMMARY")
    print("-" * 78)

    print(
        f"Total option records              : "
        f"{report['total_records']}"
    )

    print(
        f"Market snapshots                  : "
        f"{report['market_snapshot_count']}"
    )

    print(
        f"Snapshots containing options      : "
        f"{report['option_snapshot_count']}"
    )

    print(
        f"Trading sessions                  : "
        f"{len(report['trading_sessions'])}"
    )

    print()
    print("SNAPSHOT STRUCTURE")
    print("-" * 78)

    print(
        "Fixed expected record count       : NOT USED"
    )

    print(
        "Completeness rule                 : "
        "CE/PE strike parity + one timestamp + "
        "one expiry + unique contracts"
    )

    print(
        f"Structurally incomplete snapshots : "
        f"{len(report['incomplete_snapshots'])}"
    )

    if report["incomplete_snapshots"]:

        print()
        print(
            "First 20 structurally incomplete snapshots:"
        )

        for item in report[
            "incomplete_snapshots"
        ][:20]:

            print(
                f"  Snapshot {item['snapshot_id']} | "
                f"records={item['record_count']} | "
                f"CE={item['ce_count']} | "
                f"PE={item['pe_count']} | "
                f"strikes={item['strike_count']} | "
                f"{'; '.join(item['problems'])}"
            )

    print()
    print("RECORD COUNT DISTRIBUTION")
    print("-" * 78)

    distribution = report[
        "record_distribution"
    ]

    for count, frequency in sorted(
        distribution.items()
    ):

        print(
            f"  {count:>4} records/snapshot : "
            f"{frequency:>5} snapshots"
        )

    print()
    print("DUPLICATE / LINK INTEGRITY")
    print("-" * 78)

    print(
        f"Duplicate contracts               : "
        f"{len(report['duplicate_contracts'])}"
    )

    print(
        f"Snapshots with multiple timestamps: "
        f"{len(report['snapshots_with_multiple_timestamps'])}"
    )

    print(
        f"Duplicate snapshot timestamps     : "
        f"{len(report['duplicate_snapshot_timestamps'])}"
    )

    print(
        f"Orphan option records             : "
        f"{len(report['orphan_option_records'])}"
    )

    print(
        f"Market snapshots without options  : "
        f"{len(report['market_snapshots_without_options'])}"
    )

    print()
    print("NUMERIC DATA VALIDATION")
    print("-" * 78)

    numeric = report[
        "numeric_analysis"
    ]

    print(
        f"Invalid LTP                       : "
        f"{len(numeric['invalid_ltp'])}"
    )

    print(
        f"Invalid OI                        : "
        f"{len(numeric['invalid_oi'])}"
    )

    print(
        f"Invalid volume                    : "
        f"{len(numeric['invalid_volume'])}"
    )

    print(
        f"Invalid IV                        : "
        f"{len(numeric['invalid_iv'])}"
    )

    print(
        f"Invalid delta                     : "
        f"{len(numeric['invalid_delta'])}"
    )

    print(
        f"Invalid gamma                     : "
        f"{len(numeric['invalid_gamma'])}"
    )

    print(
        f"Invalid vega                      : "
        f"{len(numeric['invalid_vega'])}"
    )

    print(
        f"Invalid bid/ask                   : "
        f"{len(numeric['invalid_bid_ask'])}"
    )

    print(
        f"OI change mismatches              : "
        f"{len(numeric['oi_mismatches'])} "
        f"(informational)"
    )

    print()
    print("TIMESTAMP / COLLECTION ANALYSIS")
    print("-" * 78)

    interval = report[
        "interval_analysis"
    ]

    if interval["average"] is None:

        print(
            "Not enough valid snapshots "
            "for interval analysis."
        )

    else:

        print(
            f"Average intraday interval         : "
            f"{interval['average']:.2f} sec"
        )

        print(
            f"Minimum intraday interval         : "
            f"{interval['minimum']:.2f} sec"
        )

        print(
            f"Maximum intraday interval         : "
            f"{interval['maximum']:.2f} sec"
        )

        print(
            f"Large intraday gaps (>90 sec)     : "
            f"{len(interval['large_gaps'])}"
        )

        if interval["large_gaps"]:

            print()
            print(
                "First 10 large intraday gaps:"
            )

            for gap in interval[
                "large_gaps"
            ][:10]:

                print(
                    f"  {gap['trading_date']} | "
                    f"{gap['previous_id']} -> "
                    f"{gap['current_id']} | "
                    f"{gap['gap_seconds']:.2f} sec"
                )

    print()
    print("TRADING SESSIONS")
    print("-" * 78)

    for trading_date, snapshots in sorted(
        report["trading_sessions"].items()
    ):

        print(
            f"{trading_date} : "
            f"{len(snapshots)} snapshots"
        )

    print()
    print("OVERALL STATUS")
    print("-" * 78)

    print(
        f"DATA QUALITY STATUS                : "
        f"{report['status']}"
    )

    if report["problems"]:

        print()
        print(
            "Items requiring review:"
        )

        for problem in report[
            "problems"
        ]:

            print(
                f"  - {problem}"
            )

    else:

        print()
        print(
            "No structural or numeric "
            "data-quality problems detected."
        )

    print()
    print("=" * 78)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        report = build_report()

        display_report(
            report
        )

    except Exception as exc:

        print()
        print("=" * 78)
        print("INSPECTION ERROR")
        print("=" * 78)
        print()
        print(str(exc))
        print()
        print(
            "The database was opened in READ-ONLY mode. "
            "No data was modified."
        )
        print("=" * 78)
