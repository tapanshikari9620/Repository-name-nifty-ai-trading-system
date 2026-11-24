
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3
import math
import os

from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = str(MARKET_DATABASE_PATH)

# Minimum research thresholds.
#
# These are intentionally conservative. Passing this report
# does NOT mean the model will be profitable.
#
MIN_FEATURE_SAMPLES = 1000

MIN_5M_SAMPLES = 500

MIN_15M_SAMPLES = 500

MIN_30M_SAMPLES = 500

MIN_60M_SAMPLES = 500

# We want more than one market regime.
MIN_BULLISH_SAMPLES = 50

MIN_BEARISH_SAMPLES = 50

MIN_FLAT_SAMPLES = 50

MIN_TRADING_SESSIONS = 120

MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        f"{Path(DATABASE_NAME).resolve().as_uri()}?mode=ro",
        uri=True
    )

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
# TABLE EXISTENCE
# ============================================================

def table_exists(
    table_name
):

    allowed_tables = {
        "market_features",
        "historical_outcomes"
    }

    if table_name not in allowed_tables:

        raise ValueError(
            f"Invalid table: {table_name}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM sqlite_master

        WHERE
            type = 'table'

            AND
            name = ?
        """,
        (
            table_name,
        )
    )

    exists = (
        cursor.fetchone()[0]
        > 0
    )

    connection.close()

    return exists


# ============================================================
# TOTAL FEATURE SAMPLES
# ============================================================

def get_total_feature_samples():

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
# TOTAL TRADING SESSIONS
# ============================================================

def get_trading_sessions():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT DISTINCT timestamp_utc
        FROM market_features
        """
    )

    timestamps = cursor.fetchall()

    connection.close()

    sessions = set()

    for row in timestamps:

        try:
            timestamp = datetime.fromisoformat(
                row["timestamp_utc"]
            )
        except (TypeError, ValueError):
            continue

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        timestamp_ist = timestamp.astimezone(
            MARKET_TIMEZONE
        )
        session_time = timestamp_ist.time().replace(
            tzinfo=None
        )

        if MARKET_OPEN <= session_time <= MARKET_CLOSE:
            sessions.add(timestamp_ist.date())

    return len(sessions)


# ============================================================
# OUTCOME SAMPLE COUNTS
# ============================================================

def get_outcome_counts():

    connection = get_connection()

    cursor = connection.cursor()

    counts = {}

    for horizon in (
        "5m",
        "15m",
        "30m",
        "60m"
    ):

        cursor.execute(
            f"""
            SELECT COUNT(*)

            FROM historical_outcomes

            WHERE
                outcome_{horizon}_valid = 1
            """
        )

        counts[horizon] = (
            cursor.fetchone()[0]
        )

    connection.close()

    return counts


# ============================================================
# DIRECTION DISTRIBUTION
# ============================================================

def get_direction_distribution(
    horizon
):

    allowed_horizons = {
        "5m",
        "15m",
        "30m",
        "60m"
    }

    if horizon not in allowed_horizons:

        raise ValueError(
            f"Invalid horizon: {horizon}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        f"""
        SELECT
            outcome_{horizon}_direction
                AS direction,

            COUNT(*) AS count

        FROM historical_outcomes

        WHERE
            outcome_{horizon}_valid = 1

        GROUP BY
            outcome_{horizon}_direction

        ORDER BY
            count DESC
        """
    )

    rows = cursor.fetchall()

    connection.close()

    distribution = {

        "BULLISH": 0,

        "BEARISH": 0,

        "FLAT": 0
    }

    for row in rows:

        direction = row[
            "direction"
        ]

        if direction in distribution:

            distribution[
                direction
            ] = row["count"]

    return distribution


# ============================================================
# VALID OUTCOME PERCENTAGE
# ============================================================

def calculate_valid_percentage(
    valid_count,
    total_count
):

    if total_count <= 0:

        return 0.0

    return (
        valid_count
        / total_count
    ) * 100.0


# ============================================================
# FEATURE / OUTCOME ALIGNMENT
# ============================================================

def get_alignment_report():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM market_features mf

        INNER JOIN historical_outcomes ho

            ON
                mf.market_snapshot_id
                =
                ho.market_snapshot_id
        """
    )

    aligned = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM market_features mf

        LEFT JOIN historical_outcomes ho

            ON
                mf.market_snapshot_id
                =
                ho.market_snapshot_id

        WHERE
            ho.market_snapshot_id IS NULL
        """
    )

    missing_outcomes = (
        cursor.fetchone()[0]
    )

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM historical_outcomes ho

        LEFT JOIN market_features mf

            ON
                mf.market_snapshot_id
                =
                ho.market_snapshot_id

        WHERE
            mf.market_snapshot_id IS NULL
        """
    )

    orphan_outcomes = (
        cursor.fetchone()[0]
    )

    connection.close()

    return {

        "aligned":
            aligned,

        "missing_outcomes":
            missing_outcomes,

        "orphan_outcomes":
            orphan_outcomes
    }


