from datetime import datetime, timezone

from market_snapshot import (
    get_nearest_price,
    count_snapshots
)


def main():

    print()
    print("=" * 70)
    print("MARKET SNAPSHOT LOOKUP TEST")
    print("=" * 70)

    print(
        f"Stored snapshots : {count_snapshots()}"
    )

    target_time = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    print()
    print(
        "Target timestamp:"
    )

    print(target_time)

    result = get_nearest_price(
        target_time
    )

    print()
    print("=" * 70)
    print("LOOKUP RESULT")
    print("=" * 70)

    if result is None:

        print(
            "No snapshot found."
        )

    else:

        print(
            f"Snapshot timestamp : "
            f"{result['timestamp_utc']}"
        )

        print(
            f"NIFTY Spot         : "
            f"{result['spot_price']:.2f}"
        )

    print()
    print("=" * 70)


if __name__ == "__main__":

    main()