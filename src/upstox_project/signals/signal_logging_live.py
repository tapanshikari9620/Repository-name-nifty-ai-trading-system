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

from upstox_project.analysis.market_analyzer import (
    analyze_market
)

from upstox_project.analysis.evidence_engine import (
    build_evidence
)

from upstox_project.signals.signal_engine import (
    calculate_signal
)

from upstox_project.signals.signal_logger import (
    initialize_database,
    log_signal,
    count_signals
)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("LIVE SIGNAL LOGGING TEST")
    print("=" * 70)

    # ========================================================
    # 1. INITIALIZE DATABASE
    # ========================================================

    initialize_database()

    print()
    print(
        "Database initialized."
    )

    # ========================================================
    # 2. GET OPTION CHAIN
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
    # 3. SPOT PRICE
    # ========================================================

    spot_price = safe_number(
        option_chain[0].get(
            "underlying_spot_price"
        )
    )

    if spot_price <= 0:

        raise RuntimeError(
            "Invalid NIFTY spot price."
        )

    # ========================================================
    # 4. ATM
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
    # 5. SELECT ATM ± 5
    # ========================================================

    selected_options = select_atm_strikes(
        option_chain,
        atm_strike,
        number_of_strikes=5
    )

    # ========================================================
    # 6. BUILD FEATURES
    # ========================================================

    features = build_option_features(
        selected_options
    )

    # ========================================================
    # 7. VALIDATE
    # ========================================================

    validation = validate_market_data(
        spot_price=spot_price,
        atm_strike=atm_strike,
        selected_options=selected_options,
        features=features
    )

    if not validation["valid"]:

        raise RuntimeError(
            "Market data validation failed."
        )

    print(
        "Validation Status : PASS"
    )

    # ========================================================
    # 8. MARKET ANALYSIS
    # ========================================================

    analysis = analyze_market(
        features,
        spot_price
    )

    # ========================================================
    # 9. EVIDENCE
    # ========================================================

    evidence = build_evidence(
        analysis
    )

    # ========================================================
    # 10. SIGNAL
    # ========================================================

    signal = calculate_signal(
        evidence,
        analysis
    )

    # ========================================================
    # 11. DISPLAY
    # ========================================================

    print()
    print("=" * 70)
    print("SIGNAL")
    print("=" * 70)

    print(
        f"Spot       : {spot_price:.2f}"
    )

    print(
        f"ATM        : {atm_strike:.0f}"
    )

    print(
        f"Bias       : {signal['bias']}"
    )

    print(
        f"Action     : {signal['action']}"
    )

    print(
        f"Confidence : "
        f"{signal['confidence']:.2f}%"
    )

    print(
        f"Bullish    : "
        f"{signal['bullish_score']}"
    )

    print(
        f"Bearish    : "
        f"{signal['bearish_score']}"
    )

    print(
        f"Net Score  : "
        f"{signal['net_score']}"
    )

    # ========================================================
    # 12. LOG
    # ========================================================

    signal_id = log_signal(

        spot_price=spot_price,

        atm_strike=atm_strike,

        analysis=analysis,

        evidence=evidence,

        signal=signal,

        option_features=features,

        raw_option_chain=option_chain

    )

    # ========================================================
    # 13. RESULT
    # ========================================================

    print()
    print("=" * 70)
    print("SIGNAL LOGGED")
    print("=" * 70)

    print(
        f"Signal ID : {signal_id}"
    )

    print(
        f"Total stored signals : "
        f"{count_signals()}"
    )

    print()
    print(
        "Future market outcomes will be attached "
        "to this signal later."
    )

    print()
    print(
        "No order was placed."
    )

    print()
    print("=" * 70)
    print("LIVE SIGNAL LOGGING COMPLETED")
    print("=" * 70)


# ============================================================
# ENTRY POINT
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