# ============================================================
# OUTCOME RETURN QUALITY
# ============================================================

def get_return_statistics(
    horizon
):

    allowed_horizons = {
        "5m",
        "15m",
        "30m",
        "60m"
    }

    if horizon not in allowed_horizons:

        raise ValueError(
            f"Invalid horizon: {horizon}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        f"""
        SELECT

            MIN(
                outcome_{horizon}_return_pct
            ),

            MAX(
                outcome_{horizon}_return_pct
            ),

            AVG(
                outcome_{horizon}_return_pct
            )

        FROM historical_outcomes

        WHERE
            outcome_{horizon}_valid = 1
        """
    )

    row = cursor.fetchone()

    connection.close()

    return {

        "min":
            row[0],

        "max":
            row[1],

        "average":
            row[2]
    }


# ============================================================
# COLLECTION CONTINUITY
# ============================================================

def get_continuity_report():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            timestamp_utc

        FROM market_features

        ORDER BY
            timestamp_utc ASC
        """
    )

    rows = cursor.fetchall()

    connection.close()

    if len(rows) < 2:

        return {

            "comparisons": 0,

            "continuous": 0,

            "large_gaps": 0,

            "max_gap_seconds": None
        }

    continuous = 0

    large_gaps = 0

    max_gap = 0.0

    from datetime import datetime

    previous = None

    for row in rows:

        current = datetime.fromisoformat(
            row["timestamp_utc"]
        )

        if previous is not None:

            gap = (
                current
                - previous
            ).total_seconds()

            if gap <= 90:

                continuous += 1

            else:

                large_gaps += 1

            if gap > max_gap:

                max_gap = gap

        previous = current

    return {

        "comparisons":
            len(rows) - 1,

        "continuous":
            continuous,

        "large_gaps":
            large_gaps,

        "max_gap_seconds":
            max_gap
    }


# ============================================================
# DATASET READINESS
# ============================================================

