# ============================================================
# MARKET ANALYZER
# ============================================================
#
# Responsibility:
#
# Convert validated option features into market-structure
# information.
#
# This module DOES NOT:
#   - place orders
#   - generate final BUY/SELL signals
#   - use machine learning
#
# It calculates:
#   - Support
#   - Resistance
#   - PCR
#   - CE/PE OI concentration
#   - CE/PE OI change
#   - CE/PE volume
#   - OI pressure
#   - Market structure
#
# ============================================================


# ============================================================
# 1. SAFE NUMBER
# ============================================================

def safe_number(value):
    """
    Convert value to float safely.
    """

    if value is None:
        return 0.0

    try:
        return float(value)

    except (TypeError, ValueError):
        return 0.0


# ============================================================
# 2. FIND HIGHEST CE OI
# ============================================================

def find_highest_ce_oi(features):
    """
    Find the strike having the highest Call OI.
    """

    if not features:
        return None

    return max(
        features,
        key=lambda feature: safe_number(
            feature.get("ce_oi")
        )
    )


# ============================================================
# 3. FIND HIGHEST PE OI
# ============================================================

def find_highest_pe_oi(features):
    """
    Find the strike having the highest Put OI.
    """

    if not features:
        return None

    return max(
        features,
        key=lambda feature: safe_number(
            feature.get("pe_oi")
        )
    )


# ============================================================
# 4. FIND HIGHEST CE OI CHANGE
# ============================================================

def find_highest_ce_oi_change(features):
    """
    Find the strike with the highest positive
    Call OI change.
    """

    if not features:
        return None

    return max(
        features,
        key=lambda feature: safe_number(
            feature.get("ce_oi_change")
        )
    )


# ============================================================
# 5. FIND HIGHEST PE OI CHANGE
# ============================================================

def find_highest_pe_oi_change(features):
    """
    Find the strike with the highest positive
    Put OI change.
    """

    if not features:
        return None

    return max(
        features,
        key=lambda feature: safe_number(
            feature.get("pe_oi_change")
        )
    )


# ============================================================
# 6. TOTAL CALL OI
# ============================================================

def calculate_total_ce_oi(features):
    """
    Calculate total Call OI across the supplied features.
    """

    return sum(
        safe_number(
            feature.get("ce_oi")
        )
        for feature in features
    )


# ============================================================
# 7. TOTAL PUT OI
# ============================================================

def calculate_total_pe_oi(features):
    """
    Calculate total Put OI across the supplied features.
    """

    return sum(
        safe_number(
            feature.get("pe_oi")
        )
        for feature in features
    )


# ============================================================
# 8. CALCULATE PCR
# ============================================================

def calculate_pcr(features):
    """
    Calculate Put/Call OI Ratio.

    PCR = Total PE OI / Total CE OI
    """

    total_ce_oi = calculate_total_ce_oi(
        features
    )

    total_pe_oi = calculate_total_pe_oi(
        features
    )

    if total_ce_oi <= 0:
        return 0.0

    return (
        total_pe_oi / total_ce_oi
    )


# ============================================================
# 9. TOTAL CE OI CHANGE
# ============================================================

def calculate_total_ce_oi_change(features):
    """
    Calculate total Call OI change.
    """

    return sum(
        safe_number(
            feature.get("ce_oi_change")
        )
        for feature in features
    )


# ============================================================
# 10. TOTAL PE OI CHANGE
# ============================================================

def calculate_total_pe_oi_change(features):
    """
    Calculate total Put OI change.
    """

    return sum(
        safe_number(
            feature.get("pe_oi_change")
        )
        for feature in features
    )


# ============================================================
# 11. TOTAL CE VOLUME
# ============================================================

def calculate_total_ce_volume(features):
    """
    Calculate total Call volume.
    """

    return sum(
        safe_number(
            feature.get("ce_volume")
        )
        for feature in features
    )


# ============================================================
# 12. TOTAL PE VOLUME
# ============================================================

def calculate_total_pe_volume(features):
    """
    Calculate total Put volume.
    """

    return sum(
        safe_number(
            feature.get("pe_volume")
        )
        for feature in features
    )


# ============================================================
# 13. FIND SUPPORT
# ============================================================

def find_support(features, spot_price):
    """
    Estimate support using the strongest Put OI below
    or at the spot price.

    We prefer Put OI below spot because large Put OI
    can represent an area of potential support.

    IMPORTANT:
    This is an analytical level, NOT a guaranteed support.
    """

    if not features:
        return None

    candidates = [
        feature
        for feature in features
        if safe_number(
            feature.get("strike")
        ) <= spot_price
    ]

    if not candidates:
        candidates = features

    return max(
        candidates,
        key=lambda feature: safe_number(
            feature.get("pe_oi")
        )
    )


# ============================================================
# 14. FIND RESISTANCE
# ============================================================

def find_resistance(features, spot_price):
    """
    Estimate resistance using the strongest Call OI
    above or at the spot price.

    We prefer Call OI above spot because large Call OI
    can represent an area of potential resistance.

    IMPORTANT:
    This is an analytical level, NOT a guaranteed resistance.
    """

    if not features:
        return None

    candidates = [
        feature
        for feature in features
        if safe_number(
            feature.get("strike")
        ) >= spot_price
    ]

    if not candidates:
        candidates = features

    return max(
        candidates,
        key=lambda feature: safe_number(
            feature.get("ce_oi")
        )
    )


# ============================================================
# 15. CALCULATE OI PRESSURE
# ============================================================

