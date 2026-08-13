# ============================================================
# FEATURE ENGINE
# ============================================================
#
# Responsibility:
# Convert raw Upstox option-chain data into normalized
# option features.
#
# IMPORTANT:
# This module does NOT generate BUY / SELL signals.
#
# This module only:
#   1. Validates data
#   2. Finds ATM
#   3. Selects ATM ± N strikes
#   4. Extracts market data
#   5. Extracts Greeks
#   6. Calculates option features
# ============================================================


# ============================================================
# 1. SAFE NUMBER
# ============================================================

def safe_number(value):
    """
    Convert a value into float safely.

    None / invalid values are converted to 0.0.
    """

    if value is None:
        return 0.0

    try:
        return float(value)

    except (TypeError, ValueError):
        return 0.0


# ============================================================
# 2. FIND ATM STRIKE
# ============================================================

def find_atm(option_chain, spot_price):
    """
    Find the option strike closest to the NIFTY spot price.

    Returns:
        The complete option dictionary corresponding
        to the ATM strike.
    """

    if not option_chain:
        raise ValueError(
            "Option chain is empty."
        )

    if spot_price <= 0:
        raise ValueError(
            "Invalid spot price."
        )

    return min(
        option_chain,
        key=lambda option: abs(
            safe_number(
                option.get("strike_price")
            ) - spot_price
        )
    )


# ============================================================
# 3. SELECT ATM ± N STRIKES
# ============================================================

def select_atm_strikes(
    option_chain,
    atm_strike,
    number_of_strikes=5
):
    """
    Select ATM plus N strikes above and below ATM.

    Default:

        ATM - 5
        ATM - 4
        ATM - 3
        ATM - 2
        ATM - 1
        ATM
        ATM + 1
        ATM + 2
        ATM + 3
        ATM + 4
        ATM + 5

    Total = 11 strikes.
    """

    if not option_chain:
        raise ValueError(
            "Option chain is empty."
        )

    if atm_strike <= 0:
        raise ValueError(
            "Invalid ATM strike."
        )

    if number_of_strikes < 0:
        raise ValueError(
            "number_of_strikes cannot be negative."
        )

    sorted_options = sorted(
        option_chain,
        key=lambda option: abs(
            safe_number(
                option.get("strike_price")
            ) - atm_strike
        )
    )

    selected_options = sorted_options[
        :(number_of_strikes * 2) + 1
    ]

    selected_options = sorted(
        selected_options,
        key=lambda option: safe_number(
            option.get("strike_price")
        )
    )

    return selected_options


# ============================================================
# 4. GET MARKET DATA
# ============================================================

def get_market_data(option, option_type):
    """
    Return market_data for:

        call_options
        put_options
    """

    option_data = option.get(
        option_type
    ) or {}

    return option_data.get(
        "market_data"
    ) or {}


# ============================================================
# 5. GET GREEKS
# ============================================================

def get_greeks(option, option_type):
    """
    Return option_greeks for:

        call_options
        put_options
    """

    option_data = option.get(
        option_type
    ) or {}

    return option_data.get(
        "option_greeks"
    ) or {}


# ============================================================
# 6. CALCULATE OPTION FEATURES
# ============================================================

def calculate_option_features(option):
    """
    Calculate normalized features for one option strike.

    Returns a dictionary containing:

        Strike

        CALL:
            LTP
            OI
            Previous OI
            OI Change
            Volume
            IV
            Delta
            Gamma
            Theta
            Vega

        PUT:
            LTP
            OI
            Previous OI
            OI Change
            Volume
            IV
            Delta
            Gamma
            Theta
            Vega
    """

    # --------------------------------------------------------
    # STRIKE
    # --------------------------------------------------------

    strike = safe_number(
        option.get("strike_price")
    )


    # ========================================================
    # CALL
    # ========================================================

    call_market = get_market_data(
        option,
        "call_options"
    )

    call_greeks = get_greeks(
        option,
        "call_options"
    )


    # --------------------------------------------------------
    # CALL MARKET DATA
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # CALL GREEKS
    # --------------------------------------------------------

    ce_iv = safe_number(
        call_greeks.get("iv")
    )

    ce_delta = safe_number(
        call_greeks.get("delta")
    )

    ce_gamma = safe_number(
        call_greeks.get("gamma")
    )

    ce_theta = safe_number(
        call_greeks.get("theta")
    )

    ce_vega = safe_number(
        call_greeks.get("vega")
    )


    # ========================================================
    # PUT
    # ========================================================

    put_market = get_market_data(
        option,
        "put_options"
    )

    put_greeks = get_greeks(
        option,
        "put_options"
    )


    # --------------------------------------------------------
    # PUT MARKET DATA
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # PUT GREEKS
    # --------------------------------------------------------

    pe_iv = safe_number(
        put_greeks.get("iv")
    )

    pe_delta = safe_number(
        put_greeks.get("delta")
    )

    pe_gamma = safe_number(
        put_greeks.get("gamma")
    )

    pe_theta = safe_number(
        put_greeks.get("theta")
    )

    pe_vega = safe_number(
        put_greeks.get("vega")
    )


    # ========================================================
    # RETURN FEATURES
    # ========================================================

    return {

        # ----------------------------------------------------
        # STRIKE
        # ----------------------------------------------------

        "strike": strike,


        # ----------------------------------------------------
        # CALL FEATURES
        # ----------------------------------------------------

        "ce_ltp": ce_ltp,

        "ce_oi": ce_oi,

        "ce_prev_oi": ce_prev_oi,

        "ce_oi_change": ce_oi_change,

        "ce_volume": ce_volume,

        "ce_iv": ce_iv,

        "ce_delta": ce_delta,

        "ce_gamma": ce_gamma,

        "ce_theta": ce_theta,

        "ce_vega": ce_vega,


        # ----------------------------------------------------
        # PUT FEATURES
        # ----------------------------------------------------

        "pe_ltp": pe_ltp,

        "pe_oi": pe_oi,

        "pe_prev_oi": pe_prev_oi,

        "pe_oi_change": pe_oi_change,

        "pe_volume": pe_volume,

        "pe_iv": pe_iv,

        "pe_delta": pe_delta,

        "pe_gamma": pe_gamma,

        "pe_theta": pe_theta,

        "pe_vega": pe_vega,
    }


# ============================================================
# 7. BUILD FEATURES FOR COMPLETE OPTION CHAIN
# ============================================================

def build_option_features(option_chain):
    """
    Convert the complete option chain into
    a list of normalized feature dictionaries.
    """

    if not option_chain:
        return []

    features = []

    for option in option_chain:

        feature = calculate_option_features(
            option
        )

        features.append(
            feature
        )

    return features


# ============================================================
# 8. MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("FEATURE ENGINE")
    print("=" * 60)

    print(
        "Feature engine loaded successfully."
    )

    print(
        "Available functions:"
    )

    print(
        " - safe_number()"
    )

    print(
        " - find_atm()"
    )

    print(
        " - select_atm_strikes()"
    )

    print(
        " - get_market_data()"
    )

    print(
        " - get_greeks()"
    )

    print(
        " - calculate_option_features()"
    )

    print(
        " - build_option_features()"
    )

    print("=" * 60)