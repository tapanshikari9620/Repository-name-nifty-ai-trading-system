# ============================================================
# EVIDENCE ENGINE
# ============================================================
#
# Responsibility:
#
# Convert market-analysis output into independent evidence
# factors.
#
# IMPORTANT:
# This module DOES NOT:
#   - place orders
#   - select an option to buy
#   - guarantee direction
#   - use machine learning
#
# It only measures evidence.
# ============================================================


# ============================================================
# 1. SAFE NUMBER
# ============================================================

def safe_number(value):
    """
    Convert a value into float safely.
    """

    if value is None:
        return 0.0

    try:
        return float(value)

    except (TypeError, ValueError):
        return 0.0


# ============================================================
# 2. PCR EVIDENCE
# ============================================================

def evaluate_pcr(pcr):
    """
    Evaluate PCR as one evidence factor.

    IMPORTANT:
    These thresholds are intentionally simple starting
    thresholds. They are NOT proven trading thresholds.

    Returns:
        bullish / bearish / neutral
    """

    pcr = safe_number(pcr)

    if pcr >= 1.00:
        return {
            "factor": "PCR",
            "value": pcr,
            "direction": "BULLISH",
            "strength": "MODERATE"
        }

    if pcr <= 0.70:
        return {
            "factor": "PCR",
            "value": pcr,
            "direction": "BEARISH",
            "strength": "MODERATE"
        }

    return {
        "factor": "PCR",
        "value": pcr,
        "direction": "NEUTRAL",
        "strength": "WEAK"
    }


# ============================================================
# 3. OI CHANGE EVIDENCE
# ============================================================

def evaluate_oi_change(
    total_ce_oi_change,
    total_pe_oi_change
):
    """
    Compare Call OI addition against Put OI addition.

    More CE OI addition:
        potentially bearish pressure.

    More PE OI addition:
        potentially bullish pressure.

    This is evidence only.
    """

    ce_change = safe_number(
        total_ce_oi_change
    )

    pe_change = safe_number(
        total_pe_oi_change
    )

    if ce_change > pe_change:
        return {
            "factor": "OI_CHANGE",
            "ce_oi_change": ce_change,
            "pe_oi_change": pe_change,
            "direction": "BEARISH",
            "strength": "MODERATE"
        }

    if pe_change > ce_change:
        return {
            "factor": "OI_CHANGE",
            "ce_oi_change": ce_change,
            "pe_oi_change": pe_change,
            "direction": "BULLISH",
            "strength": "MODERATE"
        }

    return {
        "factor": "OI_CHANGE",
        "ce_oi_change": ce_change,
        "pe_oi_change": pe_change,
        "direction": "NEUTRAL",
        "strength": "WEAK"
    }


# ============================================================
# 4. VOLUME EVIDENCE
# ============================================================

def evaluate_volume(
    total_ce_volume,
    total_pe_volume
):
    """
    Compare Put and Call volume.

    This does NOT assume that volume automatically means
    buying or selling.

    It only reports the imbalance.
    """

    ce_volume = safe_number(
        total_ce_volume
    )

    pe_volume = safe_number(
        total_pe_volume
    )

    if pe_volume > ce_volume:
        return {
            "factor": "VOLUME",
            "ce_volume": ce_volume,
            "pe_volume": pe_volume,
            "direction": "BULLISH",
            "strength": "WEAK"
        }

    if ce_volume > pe_volume:
        return {
            "factor": "VOLUME",
            "ce_volume": ce_volume,
            "pe_volume": pe_volume,
            "direction": "BEARISH",
            "strength": "WEAK"
        }

    return {
        "factor": "VOLUME",
        "ce_volume": ce_volume,
        "pe_volume": pe_volume,
        "direction": "NEUTRAL",
        "strength": "WEAK"
    }


# ============================================================
# 5. SUPPORT / RESISTANCE EVIDENCE
# ============================================================

def evaluate_support_resistance(
    spot_price,
    support,
    resistance
):
    """
    Evaluate where spot is positioned relative to
    calculated support and resistance.

    This is positional evidence only.
    """

    spot = safe_number(
        spot_price
    )

    if not support or not resistance:
        return {
            "factor": "SUPPORT_RESISTANCE",
            "direction": "NEUTRAL",
            "strength": "WEAK"
        }

    support_strike = safe_number(
        support.get("strike")
    )

    resistance_strike = safe_number(
        resistance.get("strike")
    )

    if support_strike <= 0 or resistance_strike <= 0:
        return {
            "factor": "SUPPORT_RESISTANCE",
            "direction": "NEUTRAL",
            "strength": "WEAK"
        }

    if spot <= support_strike:
        return {
            "factor": "SUPPORT_RESISTANCE",
            "support": support_strike,
            "resistance": resistance_strike,
            "direction": "BULLISH",
            "strength": "MODERATE"
        }

    if spot >= resistance_strike:
        return {
            "factor": "SUPPORT_RESISTANCE",
            "support": support_strike,
            "resistance": resistance_strike,
            "direction": "BEARISH",
            "strength": "MODERATE"
        }

    return {
        "factor": "SUPPORT_RESISTANCE",
        "support": support_strike,
        "resistance": resistance_strike,
        "direction": "NEUTRAL",
        "strength": "WEAK"
    }


