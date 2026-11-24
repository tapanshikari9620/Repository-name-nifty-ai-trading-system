from upstox_project.collector.upstox_api import get_option_chain

from upstox_project.collector.market_snapshot import (
    initialize_snapshot_table,
    store_snapshot,
    count_snapshots
)


def main():

    print()
    print("=" * 70)
    print("LIVE MARKET SNAPSHOT TEST")
    print("=" * 70)

    initialize_snapshot_table()

    option_chain = get_option_chain()

    if not option_chain:

        raise RuntimeError(
            "Option chain is empty."
        )

    spot_price = option_chain[0].get(
        "underlying_spot_price"
    )

    if spot_price is None:

        raise RuntimeError(
            "NIFTY spot price unavailable."
        )

    spot_price = float(
        spot_price
    )

    snapshot_id = store_snapshot(
        spot_price
    )

    print()
    print("=" * 70)
    print("SNAPSHOT STORED")
    print("=" * 70)

    print(
        f"Snapshot ID : {snapshot_id}"
    )

    print(
        f"NIFTY Spot  : {spot_price:.2f}"
    )

    print(
        f"Total snapshots : "
        f"{count_snapshots()}"
    )

    print()
    print("=" * 70)


if __name__ == "__main__":

    main()