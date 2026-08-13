# ============================================================
# SIGNAL ENGINE
# ============================================================
#
# Purpose:
#
# Convert evidence-engine output into a structured market
# signal.
#
# IMPORTANT:
#
# This is NOT a trading strategy yet.
#
# The score and thresholds are initial engineering rules.
# They MUST eventually be validated with historical backtesting.
#
# This module:
#
#     DOES NOT place orders
#     DOES NOT select an option contract
#     DOES NOT guarantee profit
#     DOES NOT claim prediction accuracy
#
# ============================================================


# ============================================================
# 1. SIGNAL CONFIGURATION
# ============================================================

# Score assigned to each evidence strength.

STRENGTH_SCORE = {
    "STRONG": 3,
    "MODERATE": 2,
    "WEAK": 1
}


# Minimum score difference required between bullish
# and bearish evidence before considering a directional bias.

MIN_SCORE_DIFFERENCE = 2


# Minimum total directional score required.

MIN_DIRECTIONAL_SCORE = 3


# Minimum confidence required before allowing a signal.

MIN_CONFIDENCE = 60.0


# ============================================================
# 2. SAFE NUMBER
# ============================================================

def safe_number(value):
    """
    Convert a value safely into float.
    """

    if value is None:
        return 0.0

    try:
        return float(value)

    except (TypeError, ValueError):
        return 0.0


# ============================================================
# 3. GET EVIDENCE SCORE
# ============================================================

def get_evidence_score(evidence):
    """
    Convert one evidence item into a numeric score.

    Example:

        BULLISH + MODERATE
            = +2

        BEARISH + STRONG
            = -3

        NEUTRAL
            = 0
    """

    if not evidence:
        return 0

    direction = str(
        evidence.get(
            "direction",
            "NEUTRAL"
        )
    ).upper()

    strength = str(
        evidence.get(
            "strength",
            "WEAK"
        )
    ).upper()

    strength_value = STRENGTH_SCORE.get(
        strength,
        1
    )

    if direction == "BULLISH":

        return strength_value

    if direction == "BEARISH":

        return -strength_value

    return 0


# ============================================================
# 4. CALCULATE EVIDENCE SCORES
# ============================================================

def calculate_evidence_scores(evidence):
    """
    Calculate total bullish and bearish scores.
    """

    if not evidence:

        return {
            "bullish_score": 0,
            "bearish_score": 0,
            "net_score": 0
        }

    bullish_score = 0
    bearish_score = 0

    for item in evidence:

        score = get_evidence_score(
            item
        )

        if score > 0:

            bullish_score += score

        elif score < 0:

            bearish_score += abs(score)

    net_score = (
        bullish_score -
        bearish_score
    )

    return {
        "bullish_score": bullish_score,
        "bearish_score": bearish_score,
        "net_score": net_score
    }


# ============================================================
# 5. CALCULATE CONFIDENCE
# ============================================================

def calculate_confidence(
    bullish_score,
    bearish_score
):
    """
    Calculate a transparent confidence percentage.

    This is NOT statistical probability.

    It simply measures how dominant one side is among
    the directional evidence currently available.
    """

    bullish_score = safe_number(
        bullish_score
    )

    bearish_score = safe_number(
        bearish_score
    )

    total_score = (
        bullish_score +
        bearish_score
    )

    if total_score <= 0:

        return 0.0

    dominant_score = max(
        bullish_score,
        bearish_score
    )

    confidence = (
        dominant_score /
        total_score
    ) * 100

    return round(
        confidence,
        2
    )


# ============================================================
# 6. DETERMINE MARKET BIAS
# ============================================================

def determine_bias(
    bullish_score,
    bearish_score
):
    """
    Determine directional market bias.

    Conservative approach:
    If evidence is too close -> NEUTRAL.
    """

    bullish_score = safe_number(
        bullish_score
    )

    bearish_score = safe_number(
        bearish_score
    )

    difference = abs(
        bullish_score -
        bearish_score
    )

    if (
        bullish_score >= MIN_DIRECTIONAL_SCORE
        and
        bullish_score > bearish_score
        and
        difference >= MIN_SCORE_DIFFERENCE
    ):

        return "BULLISH"

    if (
        bearish_score >= MIN_DIRECTIONAL_SCORE
        and
        bearish_score > bullish_score
        and
        difference >= MIN_SCORE_DIFFERENCE
    ):

        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# 7. DETERMINE ACTION
