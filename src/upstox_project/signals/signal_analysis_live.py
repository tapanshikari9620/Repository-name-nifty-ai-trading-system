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
    build_evidence
)

from upstox_project.signals.signal_engine import (
    calculate_signal
)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("LIVE SIGNAL ANALYSIS TEST")
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
    # 6. VALIDATE MARKET DATA
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

    if not validation_result["valid"]:

        print(
            "Validation Status : FAIL"
        )

        for error in validation_result["errors"]:

            print(
                f"- {error}"
            )

        raise RuntimeError(
            "Signal analysis stopped because "
            "market data validation failed."
        )

    print(
        "Validation Status : PASS"
    )

    # ========================================================
    # 7. MARKET ANALYSIS
    # ========================================================

    analysis = analyze_market(
        features,
        spot_price
    )

    # Evidence engine expects spot price.
    analysis["spot_price"] = spot_price

    # ========================================================
    # 8. BUILD EVIDENCE
    # ========================================================

    evidence = build_evidence(
        analysis
    )

    # ========================================================
    # 9. CALCULATE SIGNAL
    # ========================================================

    signal = calculate_signal(
        evidence,
        analysis
    )

    # ========================================================
    # 10. MARKET SNAPSHOT
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

    if analysis.get("support"):

        print(
            f"Support          : "
            f"{analysis['support']['strike']:.0f}"
        )

    else:

        print(
            "Support          : N/A"
        )

    if analysis.get("resistance"):

        print(
            f"Resistance       : "
            f"{analysis['resistance']['strike']:.0f}"
        )

    else:

        print(
            "Resistance       : N/A"
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
    # 11. EVIDENCE
    # ========================================================

    print()
    print("=" * 70)
    print("EVIDENCE")
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
    # 12. SIGNAL RESULT
    # ========================================================

    print()
    print("=" * 70)
    print("SIGNAL RESULT")
    print("=" * 70)

    print(
        f"Bullish Score     : "
        f"{signal['bullish_score']}"
    )

    print(
        f"Bearish Score     : "
        f"{signal['bearish_score']}"
    )

    print(
        f"Net Score         : "
        f"{signal['net_score']}"
    )

    print(
        f"Bullish Evidence  : "
        f"{signal['bullish_evidence']}"
    )

    print(
        f"Bearish Evidence  : "
        f"{signal['bearish_evidence']}"
    )

    print(
        f"Neutral Evidence  : "
        f"{signal['neutral_evidence']}"
    )

    print(
        f"Confidence        : "
        f"{signal['confidence']:.2f}%"
    )

    print(
        f"Bias              : "
        f"{signal['bias']}"
    )

    print(
        f"Action            : "
        f"{signal['action']}"
    )

    # ========================================================
    # 13. SAFETY MESSAGE
    # ========================================================

    print()
    print("=" * 70)
    print("SAFETY")
    print("=" * 70)

    print(
        "No order was placed."
    )

    print(
        "Signal is for system testing only."
    )

    print(
        "Confidence is not a probability of profit."
    )

    # ========================================================
    # 14. COMPLETED
    # ========================================================

    print()
    print("=" * 70)
    print("LIVE SIGNAL ANALYSIS COMPLETED")
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