def calculate_readiness(
    total_features,
    outcome_counts,
    distributions,
    trading_sessions,
    alignment,
    continuity
):

    problems = []

    warnings = []

    # ========================================================
    # FEATURE SAMPLE SIZE
    # ========================================================

    if (
        total_features
        < MIN_FEATURE_SAMPLES
    ):

        problems.append(
            "Insufficient feature samples."
        )

    # ========================================================
    # TRADING SESSIONS
    # ========================================================

    if trading_sessions < MIN_TRADING_SESSIONS:

        problems.append(
            f"Insufficient trading sessions "
            f"({trading_sessions}/{MIN_TRADING_SESSIONS})."
        )

    # ========================================================
    # OUTCOME COUNTS
    # ========================================================

    minimums = {

        "5m":
            MIN_5M_SAMPLES,

        "15m":
            MIN_15M_SAMPLES,

        "30m":
            MIN_30M_SAMPLES,

        "60m":
            MIN_60M_SAMPLES
    }

    for horizon in minimums:

        if (
            outcome_counts[horizon]
            < minimums[horizon]
        ):

            problems.append(
                f"Insufficient "
                f"+{horizon} outcome samples."
            )

    # ========================================================
    # MARKET DIVERSITY
    # ========================================================

    for horizon in (
        "5m",
        "15m",
        "30m",
        "60m"
    ):

        distribution = (
            distributions[horizon]
        )

        if (
            distribution["BULLISH"]
            < MIN_BULLISH_SAMPLES
        ):

            warnings.append(
                f"+{horizon}: insufficient "
                "bullish samples."
            )

        if (
            distribution["BEARISH"]
            < MIN_BEARISH_SAMPLES
        ):

            warnings.append(
                f"+{horizon}: insufficient "
                "bearish samples."
            )

        if (
            distribution["FLAT"]
            < MIN_FLAT_SAMPLES
        ):

            warnings.append(
                f"+{horizon}: insufficient "
                "flat samples."
            )

    # ========================================================
    # ALIGNMENT
    # ========================================================

    if alignment[
        "missing_outcomes"
    ] > 0:

        warnings.append(
            "Some feature snapshots "
            "do not have outcome rows."
        )

    if alignment[
        "orphan_outcomes"
    ] > 0:

        problems.append(
            "Outcome rows exist without "
            "matching feature rows."
        )

    # ========================================================
    # CONTINUITY
    # ========================================================

    if continuity[
        "large_gaps"
    ] > 0:

        warnings.append(
            "Historical feature data "
            "contains collection gaps."
        )

    # ========================================================
    # FINAL READINESS
    # ========================================================

    ready = (
        len(problems) == 0
    )

    return {

        "ready":
            ready,

        "problems":
            problems,

        "warnings":
            warnings
    }


# ============================================================
# FULL QUALITY REPORT
# ============================================================

