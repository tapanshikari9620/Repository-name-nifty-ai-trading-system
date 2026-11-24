import sys

from upstox_project.collector.upstox_api import get_option_chain

from upstox_project.features.feature_engine import (
    safe_number,
    find_atm,
    select_atm_strikes,
    build_option_features
)

from upstox_project.features.feature_validator import validate_market_data

from upstox_project.analysis.market_analyzer import analyze_market

from upstox_project.analysis.evidence_engine import (
    build_evidence,
    count_evidence
)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("LIVE EVIDENCE ANALYSIS TEST")
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
    # 2. GET SPOT PRICE
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
    # 6. VALIDATE
    # ========================================================

    validation_result = validate_market_data(
        spot_price=spot_price,
        atm_strike=atm_strike,
        selected_options=selected_options,
        features=features
    )

    if not validation_result["valid"]:

        print()
        print("=" * 70)
        print("VALIDATION FAILED")
        print("=" * 70)

        for error in validation_result["errors"]:
            print(
                f"- {error}"
            )

        raise RuntimeError(
            "Evidence analysis stopped because "
            "market data validation failed."
        )

    print()
    print("=" * 70)
    print("DATA VALIDATION")
    print("=" * 70)

    print("Validation Status : PASS")

    # ========================================================
    # 7. MARKET ANALYSIS
    # ========================================================

    analysis = analyze_market(
        features,
        spot_price
    )

    # ========================================================
    # 8. ADD SPOT PRICE TO ANALYSIS
    #
    # Evidence Engine uses spot_price when evaluating
    # support/resistance.
    # ========================================================

    analysis["spot_price"] = spot_price

    # ========================================================
    # 9. BUILD EVIDENCE
    # ========================================================

    evidence = build_evidence(
        analysis
    )

    # ========================================================
    # 10. COUNT EVIDENCE
    # ========================================================

    evidence_count = count_evidence(
        evidence
    )

    # ========================================================
    # 11. MARKET SNAPSHOT
    # ========================================================

    print()
    print("=" * 70)
    print("MARKET SNAPSHOT")
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
        f"Support          : "
        f"{analysis['support']['strike']:.0f}"
        if analysis.get("support")
        else "Support          : N/A"
    )

    print(
        f"Resistance       : "
        f"{analysis['resistance']['strike']:.0f}"
        if analysis.get("resistance")
        else "Resistance       : N/A"
    )

    print(
        f"PCR              : "
        f"{analysis['pcr']:.2f}"
    )

    print(
        f"Market Structure : "
        f"{analysis['market_structure']}"
    )

    # ========================================================
    # 12. EVIDENCE DETAILS
    # ========================================================

    print()
    print("=" * 70)
    print("EVIDENCE ANALYSIS")
    print("=" * 70)

    for item in evidence:

        factor = item.get(
            "factor",
            "UNKNOWN"
        )

        direction = item.get(
            "direction",
            "NEUTRAL"
        )

        strength = item.get(
            "strength",
            "WEAK"
        )

        print(
            f"{factor:<22}"
            f" Direction: {direction:<10}"
            f" Strength: {strength}"
        )

    # ========================================================
    # 13. EVIDENCE SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("EVIDENCE SUMMARY")
    print("=" * 70)

    print(
        f"Bullish Evidence : "
        f"{evidence_count['bullish']}"
    )

    print(
        f"Bearish Evidence : "
        f"{evidence_count['bearish']}"
    )

    print(
        f"Neutral Evidence : "
        f"{evidence_count['neutral']}"
    )

    print(
        f"Total Factors    : "
        f"{evidence_count['total']}"
    )

    # ========================================================
    # 14. IMPORTANT
    # ========================================================

    print()
    print("=" * 70)
    print("IMPORTANT")
    print("=" * 70)

    print(
        "Evidence analysis is informational only."
    )

    print(
        "No BUY/SELL decision is generated."
    )

    print(
        "No order is placed."
    )

    # ========================================================
    # 15. COMPLETED
    # ========================================================

    print()
    print("=" * 70)
    print("LIVE EVIDENCE ANALYSIS COMPLETED")
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