# ============================================================

def determine_action(
    bias,
    confidence
):
    """
    Convert bias + confidence into a conservative action.

    IMPORTANT:
    This is still not an order instruction.
    """

    confidence = safe_number(
        confidence
    )

    if (
        bias == "BULLISH"
        and
        confidence >= MIN_CONFIDENCE
    ):

        return "WATCH_CALL"

    if (
        bias == "BEARISH"
        and
        confidence >= MIN_CONFIDENCE
    ):

        return "WATCH_PUT"

    return "NO_TRADE"


# ============================================================
# 8. CALCULATE SIGNAL
# ============================================================

def calculate_signal(
    evidence,
    analysis=None
):
    """
    Generate a structured market signal from evidence.

    Parameters
    ----------
    evidence:
        Output from evidence_engine.build_evidence()

    analysis:
        Optional output from market_analyzer.analyze_market()

    Returns
    -------
    dict
        Structured signal result.
    """

    if evidence is None:

        raise ValueError(
            "Evidence cannot be None."
        )

    if not isinstance(
        evidence,
        list
    ):

        raise TypeError(
            "Evidence must be a list."
        )

    # --------------------------------------------------------
    # Calculate scores
    # --------------------------------------------------------

    scores = calculate_evidence_scores(
        evidence
    )

    bullish_score = scores[
        "bullish_score"
    ]

    bearish_score = scores[
        "bearish_score"
    ]

    net_score = scores[
        "net_score"
    ]

    # --------------------------------------------------------
    # Determine bias
    # --------------------------------------------------------

    bias = determine_bias(
        bullish_score,
        bearish_score
    )

    # --------------------------------------------------------
    # Calculate confidence
    # --------------------------------------------------------

    confidence = calculate_confidence(
        bullish_score,
        bearish_score
    )

    # --------------------------------------------------------
    # Determine action
    # --------------------------------------------------------

    action = determine_action(
        bias,
        confidence
    )

    # --------------------------------------------------------
    # Count evidence
    # --------------------------------------------------------

    bullish_evidence = 0
    bearish_evidence = 0
    neutral_evidence = 0

    for item in evidence:

        direction = str(
            item.get(
                "direction",
                "NEUTRAL"
            )
        ).upper()

        if direction == "BULLISH":

            bullish_evidence += 1

        elif direction == "BEARISH":

            bearish_evidence += 1

        else:

            neutral_evidence += 1

    # --------------------------------------------------------
    # Build result
    # --------------------------------------------------------

    result = {

        "bias": bias,

        "action": action,

        "bullish_score": bullish_score,

        "bearish_score": bearish_score,

        "net_score": net_score,

        "confidence": confidence,

        "bullish_evidence": bullish_evidence,

        "bearish_evidence": bearish_evidence,

        "neutral_evidence": neutral_evidence,

        "total_evidence": len(
            evidence
        )
    }

    # --------------------------------------------------------
    # Preserve useful market information
    # --------------------------------------------------------

    if analysis:

        result["pcr"] = safe_number(
            analysis.get("pcr")
        )

        result["oi_pressure"] = safe_number(
            analysis.get("oi_pressure")
        )

        result["volume_pressure"] = safe_number(
            analysis.get("volume_pressure")
        )

        result["market_structure"] = (
            analysis.get(
                "market_structure",
                "UNKNOWN"
            )
        )

        support = analysis.get(
            "support"
        )

        resistance = analysis.get(
            "resistance"
        )

        if support:

            result["support"] = safe_number(
                support.get("strike")
            )

        else:

            result["support"] = None

        if resistance:

            result["resistance"] = safe_number(
                resistance.get("strike")
            )

        else:

            result["resistance"] = None

    return result


# ============================================================
# 9. MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("SIGNAL ENGINE")
    print("=" * 70)

    print()
    print(
        "Signal engine loaded successfully."
    )

    print()
    print("Available functions:")

    print(
        "- safe_number()"
    )

    print(
        "- get_evidence_score()"
    )

    print(
        "- calculate_evidence_scores()"
    )

    print(
        "- calculate_confidence()"
    )

    print(
        "- determine_bias()"
    )

    print(
        "- determine_action()"
    )

    print(
        "- calculate_signal()"
    )

    print()
    print("=" * 70)