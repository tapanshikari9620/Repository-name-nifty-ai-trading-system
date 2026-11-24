
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3

from datetime import datetime, timezone


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = str(MARKET_DATABASE_PATH)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_NAME
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# INITIALIZE TABLE
# ============================================================

def initialize_collection_health_table():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS collection_health (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            timestamp_utc TEXT NOT NULL,

            market_snapshot_id INTEGER,

            status TEXT NOT NULL,

            http_status INTEGER,

            api_latency_ms REAL,

            collection_duration_ms REAL,

            spot_price REAL,

            option_records INTEGER,

            expected_option_records INTEGER,

            validation_status TEXT,

            error_type TEXT,

            error_message TEXT

        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_collection_health_timestamp

        ON collection_health(timestamp_utc)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_collection_health_status

        ON collection_health(status)
        """
    )

    connection.commit()

    connection.close()


# ============================================================
# LOG COLLECTION RESULT
# ============================================================

def log_collection_health(
    status,
    market_snapshot_id=None,
    http_status=None,
    api_latency_ms=None,
    collection_duration_ms=None,
    spot_price=None,
    option_records=None,
    expected_option_records=None,
    validation_status=None,
    error_type=None,
    error_message=None,
    timestamp_utc=None
):

    if timestamp_utc is None:

        timestamp_utc = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

    status = str(
        status
    ).upper()

    if status not in (
        "SUCCESS",
        "FAILED"
    ):

        raise ValueError(
            "status must be SUCCESS or FAILED."
        )

    initialize_collection_health_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO collection_health (

            timestamp_utc,
            market_snapshot_id,
            status,
            http_status,
            api_latency_ms,
            collection_duration_ms,
            spot_price,
            option_records,
            expected_option_records,
            validation_status,
            error_type,
            error_message

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,

        (
            timestamp_utc,
            market_snapshot_id,
            status,
            http_status,
            api_latency_ms,
            collection_duration_ms,
            spot_price,
            option_records,
            expected_option_records,
            validation_status,
            error_type,
            error_message
        )
    )

    connection.commit()

    health_id = cursor.lastrowid

    connection.close()

    return health_id


# ============================================================
# COUNT HEALTH RECORDS
# ============================================================

def count_health_records():

    initialize_collection_health_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM collection_health
        """
    )

    count = cursor.fetchone()[0]

    connection.close()

    return count


# ============================================================
# GET HEALTH SUMMARY
# ============================================================

def get_health_summary():

    initialize_collection_health_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT

            COUNT(*) AS total,

            SUM(
                CASE
                    WHEN status = 'SUCCESS'
                    THEN 1
                    ELSE 0
                END
            ) AS successful,

            SUM(
                CASE
                    WHEN status = 'FAILED'
                    THEN 1
                    ELSE 0
                END
            ) AS failed

        FROM collection_health
        """
    )

    row = cursor.fetchone()

    connection.close()

    return {
        "total": row["total"] or 0,
        "successful": row["successful"] or 0,
        "failed": row["failed"] or 0
    }


# ============================================================
# GET RECENT HEALTH RECORDS
# ============================================================

def get_recent_health_records(
    limit=20
):

    if limit <= 0:

        raise ValueError(
            "limit must be greater than zero."
        )

    initialize_collection_health_table()

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *

        FROM collection_health

        ORDER BY
            id DESC

        LIMIT ?
        """,
        (
            limit,
        )
    )

    rows = cursor.fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "COLLECTION HEALTH"
    )

    print("=" * 70)

    initialize_collection_health_table()

    summary = (
        get_health_summary()
    )

    print()

    print(
        "Collection health table initialized."
    )

    print()

    print(
        f"Total health records : "
        f"{summary['total']}"
    )

    print(
        f"Successful           : "
        f"{summary['successful']}"
    )

    print(
        f"Failed               : "
        f"{summary['failed']}"
    )

    print()

    print(
        "Available functions:"
    )

    print(
        "- initialize_collection_health_table()"
    )

    print(
        "- log_collection_health()"
    )

    print(
        "- count_health_records()"
    )

    print(
        "- get_health_summary()"
    )

    print(
        "- get_recent_health_records()"
    )

    print()

    print("=" * 70)