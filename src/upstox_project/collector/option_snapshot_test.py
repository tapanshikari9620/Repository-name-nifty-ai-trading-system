from datetime import datetime, timezone

from .upstox_api import get_option_chain

from .option_snapshot import (
    initialize_option_snapshot_table,
    store_option_snapshot,
    count_option_snapshots,
    count_by_option_type,
    get_snapshot_summary
)

from .market_snapshot import (
    store_snapshot
)



def main():
    # ============================================================

    # OPTION SNAPSHOT LIVE TEST

    # ============================================================


    print()

    print("=" * 70)

    print("OPTION SNAPSHOT LIVE TEST")

    print("=" * 70)



    # ============================================================

    # 1. INITIALIZE DATABASE

    # ============================================================


    initialize_option_snapshot_table()


    print()

    print("Option snapshot table initialized.")



    # ============================================================

    # 2. GET LIVE OPTION CHAIN

    # ============================================================


    print()

    print("Fetching live NIFTY option chain...")


    option_chain = get_option_chain()


    if not option_chain:


        raise RuntimeError(

            "Option chain is empty."

        )


    print()

    print(

        f"Option chain received : "

        f"{len(option_chain)} strikes"

    )



    # ============================================================

    # 3. FIND NIFTY SPOT

    # ============================================================


    spot_price = None



    for option in option_chain:


        # --------------------------------------------------------

        # Most likely location

        # --------------------------------------------------------


        if option.get(

            "underlying_spot_price"

        ) is not None:


            spot_price = option[

                "underlying_spot_price"

            ]


            break



    # ------------------------------------------------------------

    # Some Upstox responses may provide the underlying price

    # through nested structures.

    # ------------------------------------------------------------


    if spot_price is None:


        for option in option_chain:


            call_options = (

                option.get(

                    "call_options"

                )

                or {}

            )


            put_options = (

                option.get(

                    "put_options"

                )

                or {}

            )


            for option_side in (

                call_options,

                put_options

            ):


                if option_side.get(

                    "underlying_spot_price"

                ) is not None:


                    spot_price = (

                        option_side[

                            "underlying_spot_price"

                        ]

                    )


                    break


            if spot_price is not None:

                break



    # ------------------------------------------------------------

    # If spot price cannot be found, stop safely.

    # ------------------------------------------------------------


    if spot_price is None:


        raise RuntimeError(

            "Could not find NIFTY spot price "

            "inside the option-chain response. "

            "We will inspect the actual Upstox "

            "response instead of guessing."

        )



    spot_price = float(

        spot_price

    )


    if spot_price <= 0:


        raise RuntimeError(

            f"Invalid NIFTY spot price: "

            f"{spot_price}"

        )



    print(

        f"NIFTY Spot            : "

        f"{spot_price}"

    )



    # ============================================================

    # 4. CREATE MARKET SNAPSHOT

    # ============================================================


    timestamp_utc = (

        datetime.now(

            timezone.utc

        ).isoformat()

    )



    market_snapshot_id = store_snapshot(

        spot_price=spot_price,

        timestamp_utc=timestamp_utc

    )



    print()

    print(

        f"Market Snapshot ID    : "

        f"{market_snapshot_id}"

    )


    print(

        f"Timestamp UTC         : "

        f"{timestamp_utc}"

    )



    # ============================================================

    # 5. STORE OPTION CHAIN

    # ============================================================


    print()

    print(

        "Storing complete option chain..."

    )



    records_stored = store_option_snapshot(

        market_snapshot_id=market_snapshot_id,

        timestamp_utc=timestamp_utc,

        option_chain=option_chain

    )



    print()

    print(

        f"Option records stored : "

        f"{records_stored}"

    )



    # ============================================================

    # 6. DATABASE COUNTS

    # ============================================================


    total_records = (

        count_option_snapshots()

    )


    type_counts = (

        count_by_option_type()

    )



    print()

    print("=" * 70)

    print("DATABASE RESULT")

    print("=" * 70)


    print()


    print(

        f"Total option records  : "

        f"{total_records}"

    )


    print(

        f"CE records            : "

        f"{type_counts.get('CE', 0)}"

    )


    print(

        f"PE records            : "

        f"{type_counts.get('PE', 0)}"

    )



    # ============================================================

    # 7. VERIFY THIS SNAPSHOT

    # ============================================================


    print()

    print("=" * 70)

    print("SNAPSHOT VERIFICATION")

    print("=" * 70)



    summaries = get_snapshot_summary(

        market_snapshot_id

    )



    if not summaries:


        raise RuntimeError(

            "No option records found for "

            "the newly created market snapshot."

        )



    for summary in summaries:


        print()


        print(

            f"Market Snapshot ID   : "

            f"{summary['market_snapshot_id']}"

        )


        print(

            f"Timestamp             : "

            f"{summary['timestamp_utc']}"

        )


        print(

            f"Expiry                : "

            f"{summary['expiry']}"

        )


        print(

            f"Total option records  : "

            f"{summary['total_options']}"

        )


        print(

            f"CE records            : "

            f"{summary['ce_count']}"

        )


        print(

            f"PE records            : "

            f"{summary['pe_count']}"

        )



    # ============================================================

    # 8. VALIDATE RECORD COUNT

    # ============================================================


    expected_minimum = (

        len(option_chain) * 2

    )



    print()

    print("=" * 70)



    if records_stored >= expected_minimum:


        print(

            "OPTION SNAPSHOT TEST : PASS"

        )


        print()


        print(

            f"Expected minimum      : "

            f"{expected_minimum}"

        )


        print(

            f"Actual records        : "

            f"{records_stored}"

        )


    else:


        print(

            "OPTION SNAPSHOT TEST : FAIL"

        )


        print()


        print(

            f"Expected minimum      : "

            f"{expected_minimum}"

        )


        print(

            f"Actual records        : "

            f"{records_stored}"

        )



    print("=" * 70)


if __name__ == "__main__":
    main()
