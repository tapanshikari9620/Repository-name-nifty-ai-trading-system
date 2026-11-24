from upstox_project.collector.upstox_api import get_option_chain

from upstox_project.analysis.option_analysis import (
    safe_number,
    find_atm,
    select_atm_strikes,
    calculate_oi_analysis,
    get_market_data,
    get_greeks
)

from upstox_project.analysis.display import (
    display_market_data,
    display_oi_analysis,
    display_option_chain
)

from upstox_project.signals.signal_engine import calculate_signal
# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 50)
    print("NIFTY OPTION CHAIN ANALYZER")
    print("=" * 50)

    # ========================================================
    # GET OPTION CHAIN
    # ========================================================

    option_chain = get_option_chain()


    # ========================================================
    # SPOT PRICE
    # ========================================================

    spot_price = safe_number(
        option_chain[0].get(
            "underlying_spot_price"
        )
    )

    if spot_price <= 0:

        raise RuntimeError(
            "NIFTY spot price unavailable."
        )

    # ========================================================
    # ATM
    # ========================================================

    atm_option = find_atm(
        option_chain,
        spot_price
    )

    atm_strike = safe_number(
        atm_option.get("strike_price")
    )

    # ========================================================
    # ATM ± 5
    # ========================================================

    selected_options = select_atm_strikes(
        option_chain,
        atm_strike
    )

    # ========================================================
    # OI ANALYSIS
    # ========================================================

    oi_analysis = calculate_oi_analysis(
        option_chain
    )
    # --------------------------------------------------------
    # 6. CALCULATE MARKET SIGNAL
    # --------------------------------------------------------

    signal = calculate_signal(
        option_chain,
        spot_price,
        atm_strike
    )

    # ========================================================
    # DISPLAY
    # ========================================================

    display_market_data(
        spot_price,
        atm_strike
    )

    display_oi_analysis(
        oi_analysis
    )
    print()
    print("=" * 80)
    print("MARKET SIGNAL")
    print("=" * 80)

    print(f"NIFTY Spot       : {signal['spot_price']:.2f}")
    print(f"ATM Strike       : {signal['atm_strike']:.0f}")
    print(f"Support          : {signal['support']:.0f}")
    print(f"Resistance       : {signal['resistance']:.0f}")
    print(f"PCR              : {signal['pcr']:.2f}")
    print(f"Market Bias      : {signal['bias']}")

    display_option_chain(
        selected_options,
        get_market_data,
        get_greeks,
        safe_number
    )

    # ========================================================
    # DONE
    # ========================================================

    print()
    print("=" * 50)
    print(
        "Option chain analysis completed."
    )
    print("=" * 50)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print("Program stopped by user.")

    except Exception as error:

        print()
        print("=" * 50)
        print("PROGRAM ERROR")
        print("=" * 50)
        print(error)