def calculate_oi_pressure(features):
    """
    Calculate aggregate OI-change pressure.

    Positive value:
        More Put OI addition relative to Call OI addition.

    Negative value:
        More Call OI addition relative to Put OI addition.

    This is a raw structural measure.
    It is NOT a trading signal.
    """

    ce_change = calculate_total_ce_oi_change(
        features
    )

    pe_change = calculate_total_pe_oi_change(
        features
    )

    return pe_change - ce_change


# ============================================================
# 16. CALCULATE VOLUME PRESSURE
# ============================================================

def calculate_volume_pressure(features):
    """
    Calculate the difference between total Put and Call
    volume.

    Positive:
        More Put volume.

    Negative:
        More Call volume.
    """

    ce_volume = calculate_total_ce_volume(
        features
    )

    pe_volume = calculate_total_pe_volume(
        features
    )

    return pe_volume - ce_volume


# ============================================================
# 17. DETERMINE MARKET STRUCTURE
# ============================================================

def determine_market_structure(
    spot_price,
    support,
    resistance
):
    """
    Determine the current position of spot relative to
    the calculated support and resistance.

    This is deliberately descriptive rather than predictive.
    """

    if support is None or resistance is None:
        return "UNKNOWN"

    support_strike = safe_number(
        support.get("strike")
    )

    resistance_strike = safe_number(
        resistance.get("strike")
    )

    if spot_price < support_strike:
        return "BELOW_SUPPORT"

    if spot_price > resistance_strike:
        return "ABOVE_RESISTANCE"

    return "INSIDE_RANGE"


# ============================================================
# 18. BUILD COMPLETE MARKET ANALYSIS
# ============================================================

def analyze_market(
    features,
    spot_price
):
    """
    Build a complete market-structure analysis.

    Returns a dictionary containing all calculated
    analytical information.
    """

    if not features:
        raise ValueError(
            "Cannot analyze empty features."
        )

    if spot_price <= 0:
        raise ValueError(
            "Invalid spot price."
        )

    # --------------------------------------------------------
    # Highest OI
    # --------------------------------------------------------

    highest_ce_oi = find_highest_ce_oi(
        features
    )

    highest_pe_oi = find_highest_pe_oi(
        features
    )

    # --------------------------------------------------------
    # Highest OI change
    # --------------------------------------------------------

    highest_ce_oi_change = (
        find_highest_ce_oi_change(
            features
        )
    )

    highest_pe_oi_change = (
        find_highest_pe_oi_change(
            features
        )
    )

    # --------------------------------------------------------
    # Support / Resistance
    # --------------------------------------------------------

    support = find_support(
        features,
        spot_price
    )

    resistance = find_resistance(
        features,
        spot_price
    )

    # --------------------------------------------------------
    # Totals
    # --------------------------------------------------------

    total_ce_oi = calculate_total_ce_oi(
        features
    )

    total_pe_oi = calculate_total_pe_oi(
        features
    )

    total_ce_oi_change = (
        calculate_total_ce_oi_change(
            features
        )
    )

    total_pe_oi_change = (
        calculate_total_pe_oi_change(
            features
        )
    )

    total_ce_volume = (
        calculate_total_ce_volume(
            features
        )
    )

    total_pe_volume = (
        calculate_total_pe_volume(
            features
        )
    )

    # --------------------------------------------------------
    # Ratios / pressures
    # --------------------------------------------------------

    pcr = calculate_pcr(
        features
    )

    oi_pressure = calculate_oi_pressure(
        features
    )

    volume_pressure = calculate_volume_pressure(
        features
    )

    # --------------------------------------------------------
    # Market structure
    # --------------------------------------------------------

    market_structure = (
        determine_market_structure(
            spot_price,
            support,
            resistance
        )
    )

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    return {

        "spot_price": spot_price,

        "highest_ce_oi": highest_ce_oi,

        "highest_pe_oi": highest_pe_oi,

        "highest_ce_oi_change":
            highest_ce_oi_change,

        "highest_pe_oi_change":
            highest_pe_oi_change,

        "support": support,

        "resistance": resistance,

        "total_ce_oi": total_ce_oi,

        "total_pe_oi": total_pe_oi,

        "total_ce_oi_change":
            total_ce_oi_change,

        "total_pe_oi_change":
            total_pe_oi_change,

        "total_ce_volume":
            total_ce_volume,

        "total_pe_volume":
            total_pe_volume,

        "pcr": pcr,

        "oi_pressure": oi_pressure,

        "volume_pressure": volume_pressure,

        "market_structure":
            market_structure
    }


# ============================================================
# 19. MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("MARKET ANALYZER")
    print("=" * 70)

    print(
        "Market analyzer loaded successfully."
    )

    print()
    print("Available functions:")

    print(
        " - find_highest_ce_oi()"
    )

    print(
        " - find_highest_pe_oi()"
    )

    print(
        " - find_highest_ce_oi_change()"
    )

    print(
        " - find_highest_pe_oi_change()"
    )

    print(
        " - calculate_total_ce_oi()"
    )

    print(
        " - calculate_total_pe_oi()"
    )

    print(
        " - calculate_pcr()"
    )

    print(
        " - find_support()"
    )

    print(
        " - find_resistance()"
    )

    print(
        " - calculate_oi_pressure()"
    )

    print(
        " - calculate_volume_pressure()"
    )

    print(
        " - determine_market_structure()"
    )

    print(
        " - analyze_market()"
    )

    print("=" * 70)