# ============================================================
# 6. MARKET STRUCTURE EVIDENCE
# ============================================================

def evaluate_market_structure(
    market_structure
):
    """
    Convert market structure into descriptive evidence.
    """

    structure = str(
        market_structure or ""
    ).upper()

    if structure == "ABOVE_RESISTANCE":

        return {
            "factor": "MARKET_STRUCTURE",
            "value": structure,
            "direction": "BULLISH",
            "strength": "STRONG"
        }

    if structure == "BELOW_SUPPORT":

        return {
            "factor": "MARKET_STRUCTURE",
            "value": structure,
            "direction": "BEARISH",
            "strength": "STRONG"
        }

    if structure == "INSIDE_RANGE":

        return {
            "factor": "MARKET_STRUCTURE",
            "value": structure,
            "direction": "NEUTRAL",
            "strength": "WEAK"
        }

    return {
        "factor": "MARKET_STRUCTURE",
        "value": structure,
        "direction": "NEUTRAL",
        "strength": "WEAK"
    }


# ============================================================
# 7. OI PRESSURE EVIDENCE
# ============================================================

def evaluate_oi_pressure(
    oi_pressure
):
    """
    Evaluate aggregate OI pressure.

    Positive:
        More Put OI addition than Call OI addition.

    Negative:
        More Call OI addition than Put OI addition.

    IMPORTANT:
    This is NOT the same as guaranteed buying/selling.
    """

    pressure = safe_number(
        oi_pressure
    )

    if pressure > 0:

        return {
            "factor": "OI_PRESSURE",
            "value": pressure,
            "direction": "BULLISH",
            "strength": "MODERATE"
        }

    if pressure < 0:

        return {
            "factor": "OI_PRESSURE",
            "value": pressure,
            "direction": "BEARISH",
            "strength": "MODERATE"
        }

    return {
        "factor": "OI_PRESSURE",
        "value": pressure,
        "direction": "NEUTRAL",
        "strength": "WEAK"
    }


# ============================================================
# 8. BUILD ALL EVIDENCE
# ============================================================

def build_evidence(analysis):
    """
    Build all independent evidence factors from the
    market-analysis result.
    """

    if not analysis:
        raise ValueError(
            "Market analysis is empty."
        )

    evidence = []

    # --------------------------------------------------------
    # PCR
    # --------------------------------------------------------

    evidence.append(
        evaluate_pcr(
            analysis.get("pcr")
        )
    )

    # --------------------------------------------------------
    # OI CHANGE
    # --------------------------------------------------------

    evidence.append(
        evaluate_oi_change(
            analysis.get(
                "total_ce_oi_change"
            ),
            analysis.get(
                "total_pe_oi_change"
            )
        )
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    evidence.append(
        evaluate_volume(
            analysis.get(
                "total_ce_volume"
            ),
            analysis.get(
                "total_pe_volume"
            )
        )
    )

    # --------------------------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------

    evidence.append(
        evaluate_support_resistance(
            analysis.get(
                "spot_price"
            ),
            analysis.get(
                "support"
            ),
            analysis.get(
                "resistance"
            )
        )
    )

    # --------------------------------------------------------
    # MARKET STRUCTURE
    # --------------------------------------------------------

    evidence.append(
        evaluate_market_structure(
            analysis.get(
                "market_structure"
            )
        )
    )

    # --------------------------------------------------------
    # OI PRESSURE
    # --------------------------------------------------------

    evidence.append(
        evaluate_oi_pressure(
            analysis.get(
                "oi_pressure"
            )
        )
    )

    return evidence


# ============================================================
# 9. COUNT EVIDENCE
# ============================================================

def count_evidence(evidence):
    """
    Count bullish, bearish and neutral evidence.
    """

    bullish = 0
    bearish = 0
    neutral = 0

    for item in evidence:

        direction = str(
            item.get("direction", "")
        ).upper()

        if direction == "BULLISH":
            bullish += 1

        elif direction == "BEARISH":
            bearish += 1

        else:
            neutral += 1

    return {
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "total": len(evidence)
    }


# ============================================================
# 10. MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("EVIDENCE ENGINE")
    print("=" * 70)

    print(
        "Evidence engine loaded successfully."
    )

    print()
    print("Available functions:")

    print(
        " - evaluate_pcr()"
    )

    print(
        " - evaluate_oi_change()"
    )

    print(
        " - evaluate_volume()"
    )

    print(
        " - evaluate_support_resistance()"
    )

    print(
        " - evaluate_market_structure()"
    )

    print(
        " - evaluate_oi_pressure()"
    )

    print(
        " - build_evidence()"
    )

    print(
        " - count_evidence()"
    )

    print("=" * 70)