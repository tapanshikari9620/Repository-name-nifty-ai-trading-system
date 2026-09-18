import time
import sqlite3
import msvcrt
import os

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from upstox_api import get_option_chain

from market_snapshot import (
    store_snapshot
)

from option_snapshot import (
    store_option_snapshot
)

from option_snapshot_validation import (
    validate_snapshot
)

from collection_health import (
    log_collection_health
)


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_NAME = "nifty_market_data.db"

COLLECTION_INTERVAL_SECONDS = 60

COLLECTOR_LOCK_FILE = (
    ".option_snapshot_collector.lock"
)

MARKET_TIMEZONE = ZoneInfo(
    "Asia/Kolkata"
)

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15

MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_NAME,
        timeout=30
    )

    connection.execute(
        "PRAGMA busy_timeout = 30000"
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def acquire_collector_lock():

    lock_path = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        COLLECTOR_LOCK_FILE
    )

    lock_handle = open(
        lock_path,
        "a+b"
    )

    lock_handle.seek(
        0,
        os.SEEK_END
    )

    if lock_handle.tell() == 0:

        lock_handle.write(b"1")
        lock_handle.flush()

    lock_handle.seek(0)

    try:

        msvcrt.locking(
            lock_handle.fileno(),
            msvcrt.LK_NBLCK,
            1
        )

    except OSError as error:

        lock_handle.close()

        raise RuntimeError(
            "Another option snapshot collector "
            "instance is already running."
        ) from error

    return lock_handle


def configure_database():

    connection = sqlite3.connect(
        DATABASE_NAME,
        timeout=30
    )

    try:

        connection.execute(
            "PRAGMA busy_timeout = 30000"
        )

        connection.execute(
            "PRAGMA journal_mode = WAL"
        )

        connection.commit()

    finally:

        connection.close()


# ============================================================
# CURRENT IST TIME
# ============================================================

def get_current_ist():

    return datetime.now(
        timezone.utc
    ).astimezone(
        MARKET_TIMEZONE
    )


# ============================================================
# MARKET SESSION CHECK
# ============================================================

def is_market_open():

    now = get_current_ist()

    # Saturday / Sunday

    if now.weekday() >= 5:

        return False

    market_open = now.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0
    )

    market_close = now.replace(
        hour=MARKET_CLOSE_HOUR,
        minute=MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )

    return (
        market_open
        <= now
        <= market_close
    )


# ============================================================
# OPTION CHAIN VALIDATION
# ============================================================

def validate_option_chain_response(
    option_chain
):

    errors = []

    if not option_chain:

        errors.append(
            "Option chain is empty."
        )

        return errors

    strikes = []

    ce_count = 0
    pe_count = 0

    for option in option_chain:

        strike = option.get(
            "strike_price"
        )

        if strike is None:

            errors.append(
                "Option record has no strike."
            )

            continue

        try:

            strike = float(
                strike
            )

        except (
            TypeError,
            ValueError
        ):

            errors.append(
                f"Invalid strike: {strike}"
            )

            continue

        if strike <= 0:

            errors.append(
                f"Invalid strike: {strike}"
            )

        strikes.append(
            strike
        )

        if option.get(
            "call_options"
        ):

            ce_count += 1

        if option.get(
            "put_options"
        ):

            pe_count += 1

    # Duplicate strike check

    if len(strikes) != len(
        set(strikes)
    ):

        errors.append(
            "Duplicate strikes detected."
        )

    # CE check

    if ce_count == 0:

        errors.append(
            "No CE records found."
        )

    # PE check

    if pe_count == 0:

        errors.append(
            "No PE records found."
        )

    return errors


# ============================================================
# EXTRACT NIFTY SPOT
# ============================================================