def build_quality_report():

    required_tables = [
        "market_features",
        "historical_outcomes"
    ]

    missing_tables = []

    for table in required_tables:

        if not table_exists(
            table
        ):

            missing_tables.append(
                table
            )

    if missing_tables:

        raise RuntimeError(
            "Missing required tables: "
            + ", ".join(
                missing_tables
            )
        )

    total_features = (
        get_total_feature_samples()
    )

    trading_sessions = (
        get_trading_sessions()
    )

    outcome_counts = (
        get_outcome_counts()
    )

    distributions = {}

    for horizon in (
        "5m",
        "15m",
        "30m",
        "60m"
    ):

        distributions[horizon] = (
            get_direction_distribution(
                horizon
            )
        )

    alignment = (
        get_alignment_report()
    )

    continuity = (
        get_continuity_report()
    )

    readiness = (
        calculate_readiness(
            total_features=
                total_features,

            outcome_counts=
                outcome_counts,

            distributions=
                distributions,

            trading_sessions=
                trading_sessions,

            alignment=
                alignment,

            continuity=
                continuity
        )
    )

    return {

        "total_features":
            total_features,

        "trading_sessions":
            trading_sessions,

        "outcome_counts":
            outcome_counts,

        "distributions":
            distributions,

        "alignment":
            alignment,

        "continuity":
            continuity,

        "readiness":
            readiness
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "NIFTY ML DATASET QUALITY REPORT"
    )

    print("=" * 70)

    try:

        report = (
            build_quality_report()
        )

    except Exception as error:

        print()

        print(
            "QUALITY REPORT FAILED"
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
    # BASIC DATASET
    # ========================================================

    print()

    print(
        "DATASET SIZE"
    )

    print("-" * 70)

    print(
        f"Feature snapshots : "
        f"{report['total_features']}"
    )

    print(
        f"Trading sessions  : "
        f"{report['trading_sessions']}"
    )

    # ========================================================
    # OUTCOME COVERAGE
    # ========================================================

    print()

    print(
        "OUTCOME COVERAGE"
    )

    print("-" * 70)

    for horizon in (
        "5m",
        "15m",
        "30m",
        "60m"
    ):

        count = (
            report[
                "outcome_counts"
            ][horizon]
        )

        total = (
            report[
                "total_features"
            ]
        )

        percentage = (
            calculate_valid_percentage(
                count,
                total
            )
        )

        print(
            f"+{horizon:<3} : "
            f"{count:6d} valid "
            f"({percentage:6.2f}%)"
        )

    # ========================================================
    # OUTCOME DISTRIBUTION
    # ========================================================

    print()

    print(
        "OUTCOME DISTRIBUTION"
    )

    print("-" * 70)

    for horizon in (
        "5m",
        "15m",
        "30m",
        "60m"
    ):

        distribution = (
            report[
                "distributions"
            ][horizon]
        )

        total = (
            sum(
                distribution.values()
            )
        )

        print()

        print(
            f"+{horizon.upper()}"
        )

        print(
            f"  BULLISH : "
            f"{distribution['BULLISH']:6d}"
        )

        print(
            f"  BEARISH : "
            f"{distribution['BEARISH']:6d}"
        )

        print(
            f"  FLAT    : "
            f"{distribution['FLAT']:6d}"
        )

        if total > 0:

            bullish_pct = (
                distribution[
                    "BULLISH"
                ]
                / total
            ) * 100

            bearish_pct = (
                distribution[
                    "BEARISH"
                ]
                / total
            ) * 100

            flat_pct = (
                distribution[
                    "FLAT"
                ]
                / total
            ) * 100

            print(
                f"  TOTAL   : "
                f"{total:6d}"
            )

            print(
                f"  MIX     : "
                f"B {bullish_pct:.1f}% | "
                f"BE {bearish_pct:.1f}% | "
                f"F {flat_pct:.1f}%"
            )

    # ========================================================
    # ALIGNMENT
    # ========================================================

    print()

    print(
        "FEATURE / OUTCOME ALIGNMENT"
    )

    print("-" * 70)

    print(
        f"Aligned rows          : "
        f"{report['alignment']['aligned']}"
    )

    print(
        f"Features without outcome: "
        f"{report['alignment']['missing_outcomes']}"
    )

    print(
        f"Orphan outcome rows   : "
        f"{report['alignment']['orphan_outcomes']}"
    )

    # ========================================================
    # CONTINUITY
    # ========================================================

    print()

    print(
        "TIME-SERIES CONTINUITY"
    )

    print("-" * 70)

    continuity = (
        report[
            "continuity"
        ]
    )

    print(
        f"Comparisons           : "
        f"{continuity['comparisons']}"
    )

    print(
        f"Continuous intervals  : "
        f"{continuity['continuous']}"
    )

    print(
        f"Large gaps            : "
        f"{continuity['large_gaps']}"
    )

    if (
        continuity[
            "max_gap_seconds"
        ]
        is not None
    ):

        print(
            f"Maximum gap           : "
            f"{continuity['max_gap_seconds']:.2f} sec"
        )

    # ========================================================
    # WARNINGS
    # ========================================================

    readiness = (
        report[
            "readiness"
        ]
    )

    if readiness[
        "warnings"
    ]:

        print()

        print(
            "WARNINGS"
        )

        print("-" * 70)

        for warning in (
            readiness[
                "warnings"
            ]
        ):

            print(
                f"  - {warning}"
            )

    # ========================================================
    # PROBLEMS
    # ========================================================

    if readiness[
        "problems"
    ]:

        print()

        print(
            "BLOCKING ISSUES"
        )

        print("-" * 70)

        for problem in (
            readiness[
                "problems"
            ]
        ):

            print(
                f"  - {problem}"
            )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    print()

    print("=" * 70)

    if readiness[
        "ready"
    ]:

        print(
            "RESEARCH DATA GATE : PASSED"
        )

        print()

        print(
            "Configured research-data "
            "thresholds are met. This does "
            "not establish ML-training or "
            "production readiness."
        )

    else:

        print(
            "RESEARCH DATA GATE : NOT MET"
        )

        print()

        print(
            "Continue collection and "
            "data-quality validation."
        )

    print("=" * 70)