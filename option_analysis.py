# ============================================================
# SAFE NUMBER
# ============================================================

def safe_number(value):

    if value is None:
        return 0.0

    try:
        return float(value)

    except (TypeError, ValueError):
        return 0.0


# ============================================================
# FIND ATM
# ============================================================

def find_atm(
    option_chain,
    spot_price
):

    return min(
        option_chain,
        key=lambda option: abs(
            safe_number(
                option.get("strike_price")
            ) - spot_price
        )
    )


# ============================================================
# SELECT ATM ± 5
# ============================================================

def select_atm_strikes(
    option_chain,
    atm_strike
):

    sorted_options = sorted(
        option_chain,
        key=lambda option: abs(
            safe_number(
                option.get("strike_price")
            ) - atm_strike
        )
    )

    selected = sorted_options[:11]

    return sorted(
        selected,
        key=lambda option:
        safe_number(
            option.get("strike_price")
        )
    )


# ============================================================
# GET MARKET DATA
# ============================================================

def get_market_data(
    option,
    option_type
):

    option_data = (
        option.get(option_type)
        or {}
    )

    return (
        option_data.get("market_data")
        or {}
    )


# ============================================================
# GET GREEKS
# ============================================================

def get_greeks(
    option,
    option_type
):

    option_data = (
        option.get(option_type)
        or {}
    )

    return (
        option_data.get("option_greeks")
        or {}
    )


# ============================================================
# GET CALL OI
# ============================================================

def get_call_oi(option):

    market_data = get_market_data(
        option,
        "call_options"
    )

    return safe_number(
        market_data.get("oi")
    )


# ============================================================
# GET PUT OI
# ============================================================

def get_put_oi(option):

    market_data = get_market_data(
        option,
        "put_options"
    )

    return safe_number(
        market_data.get("oi")
    )


# ============================================================
# OI ANALYSIS
# ============================================================

def calculate_oi_analysis(
    option_chain
):

    max_ce = max(
        option_chain,
        key=get_call_oi
    )

    max_pe = max(
        option_chain,
        key=get_put_oi
    )

    total_ce_oi = sum(
        get_call_oi(option)
        for option in option_chain
    )

    total_pe_oi = sum(
        get_put_oi(option)
        for option in option_chain
    )

    pcr = (
        total_pe_oi / total_ce_oi
        if total_ce_oi > 0
        else 0.0
    )

    return {

        "highest_ce_oi":
            get_call_oi(max_ce),

        "highest_ce_strike":
            safe_number(
                max_ce.get("strike_price")
            ),

        "highest_pe_oi":
            get_put_oi(max_pe),

        "highest_pe_strike":
            safe_number(
                max_pe.get("strike_price")
            ),

        "total_ce_oi":
            total_ce_oi,

        "total_pe_oi":
            total_pe_oi,

        "pcr":
            pcr
    }