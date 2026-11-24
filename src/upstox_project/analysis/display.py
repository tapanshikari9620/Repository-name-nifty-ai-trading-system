# ============================================================
# MARKET DATA
# ============================================================

def display_market_data(
    spot_price,
    atm_strike
):

    print()
    print("=" * 100)
    print("NIFTY MARKET DATA")
    print("=" * 100)

    print(
        f"NIFTY Spot Price : "
        f"{spot_price:.2f}"
    )

    print(
        f"ATM Strike       : "
        f"{atm_strike:.0f}"
    )


# ============================================================
# OI ANALYSIS
# ============================================================

def display_oi_analysis(
    analysis
):

    print()
    print("=" * 100)
    print("OI ANALYSIS")
    print("=" * 100)

    print(
        f"Highest CE OI : "
        f"{analysis['highest_ce_oi']:,.0f} "
        f"at Strike "
        f"{analysis['highest_ce_strike']:.0f}"
    )

    print(
        f"Highest PE OI : "
        f"{analysis['highest_pe_oi']:,.0f} "
        f"at Strike "
        f"{analysis['highest_pe_strike']:.0f}"
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
        f"Overall PCR   : "
        f"{analysis['pcr']:.2f}"
    )


# ============================================================
# OPTION CHAIN
# ============================================================

def display_option_chain(
    selected_options,
    get_market_data,
    get_greeks,
    safe_number
):

    print()
    print("=" * 180)
    print(
        "NIFTY OPTION CHAIN - "
        "ATM ± 5 STRIKES"
    )
    print("=" * 180)

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    print(
        f"{'STRIKE':>8} "
        f"{'CE LTP':>10} "
        f"{'CE OI':>13} "
        f"{'CE OI CHG':>13} "
        f"{'CE VOL':>13} "
        f"{'CE IV':>9} "
        f"{'CE DELTA':>10} "
        f"{'PE LTP':>10} "
        f"{'PE OI':>13} "
        f"{'PE OI CHG':>13} "
        f"{'PE VOL':>13} "
        f"{'PE IV':>9} "
        f"{'PE DELTA':>10}"
    )

    print("-" * 180)

    # --------------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------------

    if not selected_options:

        print(
            "No option strikes available."
        )

        return

    print(
        f"Processing "
        f"{len(selected_options)} "
        f"selected strikes..."
    )

    # --------------------------------------------------------
    # PROCESS OPTIONS
    # --------------------------------------------------------

    for option in selected_options:

        strike = safe_number(
            option.get("strike_price")
        )

        # ====================================================
        # CALL
        # ====================================================

        call_market = get_market_data(
            option,
            "call_options"
        )

        call_greeks = get_greeks(
            option,
            "call_options"
        )

        ce_ltp = safe_number(
            call_market.get("ltp")
        )

        ce_oi = safe_number(
            call_market.get("oi")
        )

        ce_prev_oi = safe_number(
            call_market.get("prev_oi")
        )

        ce_volume = safe_number(
            call_market.get("volume")
        )

        ce_oi_change = (
            ce_oi - ce_prev_oi
        )

        ce_iv = safe_number(
            call_greeks.get("iv")
        )

        ce_delta = safe_number(
            call_greeks.get("delta")
        )

        # ====================================================
        # PUT
        # ====================================================

        put_market = get_market_data(
            option,
            "put_options"
        )

        put_greeks = get_greeks(
            option,
            "put_options"
        )

        pe_ltp = safe_number(
            put_market.get("ltp")
        )

        pe_oi = safe_number(
            put_market.get("oi")
        )

        pe_prev_oi = safe_number(
            put_market.get("prev_oi")
        )

        pe_volume = safe_number(
            put_market.get("volume")
        )

        pe_oi_change = (
            pe_oi - pe_prev_oi
        )

        pe_iv = safe_number(
            put_greeks.get("iv")
        )

        pe_delta = safe_number(
            put_greeks.get("delta")
        )

        # ====================================================
        # PRINT ROW
        # ====================================================

        print(
            f"{strike:>8.0f} "
            f"{ce_ltp:>10.2f} "
            f"{ce_oi:>13,.0f} "
            f"{ce_oi_change:>13,.0f} "
            f"{ce_volume:>13,.0f} "
            f"{ce_iv:>9.2f} "
            f"{ce_delta:>10.4f} "
            f"{pe_ltp:>10.2f} "
            f"{pe_oi:>13,.0f} "
            f"{pe_oi_change:>13,.0f} "
            f"{pe_volume:>13,.0f} "
            f"{pe_iv:>9.2f} "
            f"{pe_delta:>10.4f}"
        )