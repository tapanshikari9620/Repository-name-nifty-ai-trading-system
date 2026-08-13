from upstox_api import get_option_chain
from feature_engine import (
    safe_number,
    find_atm,
    select_atm_strikes,
    calculate_option_features
)


def main():

    print("=" * 70)
    print("LIVE FEATURE ENGINE TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. GET LIVE OPTION CHAIN
    # --------------------------------------------------------

    option_chain = get_option_chain()

    if not option_chain:
        raise RuntimeError(
            "Upstox returned an empty option chain."
        )

    print(
        f"Option chain received: "
        f"{len(option_chain)} strikes"
    )

    # --------------------------------------------------------
    # 2. GET SPOT PRICE
    # --------------------------------------------------------

    spot_price = safe_number(
        option_chain[0].get(
            "underlying_spot_price"
        )
    )

    if spot_price <= 0:
        raise RuntimeError(
            "NIFTY spot price is unavailable."
        )

    print(
        f"NIFTY Spot Price : "
        f"{spot_price:.2f}"
    )

    # --------------------------------------------------------
    # 3. FIND ATM
    # --------------------------------------------------------

    atm_option = find_atm(
        option_chain,
        spot_price
    )

    atm_strike = safe_number(
        atm_option.get("strike_price")
    )

    print(
        f"ATM Strike       : "
        f"{atm_strike:.0f}"
    )

    # --------------------------------------------------------
    # 4. SELECT ATM ± 5
    # --------------------------------------------------------

    selected_options = select_atm_strikes(
        option_chain,
        atm_strike
    )

    print(
        f"Selected options : "
        f"{len(selected_options)}"
    )

    # --------------------------------------------------------
    # 5. CALCULATE FEATURES
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("CALCULATED FEATURES")
    print("=" * 70)

    for option in selected_options:

        feature = calculate_option_features(
            option
        )

        print()
        print(
            f"Strike: "
            f"{feature.get('strike')}"
        )

        for key, value in feature.items():

            print(
                f"{key:<25}: {value}"
            )

    # --------------------------------------------------------
    # 6. COMPLETED
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("LIVE FEATURE TEST COMPLETED")
    print("=" * 70)


if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        print()
        print("=" * 70)
        print("PROGRAM ERROR")
        print("=" * 70)
        print(error)