# ============================================================
# LIVE FEATURE VALIDATION TEST
# ============================================================
#
# Flow:
#
# Upstox API
#     ↓
# option_chain
#     ↓
# feature_engine
#     ↓
# feature_validator
#     ↓
# PASS / FAIL
#
# This module does NOT generate trading signals.
# ============================================================

import sys

from upstox_project.collector.upstox_api import get_option_chain

from upstox_project.features.feature_engine import (
    safe_number,
    find_atm,
    select_atm_strikes,
    build_option_features
)

from upstox_project.features.feature_validator import (
    validate_market_data
)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("LIVE FEATURE VALIDATION TEST")
    print("=" * 70)

    # ========================================================
    # 1. GET LIVE OPTION CHAIN
    # ========================================================

    option_chain = get_option_chain()

    if not option_chain:
        raise RuntimeError(
            "Upstox returned an empty option chain."
        )

    print(
        f"Option chain received: "
        f"{len(option_chain)} strikes"
    )

    # ========================================================
    # 2. GET NIFTY SPOT PRICE
    # ========================================================

    spot_price = safe_number(
        option_chain[0].get(
            "underlying_spot_price"
        )
    )

    if spot_price <= 0:
        raise RuntimeError(
            "NIFTY spot price is unavailable."
        )

    # ========================================================
    # 3. FIND ATM
    # ========================================================

    atm_option = find_atm(
        option_chain,
        spot_price
    )

    atm_strike = safe_number(
        atm_option.get(
            "strike_price"
        )
    )

    # ========================================================
    # 4. SELECT ATM ± 5
    # ========================================================

    selected_options = select_atm_strikes(
        option_chain,
        atm_strike,
        number_of_strikes=5
    )

    # ========================================================
    # 5. CALCULATE FEATURES
    # ========================================================

    features = build_option_features(
        selected_options
    )

    # ========================================================
    # 6. DISPLAY BASIC INFORMATION
    # ========================================================

    print()
    print("=" * 70)
    print("MARKET DATA")
    print("=" * 70)

    print(
        f"NIFTY Spot Price : "
        f"{spot_price:.2f}"
    )

    print(
        f"ATM Strike       : "
        f"{atm_strike:.0f}"
    )

    print(
        f"Selected Strikes : "
        f"{len(selected_options)}"
    )

    print(
        f"Calculated Features : "
        f"{len(features)}"
    )

    # ========================================================
    # 7. VALIDATE EVERYTHING
    # ========================================================

    validation_result = validate_market_data(
        spot_price=spot_price,
        atm_strike=atm_strike,
        selected_options=selected_options,
        features=features
    )

    # ========================================================
    # 8. DISPLAY VALIDATION RESULT
    # ========================================================

    print()
    print("=" * 70)
    print("VALIDATION RESULT")
    print("=" * 70)

    print(
        f"Overall Status : "
        f"{'PASS' if validation_result['valid'] else 'FAIL'}"
    )

    feature_result = (
        validation_result["feature_result"]
    )

    print(
        f"Total Features : "
        f"{feature_result['total']}"
    )

    print(
        f"Valid Features : "
        f"{feature_result['valid_count']}"
    )

    print(
        f"Invalid Features : "
        f"{feature_result['invalid_count']}"
    )

    # ========================================================
    # 9. DISPLAY ERRORS
    # ========================================================

    if validation_result["errors"]:

        print()
        print("=" * 70)
        print("VALIDATION ERRORS")
        print("=" * 70)

        for error in validation_result["errors"]:

            print(
                f"- {error}"
            )

        print()
        print(
            "DATA VALIDATION FAILED."
        )

        sys.exit(1)

    # ========================================================
    # 10. SUCCESS
    # ========================================================

    print()
    print("=" * 70)
    print("ALL LIVE FEATURE VALIDATION TESTS PASSED")
    print("=" * 70)

    print()
    print(
        "The live option-chain data passed "
        "the feature validation layer."
    )

    print()
    print(
        "Safe to proceed to the next analysis layer."
    )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print()
        print("=" * 70)
        print("PROGRAM ERROR")
        print("=" * 70)

        print(error)

        sys.exit(1)