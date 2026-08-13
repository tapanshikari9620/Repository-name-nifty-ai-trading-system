# ============================================================
# FEATURE VALIDATOR
# ============================================================
#
# Responsibility:
# Validate the normalized option features before they are
# passed to the market-analysis / signal engine.
#
# IMPORTANT:
# This module DOES NOT generate BUY / SELL signals.
#
# It only answers:
#
#       "Is this data reliable enough to analyze?"
# ============================================================


# ============================================================
# 1. VALIDATE SPOT PRICE
# ============================================================

def validate_spot_price(spot_price):
    """
    Validate NIFTY spot price.
    """

    if spot_price is None:
        return False, "Spot price is missing."

    if spot_price <= 0:
        return False, "Spot price must be greater than zero."

    return True, "Spot price is valid."


# ============================================================
# 2. VALIDATE ATM STRIKE
# ============================================================

def validate_atm_strike(atm_strike):
    """
    Validate ATM strike.
    """

    if atm_strike is None:
        return False, "ATM strike is missing."

    if atm_strike <= 0:
        return False, "ATM strike must be greater than zero."

    return True, "ATM strike is valid."


# ============================================================
# 3. VALIDATE SELECTED STRIKES
# ============================================================

def validate_selected_strikes(selected_options):
    """
    Validate ATM ± 5 option selection.

    Expected:
        11 strikes
        unique strikes
        valid strike prices
        sorted strikes
    """

    if not selected_options:
        return False, "Selected option list is empty."

    if len(selected_options) != 11:
        return (
            False,
            f"Expected 11 strikes, got {len(selected_options)}."
        )

    strikes = []

    for option in selected_options:

        strike = option.get("strike_price")

        if strike is None:
            return False, "A selected option has no strike price."

        if strike <= 0:
            return False, f"Invalid strike price: {strike}"

        strikes.append(strike)

    # Check duplicate strikes
    if len(strikes) != len(set(strikes)):
        return False, "Duplicate strike detected."

    # Check sorting
    if strikes != sorted(strikes):
        return False, "Selected strikes are not sorted."

    return True, "Selected strikes are valid."


# ============================================================
# 4. VALIDATE SINGLE OPTION FEATURE
# ============================================================

def validate_option_feature(feature):
    """
    Validate one normalized option feature dictionary.
    """

    if not feature:
        return False, "Feature dictionary is empty."

    required_fields = [

        "strike",

        # CALL
        "ce_ltp",
        "ce_oi",
        "ce_oi_change",
        "ce_volume",
        "ce_iv",
        "ce_delta",
        "ce_gamma",
        "ce_theta",
        "ce_vega",

        # PUT
        "pe_ltp",
        "pe_oi",
        "pe_oi_change",
        "pe_volume",
        "pe_iv",
        "pe_delta",
        "pe_gamma",
        "pe_theta",
        "pe_vega",
    ]

    # --------------------------------------------------------
    # Check missing fields
    # --------------------------------------------------------

    for field in required_fields:

        if field not in feature:
            return (
                False,
                f"Missing feature: {field}"
            )

        if feature[field] is None:
            return (
                False,
                f"Feature is None: {field}"
            )

    # --------------------------------------------------------
    # Strike
    # --------------------------------------------------------

    if feature["strike"] <= 0:
        return False, "Invalid strike."

    # --------------------------------------------------------
    # LTP
    # --------------------------------------------------------

    if feature["ce_ltp"] < 0:
        return False, "Invalid CE LTP."

    if feature["pe_ltp"] < 0:
        return False, "Invalid PE LTP."

    # --------------------------------------------------------
    # OI
    # --------------------------------------------------------

    if feature["ce_oi"] < 0:
        return False, "Invalid CE OI."

    if feature["pe_oi"] < 0:
        return False, "Invalid PE OI."

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    if feature["ce_volume"] < 0:
        return False, "Invalid CE volume."

    if feature["pe_volume"] < 0:
        return False, "Invalid PE volume."

    # --------------------------------------------------------
    # IV
    # --------------------------------------------------------

    if feature["ce_iv"] < 0:
        return False, "Invalid CE IV."

    if feature["pe_iv"] < 0:
        return False, "Invalid PE IV."

    # --------------------------------------------------------
    # Delta
    #
    # We intentionally allow a small tolerance because
    # market-data providers may return values slightly outside
    # theoretical bounds.
    # --------------------------------------------------------

    if not -1.1 <= feature["ce_delta"] <= 1.1:
        return False, "Invalid CE delta."

    if not -1.1 <= feature["pe_delta"] <= 1.1:
        return False, "Invalid PE delta."

    # --------------------------------------------------------
    # Gamma
    # --------------------------------------------------------

    if feature["ce_gamma"] < 0:
        return False, "Invalid CE gamma."

    if feature["pe_gamma"] < 0:
        return False, "Invalid PE gamma."

    # --------------------------------------------------------
    # Vega
    # --------------------------------------------------------

    if feature["ce_vega"] < 0:
        return False, "Invalid CE vega."

    if feature["pe_vega"] < 0:
        return False, "Invalid PE vega."

    return True, "Option feature is valid."


# ============================================================
# 5. VALIDATE ALL FEATURES
# ============================================================

def validate_features(features):
    """
    Validate all normalized option features.

    Returns:

        {
            "valid": True / False,
            "total": number,
            "valid_count": number,
            "invalid_count": number,
            "errors": [...]
        }
    """

    if not features:
        return {
            "valid": False,
            "total": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "errors": [
                "Feature list is empty."
            ]
        }

    errors = []
    valid_count = 0

    for index, feature in enumerate(features):

        valid, message = validate_option_feature(
            feature
        )

        if valid:

            valid_count += 1

        else:

            errors.append(
                f"Feature {index}: {message}"
            )

    invalid_count = (
        len(features) - valid_count
    )

    return {
        "valid": invalid_count == 0,
        "total": len(features),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "errors": errors
    }


# ============================================================
# 6. VALIDATE COMPLETE MARKET DATA
# ============================================================

def validate_market_data(
    spot_price,
    atm_strike,
    selected_options,
    features
):
    """
    Perform complete validation before analysis.

    This is the main validation function that the
    application should call.
    """

    errors = []

    # --------------------------------------------------------
    # Spot
    # --------------------------------------------------------

    valid, message = validate_spot_price(
        spot_price
    )

    if not valid:
        errors.append(message)

    # --------------------------------------------------------
    # ATM
    # --------------------------------------------------------

    valid, message = validate_atm_strike(
        atm_strike
    )

    if not valid:
        errors.append(message)

    # --------------------------------------------------------
    # Selected strikes
    # --------------------------------------------------------

    valid, message = validate_selected_strikes(
        selected_options
    )

    if not valid:
        errors.append(message)

    # --------------------------------------------------------
    # Features
    # --------------------------------------------------------

    feature_result = validate_features(
        features
    )

    if not feature_result["valid"]:

        errors.extend(
            feature_result["errors"]
        )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "feature_result": feature_result
    }


# ============================================================
# 7. MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("FEATURE VALIDATOR")
    print("=" * 60)

    print(
        "Feature validator loaded successfully."
    )

    print()
    print("Available functions:")

    print(
        " - validate_spot_price()"
    )

    print(
        " - validate_atm_strike()"
    )

    print(
        " - validate_selected_strikes()"
    )

    print(
        " - validate_option_feature()"
    )

    print(
        " - validate_features()"
    )

    print(
        " - validate_market_data()"
    )

    print("=" * 60)