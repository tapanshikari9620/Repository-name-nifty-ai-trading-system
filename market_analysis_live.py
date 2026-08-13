# ============================================================
# LIVE MARKET ANALYSIS TEST
# ============================================================
#
# Flow:
#
# Upstox API
#     ↓
# Option Chain
#     ↓
# Feature Engine
#     ↓
# Feature Validator
#     ↓
# Market Analyzer
#     ↓
# Market Structure
#
# This module does NOT:
#     - place orders
#     - generate BUY/SELL signals
#     - use AI/ML
#
# ============================================================

import sys

from upstox_api import get_option_chain

from feature_engine import (
    safe_number,
    find_atm,
    select_atm_strikes,
    build_option_features
)

from feature_validator import (
    validate_market_data
)

from market_analyzer import (
    analyze_market
)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("LIVE MARKET ANALYSIS TEST")
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
    # 2. GET NIFTY SPOT
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
    # 5. BUILD FEATURES
    # ========================================================

    features = build_option_features(
        selected_options
    )

    # ========================================================
    # 6. VALIDATE DATA
    # ========================================================

    validation_result = validate_market_data(
        spot_price=spot_price,
        atm_strike=atm_strike,
        selected_options=selected_options,
        features=features
    )

    print()
    print("=" * 70)
    print("DATA VALIDATION")
    print("=" * 70)

    print(
        f"Validation Status : "
        f"{'PASS' if validation_result['valid'] else 'FAIL'}"
    )

    if not validation_result["valid"]:

        print()
        print("Validation errors:")

        for error in validation_result["errors"]:
            print(
                f"- {error}"
            )

        raise RuntimeError(
            "Market analysis stopped because "
            "data validation failed."
        )

    # ========================================================
    # 7. RUN MARKET ANALYZER
    # ========================================================

    analysis = analyze_market(
        features,
        spot_price
    )

    # ========================================================
    # 8. DISPLAY BASIC MARKET DATA
    # ========================================================

    print()
    print("=" * 70)
    print("MARKET DATA")
    print("=" * 70)

    print(
        f"NIFTY Spot       : "
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

    # ========================================================
    # 9. DISPLAY OI ANALYSIS
    # ========================================================

    print()
    print("=" * 70)
    print("OI ANALYSIS")
    print("=" * 70)

    highest_ce_oi = (
        analysis["highest_ce_oi"]
    )

    highest_pe_oi = (
        analysis["highest_pe_oi"]
    )

    highest_ce_oi_change = (
        analysis["highest_ce_oi_change"]
    )

    highest_pe_oi_change = (
        analysis["highest_pe_oi_change"]
    )

    print(
        f"Highest CE OI : "
        f"{highest_ce_oi['ce_oi']:,.0f} "
        f"at {highest_ce_oi['strike']:.0f}"
    )

    print(
        f"Highest PE OI : "
        f"{highest_pe_oi['pe_oi']:,.0f} "
        f"at {highest_pe_oi['strike']:.0f}"
    )

    print(
        f"Total CE OI   : "
        f"{analysis['total_ce_oi']:,.0f}"
    )

    print(
        f"Total PE OI   : "
        f"{analysis['total_pe_oi']:,.0f}"
    )

    print(
        f"PCR           : "
        f"{analysis['pcr']:.2f}"
    )

    # ========================================================
    # 10. OI CHANGE ANALYSIS
    # ========================================================

    print()
    print("=" * 70)
    print("OI CHANGE ANALYSIS")
    print("=" * 70)

    print(
        f"Total CE OI Change : "
        f"{analysis['total_ce_oi_change']:,.0f}"
    )

    print(
        f"Total PE OI Change : "
        f"{analysis['total_pe_oi_change']:,.0f}"
    )

    print(
        f"OI Pressure        : "
        f"{analysis['oi_pressure']:,.0f}"
    )

    print()

    print(
        f"Highest CE OI Change : "
        f"{highest_ce_oi_change['ce_oi_change']:,.0f} "
        f"at {highest_ce_oi_change['strike']:.0f}"
    )

    print(
        f"Highest PE OI Change : "
        f"{highest_pe_oi_change['pe_oi_change']:,.0f} "
        f"at {highest_pe_oi_change['strike']:.0f}"
    )

    # ========================================================
    # 11. VOLUME ANALYSIS
    # ========================================================

    print()
    print("=" * 70)
    print("VOLUME ANALYSIS")
    print("=" * 70)

    print(
        f"Total CE Volume : "
        f"{analysis['total_ce_volume']:,.0f}"
    )

    print(
        f"Total PE Volume : "
        f"{analysis['total_pe_volume']:,.0f}"
    )

    print(
        f"Volume Pressure : "
        f"{analysis['volume_pressure']:,.0f}"
    )

    # ========================================================
    # 12. SUPPORT / RESISTANCE
    # ========================================================

    support = analysis["support"]
    resistance = analysis["resistance"]

    print()
    print("=" * 70)
    print("SUPPORT / RESISTANCE")
    print("=" * 70)

    if support:

        print(
            f"Support    : "
            f"{support['strike']:.0f}"
        )

        print(
            f"Support PE OI : "
            f"{support['pe_oi']:,.0f}"
        )

    else:

        print(
            "Support    : N/A"
        )

    if resistance:

        print(
            f"Resistance : "
            f"{resistance['strike']:.0f}"
        )

        print(
            f"Resistance CE OI : "
            f"{resistance['ce_oi']:,.0f}"
        )

    else:

        print(
            "Resistance : N/A"
        )

    # ========================================================
    # 13. MARKET STRUCTURE
    # ========================================================

    print()
    print("=" * 70)
    print("MARKET STRUCTURE")
    print("=" * 70)

    print(
        f"Structure : "
        f"{analysis['market_structure']}"
    )

    # ========================================================
    # 14. COMPLETED
    # ========================================================

    print()
    print("=" * 70)
    print("LIVE MARKET ANALYSIS COMPLETED")
    print("=" * 70)


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