def extract_spot_price(
    option_chain
):

    spot_price = None

    # --------------------------------------------------------
    # Try top-level option record
    # --------------------------------------------------------

    for option in option_chain:

        value = option.get(
            "underlying_spot_price"
        )

        if value is not None:

            try:

                spot_price = float(
                    value
                )

                break

            except (
                TypeError,
                ValueError
            ):

                pass

    # --------------------------------------------------------
    # Try CE / PE
    # --------------------------------------------------------

    if spot_price is None:

        for option in option_chain:

            for side_name in (
                "call_options",
                "put_options"
            ):

                side = option.get(
                    side_name
                ) or {}

                value = side.get(
                    "underlying_spot_price"
                )

                if value is None:
                    continue

                try:

                    spot_price = float(
                        value
                    )

                    break

                except (
                    TypeError,
                    ValueError
                ):

                    pass

            if spot_price is not None:
                break

    if spot_price is None:

        raise RuntimeError(
            "NIFTY spot price could not "
            "be extracted from option chain."
        )

    if spot_price <= 0:

        raise RuntimeError(
            f"Invalid NIFTY spot price: "
            f"{spot_price}"
        )

    return spot_price


# ============================================================
# ROLLBACK SNAPSHOT
# ============================================================

def rollback_snapshot(
    market_snapshot_id
):

    if market_snapshot_id is None:
        return

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            DELETE FROM option_snapshots
            WHERE market_snapshot_id = ?
            """,
            (
                market_snapshot_id,
            )
        )

        cursor.execute(
            """
            DELETE FROM market_snapshots
            WHERE id = ?
            """,
            (
                market_snapshot_id,
            )
        )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# SAFE HEALTH LOGGER
# ============================================================

def write_health_record(
    status,
    collection_started,
    market_snapshot_id=None,
    api_latency_ms=None,
    collection_duration_ms=None,
    spot_price=None,
    option_records=None,
    expected_option_records=None,
    validation_status=None,
    error_type=None,
    error_message=None
):

    try:

        log_collection_health(

            status=status,

            market_snapshot_id=
                market_snapshot_id,

            api_latency_ms=
                api_latency_ms,

            collection_duration_ms=
                collection_duration_ms,

            spot_price=
                spot_price,

            option_records=
                option_records,

            expected_option_records=
                expected_option_records,

            validation_status=
                validation_status,

            error_type=
                error_type,

            error_message=
                error_message,

            timestamp_utc=
                collection_started
        )

    except Exception as health_error:

        # Health logging must never crash
        # the market-data collector.

        print()
        print(
            "[WARNING] Collection health "
            "logging failed:"
        )

        print(
            health_error
        )


# ============================================================
# COLLECT ONE SNAPSHOT
# ============================================================

def collect_one_snapshot():

    collection_start_monotonic = (
        time.monotonic()
    )

    collection_started = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    market_snapshot_id = None

    spot_price = None

    option_records = 0

    expected_option_records = None

    validation_status = None

    api_latency_ms = None

    try:

        print()
        print("-" * 70)

        current_ist = get_current_ist()

        print(
            f"Collection time IST : "
            f"{current_ist.isoformat()}"
        )

        # ====================================================
        # 1. API REQUEST
        # ====================================================

        print(
            "Fetching NIFTY option chain..."
        )

        api_start = time.monotonic()

        option_chain = get_option_chain()

        api_end = time.monotonic()

        api_latency_ms = (
            api_end
            - api_start
        ) * 1000

        # ====================================================
        # 2. RESPONSE VALIDATION
        # ====================================================

        response_errors = (
            validate_option_chain_response(
                option_chain
            )
        )

        if response_errors:

            raise RuntimeError(
                "Option chain validation failed: "
                + " | ".join(
                    response_errors
                )
            )

        print(
            f"Option chain received : "
            f"{len(option_chain)} strikes"
        )

        # ====================================================
        # 3. EXPECTED RECORD COUNT
        # ====================================================

        expected_option_records = (
            len(option_chain) * 2
        )

        # ====================================================
        # 4. NIFTY SPOT
        # ====================================================

        spot_price = extract_spot_price(
            option_chain
        )

        print(
            f"NIFTY Spot            : "
            f"{spot_price:.2f}"
        )

        # ====================================================
        # 5. SINGLE SNAPSHOT TIMESTAMP
        # ====================================================

        timestamp_utc = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        # ====================================================
        # 6. STORE MARKET SNAPSHOT
        # ====================================================

        market_snapshot_id = (
            store_snapshot(
                spot_price=spot_price,
                timestamp_utc=timestamp_utc
            )
        )

        print(
            f"Market Snapshot ID    : "
            f"{market_snapshot_id}"
        )

        try:

            # =================================================
            # 7. STORE COMPLETE OPTION CHAIN
            # =================================================

            option_records = (
                store_option_snapshot(
                    market_snapshot_id=
                        market_snapshot_id,

                    timestamp_utc=
                        timestamp_utc,

                    option_chain=
                        option_chain
                )
            )

            print(
                f"Option records stored : "
                f"{option_records}"
            )

            # =================================================
            # 8. RECORD COUNT VALIDATION
            # =================================================

            if option_records <= 0:

                raise RuntimeError(
                    "No option records were stored."
                )

            if (
                option_records
                != expected_option_records
            ):

                raise RuntimeError(
                    "Option record count mismatch. "
                    f"Expected "
                    f"{expected_option_records}, "
                    f"stored "
                    f"{option_records}."
                )

            # =================================================
            # 9. DATABASE VALIDATION
            # =================================================

            validation_result = (
                validate_snapshot(
                    market_snapshot_id
                )
            )

            # -------------------------------------------------
            # Support either:
            #
            # True / False
            #
            # OR
            #
            # {"valid": True, ...}
            # -------------------------------------------------

            if isinstance(
                validation_result,
                dict
            ):

                is_valid = (
                    validation_result.get(
                        "valid",
                        False
                    )
                )

                validation_error = (
                    validation_result.get(
                        "errors",
                        []
                    )
                )

            else:

                is_valid = bool(
                    validation_result
                )

                validation_error = []

            if not is_valid:

                validation_status = (
                    "FAIL"
                )

                raise RuntimeError(
                    "Stored option snapshot "
                    "failed validation: "
                    f"{validation_error}"
                )

            validation_status = (
                "PASS"
            )

            # =================================================
            # 10. SUCCESS
            # =================================================

            collection_duration_ms = (
                time.monotonic()
                - collection_start_monotonic
            ) * 1000

            write_health_record(

                status="SUCCESS",

                collection_started=
                    collection_started,

                market_snapshot_id=
                    market_snapshot_id,

                api_latency_ms=
                    api_latency_ms,

                collection_duration_ms=
                    collection_duration_ms,

                spot_price=
                    spot_price,

                option_records=
                    option_records,

                expected_option_records=
                    expected_option_records,

                validation_status=
                    validation_status
            )

            print()
            print(
                "[SUCCESS] Snapshot committed."
            )

            print(
                f"Timestamp UTC         : "
                f"{timestamp_utc}"
            )

            print(
                f"NIFTY                 : "
                f"{spot_price:.2f}"
            )

            print(
                f"Option records        : "
                f"{option_records}"
            )

            print(
                f"API latency           : "
                f"{api_latency_ms:.2f} ms"
            )

            print(
                f"Collection duration   : "
                f"{collection_duration_ms:.2f} ms"
            )

            print(
                "Validation             : PASS"
            )

            print(
                "Health                 : SUCCESS"
            )

            return {
                "success": True,

                "market_snapshot_id":
                    market_snapshot_id,

                "timestamp_utc":
                    timestamp_utc,

                "spot_price":
                    spot_price,

                "option_records":
                    option_records,

                "api_latency_ms":
                    api_latency_ms,

                "validation_status":
                    validation_status
            }

        except Exception:

            # ================================================
            # ROLLBACK
            # ================================================

            try:

                rollback_snapshot(
                    market_snapshot_id
                )

                print()
                print(
                    "[ROLLBACK] Invalid snapshot "
                    "removed from database."
                )

            except Exception as rollback_error:

                print()
                print(
                    "[CRITICAL] Rollback failed:"
                )

                print(
                    rollback_error
                )

            raise

    except Exception as error:

        # ====================================================
        # FAILED COLLECTION
        # ====================================================

        collection_duration_ms = (
            time.monotonic()
            - collection_start_monotonic
        ) * 1000

        error_type = (
            type(error).__name__
        )

        error_message = str(
            error
        )

        write_health_record(

            status="FAILED",

            collection_started=
                collection_started,

            market_snapshot_id=
                market_snapshot_id,

            api_latency_ms=
                api_latency_ms,

            collection_duration_ms=
                collection_duration_ms,

            spot_price=
                spot_price,

            option_records=
                option_records,

            expected_option_records=
                expected_option_records,

            validation_status=
                validation_status,

            error_type=
                error_type,

            error_message=
                error_message
        )

        print()
        print(
            "[FAILED] Snapshot collection."
        )

        print(
            f"Error type           : "
            f"{error_type}"
        )

        print(
            f"Error message        : "
            f"{error_message}"
        )

        print(
            f"Collection duration  : "
            f"{collection_duration_ms:.2f} ms"
        )

        return {
            "success": False,

            "market_snapshot_id":
                market_snapshot_id,

            "spot_price":
                spot_price,

            "option_records":
                option_records,

            "error_type":
                error_type,

            "error_message":
                error_message
        }


# ============================================================
# WAIT UNTIL MARKET OPENS
# ============================================================

def wait_until_market_open():

    while True:

        now = get_current_ist()

        if is_market_open():

            return

        print()
        print(
            f"Market closed. "
            f"Current IST: "
            f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print(
            "Waiting 60 seconds..."
        )

        time.sleep(
            60
        )


# ============================================================
# MAIN COLLECTOR
# ============================================================

def run_collector():

    try:

        collector_lock = (
            acquire_collector_lock()
        )

        configure_database()

    except RuntimeError as error:

        print()
        print(
            f"[COLLECTOR NOT STARTED] {error}"
        )

        return

    print()
    print("=" * 70)

    print(
        "NIFTY OPTION SNAPSHOT COLLECTOR"
    )

    print("=" * 70)

    print()

    print(
        f"Collection interval : "
        f"{COLLECTION_INTERVAL_SECONDS} seconds"
    )

    print(
        f"Database             : "
        f"{DATABASE_NAME}"
    )

    print()

    print(
        "Collection Health    : ENABLED"
    )

    print()

    print(
        "Collector started."
    )

    print(
        "Press Ctrl+C to stop."
    )

    print()

    next_run = time.monotonic()

    while True:

        try:

            # =================================================
            # MARKET SESSION
            # =================================================

            if not is_market_open():

                wait_until_market_open()

                next_run = (
                    time.monotonic()
                )

            # =================================================
            # COLLECTION
            # =================================================

            collect_one_snapshot()

            # =================================================
            # NEXT SCHEDULED RUN
            # =================================================

            next_run += (
                COLLECTION_INTERVAL_SECONDS
            )

            sleep_seconds = (
                next_run
                - time.monotonic()
            )

            if sleep_seconds < 0:

                next_run = (
                    time.monotonic()
                )

                sleep_seconds = 0

            print()

            print(
                f"Next collection in "
                f"{sleep_seconds:.1f} seconds."
            )

            if sleep_seconds > 0:

                time.sleep(
                    sleep_seconds
                )

        except KeyboardInterrupt:

            print()
            print()

            print(
                "=" * 70
            )

            print(
                "OPTION SNAPSHOT COLLECTOR STOPPED"
            )

            print(
                "=" * 70
            )

            break

        except Exception as error:

            print()
            print(
                "[CRITICAL LOOP ERROR]"
            )

            print(
                error
            )

            print(
                "Collector will retry in "
                "10 seconds."
            )

            time.sleep(
                10
            )

    collector_lock.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    run_collector()