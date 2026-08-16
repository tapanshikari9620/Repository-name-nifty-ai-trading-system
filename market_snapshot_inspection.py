import sqlite3
import logging

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


DATABASE_NAME = "nifty_market_data.db"

# ============================================================
# CONFIGURATION
# ============================================================

EXPECTED_INTERVAL_SECONDS = 60

MAX_ALLOWED_INTRADAY_INTERVAL_SECONDS = 90

MAX_REASONABLE_PRICE_CHANGE = 300.0

MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15

MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    try:
        connection = sqlite3.connect(
            DATABASE_NAME
        )

        connection.row_factory = sqlite3.Row

        # Validate connection with simple query
        connection.execute("SELECT 1")

        return connection

    except sqlite3.Error as error:
        logger.error(
            f"Database connection failed: {error}"
        )
        raise RuntimeError(
            f"Database connection failed: {error}"
        )


# ============================================================
# PARSE TIMESTAMP
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

    except (TypeError, ValueError):

        return None


# ============================================================
# CONVERT UTC → IST
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
# LOAD SNAPSHOTS
# ============================================================

def load_snapshots():

    connection = None

    try:
        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                timestamp_utc,
                spot_price

            FROM market_snapshots

            ORDER BY timestamp_utc ASC
            """
        )

        rows = cursor.fetchall()

        logger.info(
            f"Loaded {len(rows)} snapshots from database"
        )

        return rows

    except sqlite3.Error as error:
        logger.error(
            f"Failed to load snapshots from database: {error}"
        )
        raise RuntimeError(
            f"Failed to load snapshots from database: {error}"
        )

    finally:
        if connection:
            connection.close()


# ============================================================
# CHECK NSE MARKET SESSION
# ============================================================

def is_market_session(timestamp):

    ist_time = convert_to_ist(
        timestamp
    )

    if ist_time is None:
        return False

    market_open = ist_time.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0
    )

    market_close = ist_time.replace(
        hour=MARKET_CLOSE_HOUR,
        minute=MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )

    return (
        market_open
        <= ist_time
        <= market_close
    )


# ============================================================
# GROUP BY TRADING DATE
# ============================================================

def group_by_trading_date(
    snapshots
):

    sessions = {}

    for row in snapshots:

        timestamp_ist = convert_to_ist(
            row["timestamp_utc"]
        )

        if timestamp_ist is None:
            continue

        # Ignore observations outside
        # normal NSE trading hours.
        if not is_market_session(
            row["timestamp_utc"]
        ):
            continue

        trading_date = (
            timestamp_ist
            .date()
            .isoformat()
        )

        sessions.setdefault(
            trading_date,
            []
        ).append(row)

    return sessions


# ============================================================
# BASIC VALIDATION
# ============================================================

def validate_basic_data(
    snapshots
):

    invalid_prices = []

    invalid_timestamps = []

    for row in snapshots:

        snapshot_id = row["id"]

        price = row["spot_price"]

        timestamp = row[
            "timestamp_utc"
        ]

        if price is None or price <= 0:

            invalid_prices.append(
                snapshot_id
            )

        if parse_timestamp(
            timestamp
        ) is None:

            invalid_timestamps.append(
                snapshot_id
            )

    return {

        "invalid_prices":
            invalid_prices,

        "invalid_timestamps":
            invalid_timestamps

    }


# ============================================================
# SESSION INTERVAL ANALYSIS
# ============================================================

def analyze_session_intervals(
    session_snapshots
):

    intervals = []

    large_gaps = []

    for previous, current in zip(
        session_snapshots,
        session_snapshots[1:]
    ):

        previous_time = parse_timestamp(
            previous["timestamp_utc"]
        )

        current_time = parse_timestamp(
            current["timestamp_utc"]
        )

        if (
            previous_time is None
            or current_time is None
        ):
            continue

        interval = (
            current_time
            - previous_time
        ).total_seconds()

        intervals.append(
            interval
        )

        if (
            interval
            > MAX_ALLOWED_INTRADAY_INTERVAL_SECONDS
        ):

            large_gaps.append(
                {
                    "previous_id":
                        previous["id"],

                    "current_id":
                        current["id"],

                    "interval":
                        interval
                }
            )

    if not intervals:

        return {

            "intervals": [],

            "average": None,

            "minimum": None,

            "maximum": None,

            "large_gaps": []

        }

    return {

        "intervals":
            intervals,

        "average":
            sum(intervals)
            / len(intervals),

        "minimum":
            min(intervals),

        "maximum":
            max(intervals),

        "large_gaps":
            large_gaps

    }


# ============================================================
# DUPLICATE TIMESTAMP CHECK
# ============================================================

def find_duplicate_timestamps(
    snapshots
):

    timestamps = {}

    for row in snapshots:

        timestamp = row[
            "timestamp_utc"
        ]

        timestamps.setdefault(
            timestamp,
            []
        ).append(
            row["id"]
        )

    duplicates = {

        timestamp: ids

        for timestamp, ids
        in timestamps.items()

        if len(ids) > 1

    }

    return duplicates


# ============================================================
# PRICE MOVEMENT ANALYSIS
# ============================================================

def analyze_price_movements(
    session_snapshots
):

    movements = []

    suspicious_movements = []

    for previous, current in zip(
        session_snapshots,
        session_snapshots[1:]
    ):

        try:
            previous_price = float(
                previous["spot_price"]
            )

            current_price = float(
                current["spot_price"]
            )

        except (ValueError, TypeError) as error:
            logger.warning(
                f"Skipping price movement: "
                f"Cannot convert prices to float - "
                f"previous_id={previous['id']}, "
                f"current_id={current['id']}, "
                f"error={error}"
            )
            continue

        change = (
            current_price
            - previous_price
        )

        movements.append(
            {
                "previous_id":
                    previous["id"],

                "current_id":
                    current["id"],

                "change":
                    change
            }
        )

        if (
            abs(change)
            > MAX_REASONABLE_PRICE_CHANGE
        ):

            suspicious_movements.append(
                {
                    "previous_id":
                        previous["id"],

                    "current_id":
                        current["id"],

                    "previous_price":
                        previous_price,

                    "current_price":
                        current_price,

                    "change":
                        change
                }
            )

    return {

        "movements":
            movements,

        "suspicious_movements":
            suspicious_movements

    }


# ============================================================
# SESSION ANALYSIS
# ============================================================

def analyze_sessions(
    sessions
):

    session_reports = {}

    for (
        trading_date,
        snapshots
    ) in sessions.items():

        # Validate we can parse timestamps for this session
        first_ist = convert_to_ist(
            snapshots[0]["timestamp_utc"]
        )

        if first_ist is None:
            logger.warning(
                f"Skipping session {trading_date}: "
                f"Cannot parse first timestamp"
            )
            continue

        last_ist = convert_to_ist(
            snapshots[-1]["timestamp_utc"]
        )

        if last_ist is None:
            logger.warning(
                f"Skipping session {trading_date}: "
                f"Cannot parse last timestamp"
            )
            continue

        interval_analysis = (
            analyze_session_intervals(
                snapshots
            )
        )

        price_analysis = (
            analyze_price_movements(
                snapshots
            )
        )

        session_reports[
            trading_date
        ] = {

            "snapshot_count":
                len(snapshots),

            "first_timestamp":
                snapshots[0][
                    "timestamp_utc"
                ],

            "last_timestamp":
                snapshots[-1][
                    "timestamp_utc"
                ],

            "first_timestamp_ist":
                first_ist.isoformat(),

            "last_timestamp_ist":
                last_ist.isoformat(),

            "first_price":
                snapshots[0][
                    "spot_price"
                ],

            "last_price":
                snapshots[-1][
                    "spot_price"
                ],

            "average_interval":
                interval_analysis[
                    "average"
                ],

            "minimum_interval":
                interval_analysis[
                    "minimum"
                ],

            "maximum_interval":
                interval_analysis[
                    "maximum"
                ],

            "large_gaps":
                interval_analysis[
                    "large_gaps"
                ],

            "suspicious_movements":
                price_analysis[
                    "suspicious_movements"
                ]

        }

    return session_reports


# ============================================================
# DETERMINE QUALITY STATUS
# ============================================================

def determine_quality_status(
    snapshots,
    basic_validation,
    sessions,
    duplicate_timestamps
):

    if not snapshots:

        return "FAIL"

    if basic_validation[
        "invalid_prices"
    ]:

        return "FAIL"

    if basic_validation[
        "invalid_timestamps"
    ]:

        return "FAIL"

    if duplicate_timestamps:

        return "WARNING"

    for report in sessions.values():

        if report[
            "large_gaps"
        ]:

            return "WARNING"

        if report[
            "suspicious_movements"
        ]:

            return "WARNING"

    return "PASS"


# ============================================================
# BUILD REPORT
# ============================================================

def build_report():

    try:
        snapshots = load_snapshots()

    except RuntimeError as error:
        logger.error(
            f"Failed to build report: {error}"
        )
        return {
            "status": "FAIL",
            "reason": f"Database error: {error}"
        }

    if not snapshots:

        logger.warning(
            "No market snapshots found in database"
        )
        return {

            "status": "FAIL",

            "reason":
                "No market snapshots found."

        }

    logger.info(
        f"Starting validation for {len(snapshots)} snapshots"
    )

    basic_validation = (
        validate_basic_data(
            snapshots
        )
    )

    sessions = (
        group_by_trading_date(
            snapshots
        )
    )

    logger.info(
        f"Grouped {len(snapshots)} snapshots into "
        f"{len(sessions)} trading sessions"
    )

    session_reports = (
        analyze_sessions(
            sessions
        )
    )

    duplicate_timestamps = (
        find_duplicate_timestamps(
            snapshots
        )
    )

    status = (
        determine_quality_status(
            snapshots,
            basic_validation,
            session_reports,
            duplicate_timestamps
        )
    )

    logger.info(
        f"Validation complete - Status: {status}"
    )

    return {

        "status":
            status,

        "total_snapshots":
            len(snapshots),

        "sessions":
            session_reports,

        "duplicate_timestamps":
            duplicate_timestamps,

        "invalid_prices":
            basic_validation[
                "invalid_prices"
            ],

        "invalid_timestamps":
            basic_validation[
                "invalid_timestamps"
            ]

    }


# ============================================================
# DISPLAY REPORT
# ============================================================

def display_report(
    report
):

    print()

    print("=" * 70)

    print(
        "NIFTY MARKET DATA QUALITY REPORT"
    )

    print("=" * 70)

    if report["status"] == "FAIL":

        print()

        print(
            "STATUS :",
            report["status"]
        )

        print(
            "REASON :",
            report.get(
                "reason",
                "Unknown"
            )
        )

        return

    print()

    print(
        f"Total snapshots        : "
        f"{report['total_snapshots']}"
    )

    print(
        f"Trading sessions       : "
        f"{len(report['sessions'])}"
    )

    print()

    print(
        "SESSION ANALYSIS"
    )

    print("-" * 70)

    for (
        trading_date,
        session
    ) in report[
        "sessions"
    ].items():

        print()

        print(
            f"Trading date           : "
            f"{trading_date}"
        )

        print(
            f"Snapshots              : "
            f"{session['snapshot_count']}"
        )

        print(
            f"First snapshot UTC     : "
            f"{session['first_timestamp']}"
        )

        print(
            f"First snapshot IST     : "
            f"{session['first_timestamp_ist']}"
        )

        print(
            f"Last snapshot UTC      : "
            f"{session['last_timestamp']}"
        )

        print(
            f"Last snapshot IST      : "
            f"{session['last_timestamp_ist']}"
        )

        print(
            f"First NIFTY            : "
            f"{session['first_price']}"
        )

        print(
            f"Last NIFTY             : "
            f"{session['last_price']}"
        )

        if (
            session[
                "average_interval"
            ]
            is not None
        ):

            print(
                f"Average interval      : "
                f"{session['average_interval']:.2f} sec"
            )

            print(
                f"Minimum interval      : "
                f"{session['minimum_interval']:.2f} sec"
            )

            print(
                f"Maximum interval      : "
                f"{session['maximum_interval']:.2f} sec"
            )

        print(
            f"Intraday gaps         : "
            f"{len(session['large_gaps'])}"
        )

        print(
            f"Suspicious movements  : "
            f"{len(session['suspicious_movements'])}"
        )

    print()

    print(
        "GLOBAL VALIDATION"
    )

    print("-" * 70)

    print(
        f"Duplicate timestamps  : "
        f"{len(report['duplicate_timestamps'])}"
    )

    print(
        f"Invalid prices        : "
        f"{len(report['invalid_prices'])}"
    )

    print(
        f"Invalid timestamps    : "
        f"{len(report['invalid_timestamps'])}"
    )

    print()

    print("-" * 70)

    print(
        f"DATA QUALITY STATUS : "
        f"{report['status']}"
    )

    print("-" * 70)

    if report[
        "duplicate_timestamps"
    ]:

        print()

        print(
            "WARNING: Duplicate timestamps detected."
        )

        for (
            timestamp,
            ids
        ) in list(
            report[
                "duplicate_timestamps"
            ].items()
        )[:10]:

            print(
                f"  {timestamp} → {ids}"
            )

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