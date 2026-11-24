from datetime import datetime, timedelta, timezone

from upstox_project.collector.market_snapshot import (
    initialize_snapshot_table,
    store_snapshot,
    get_price_at_or_after
)


def main():

    print()
    print("=" * 70)
    print("MARKET SNAPSHOT TIMESTAMP VALIDATION")
    print("=" * 70)

    initialize_snapshot_table()

    # ========================================================
    # CREATE CONTROLLED TEST DATA
    # ========================================================

    base_time = datetime.now(
        timezone.utc
    ).replace(microsecond=0)

    print()
    print("Creating controlled test snapshots...")

    # Target = base time
    target_time = base_time

    # Snapshot exactly +10 seconds
    store_snapshot(
        24500.00,
        (
            base_time +
            timedelta(seconds=10)
        ).isoformat()
    )

    # Snapshot +60 seconds
    store_snapshot(
        24600.00,
        (
            base_time +
            timedelta(seconds=60)
        ).isoformat()
    )

    # Snapshot before target
    store_snapshot(
        24400.00,
        (
            base_time -
            timedelta(seconds=10)
        ).isoformat()
    )

    print("Test snapshots created.")

    # ========================================================
    # TEST 1
    # ========================================================

    print()
    print("-" * 70)
    print("TEST 1: Snapshot within allowed delay")
    print("-" * 70)

    result = get_price_at_or_after(
        target_time.isoformat(),
        max_delay_seconds=30
    )

    if result is not None:

        print("PASS")

        print(
            f"Price         : "
            f"{result['spot_price']}"
        )

        print(
            f"Delay seconds : "
            f"{result['delay_seconds']}"
        )

    else:

        print("FAIL")

    # ========================================================
    # TEST 2
    # ========================================================

    print()
    print("-" * 70)
    print("TEST 2: Snapshot beyond allowed delay")
    print("-" * 70)

    late_target = (
            base_time +
            timedelta(seconds=29)
    )

    result = get_price_at_or_after(
        late_target.isoformat(),
        max_delay_seconds=30
    )

    if result is None:

        print("PASS")

        print(
            "Snapshot beyond 30 seconds correctly rejected."
        )

    else:

        print("FAIL")

        print(
            f"Unexpected price : "
            f"{result['spot_price']}"
        )

        print(
            f"Delay seconds : "
            f"{result['delay_seconds']}"
        )

    # ========================================================
    # TEST 3
    # ========================================================

    print()
    print("-" * 70)
    print("TEST 3: Snapshot before target")
    print("-" * 70)

    future_target = (
        base_time +
        timedelta(seconds=5)
    )

    result = get_price_at_or_after(
        future_target.isoformat(),
        max_delay_seconds=30
    )

    if (
        result is not None
        and
        result["spot_price"] == 24500.00
    ):

        print("PASS")

        print(
            "Snapshot before target was ignored."
        )

    else:

        print("FAIL")

    # ========================================================
    # COMPLETED
    # ========================================================

    print()
    print("=" * 70)
    print("TIMESTAMP VALIDATION COMPLETED")
    print("=" * 70)


if __name__ == "__main__":

    main()