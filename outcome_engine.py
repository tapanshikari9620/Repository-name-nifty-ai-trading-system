# ============================================================
# OUTCOME ENGINE
# ============================================================
#
# Purpose:
#
# Measure what actually happened after a generated signal.
#
# Horizons:
#
#     +5 minutes
#     +15 minutes
#     +30 minutes
#     +60 minutes
#
# The engine:
#
#     1. Reads PENDING signals
#     2. Gets current NIFTY spot
#     3. Calculates elapsed time
#     4. Updates only completed horizons
#     5. Preserves previous outcomes
#
# IMPORTANT:
#
# This module DOES NOT:
#
#     - place orders
#     - generate signals
#     - change the original signal
#
# It only measures the future market outcome.
#
# ============================================================

from datetime import datetime, timezone, timedelta

from upstox_api import get_option_chain

from signal_logger import (
    get_pending_signals,
    update_outcome
)


# ============================================================
# CONFIGURATION
# ============================================================

HORIZONS = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60
}


# ============================================================
# GET CURRENT NIFTY SPOT
# ============================================================

def get_current_spot():
    """
    Retrieve the current NIFTY spot price using the existing
    Upstox option-chain API layer.
    """

    option_chain = get_option_chain()

    if not option_chain:

        raise RuntimeError(
            "Unable to retrieve option chain."
        )

    spot_price = option_chain[0].get(
        "underlying_spot_price"
    )

    if spot_price is None:

        raise RuntimeError(
            "NIFTY spot price unavailable."
        )

    try:

        spot_price = float(
            spot_price
        )

    except (
        TypeError,
        ValueError
    ):

        raise RuntimeError(
            "Invalid NIFTY spot price."
        )

    if spot_price <= 0:

        raise RuntimeError(
            "NIFTY spot price must be greater than zero."
        )

    return spot_price


# ============================================================
# PARSE TIMESTAMP
# ============================================================

def parse_timestamp(timestamp):
    """
    Convert stored UTC ISO timestamp into a timezone-aware
    datetime object.
    """

    if not timestamp:

        raise ValueError(
            "Signal timestamp is missing."
        )

    parsed = datetime.fromisoformat(
        timestamp
    )

    if parsed.tzinfo is None:

        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


# ============================================================
# CALCULATE ELAPSED MINUTES
# ============================================================

def calculate_elapsed_minutes(
    signal_timestamp
):
    """
    Return elapsed minutes between signal creation and now.
    """

    signal_time = parse_timestamp(
        signal_timestamp
    )

    now = datetime.now(
        timezone.utc
    )

    elapsed_seconds = (
        now - signal_time
    ).total_seconds()

    return elapsed_seconds / 60.0


# ============================================================
# CALCULATE OUTCOME
# ============================================================

def calculate_price_change(
    entry_price,
    current_price
):
    """
    Calculate NIFTY point movement.

    Example:

        Entry  = 24435
        Current = 24410

        Result = -25
    """

    return (
        current_price -
        entry_price
    )


# ============================================================
# CALCULATE DIRECTIONAL MOVE
# ============================================================

def calculate_directional_move(
    bias,
    entry_price,
    current_price
):
    """
    Convert the raw NIFTY movement into movement in the
    predicted direction.

    BEARISH:

        price falling = positive

    BULLISH:

        price rising = positive

    NEUTRAL:

        raw movement is returned.
    """

    raw_change = (
        current_price -
        entry_price
    )

    if bias == "BULLISH":

        return raw_change

    if bias == "BEARISH":

        return -raw_change

    return raw_change


# ============================================================
# PROCESS ONE SIGNAL
# ============================================================

def process_signal(
    signal,
    current_spot
):
    """
    Process one pending signal.

    Returns a dictionary describing what was updated.
    """

    signal_id = signal["signal_id"]

    entry_price = float(
        signal["spot_price"]
    )

    bias = (
        signal["bias"] or
        "NEUTRAL"
    )

    elapsed_minutes = calculate_elapsed_minutes(
        signal["timestamp_utc"]
    )

    updates = {}

    # --------------------------------------------------------
    # 5 MINUTE
    # --------------------------------------------------------

    if (
        elapsed_minutes >= 5
        and
        signal["outcome_5m"] is None
    ):

        updates["outcome_5m"] = (
            calculate_price_change(
                entry_price,
                current_spot
            )
        )

    # --------------------------------------------------------
    # 15 MINUTE
    # --------------------------------------------------------

    if (
        elapsed_minutes >= 15
        and
        signal["outcome_15m"] is None
    ):

        updates["outcome_15m"] = (
            calculate_price_change(
                entry_price,
                current_spot
            )
        )

    # --------------------------------------------------------
    # 30 MINUTE
    # --------------------------------------------------------

    if (
        elapsed_minutes >= 30
        and
        signal["outcome_30m"] is None
    ):

        updates["outcome_30m"] = (
            calculate_price_change(
                entry_price,
                current_spot
            )
        )

    # --------------------------------------------------------
    # 60 MINUTE
    # --------------------------------------------------------

    if (
        elapsed_minutes >= 60
        and
        signal["outcome_60m"] is None
    ):

        updates["outcome_60m"] = (
            calculate_price_change(
                entry_price,
                current_spot
            )
        )

    # --------------------------------------------------------
    # DIRECTIONAL MOVE
    # --------------------------------------------------------

    directional_move = (
        calculate_directional_move(
            bias,
            entry_price,
            current_spot
        )
    )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if elapsed_minutes >= 60:

        status = "COMPLETED"

    else:

        status = "PENDING"

    # --------------------------------------------------------
    # UPDATE DATABASE
    # --------------------------------------------------------

    if updates:

        update_outcome(

            signal_id=signal_id,

            outcome_5m=
                updates.get(
                    "outcome_5m"
                ),

            outcome_15m=
                updates.get(
                    "outcome_15m"
                ),

            outcome_30m=
                updates.get(
                    "outcome_30m"
                ),

            outcome_60m=
                updates.get(
                    "outcome_60m"
                ),

            max_favorable_move=(
                directional_move
                if directional_move > 0
                else None
            ),

            max_adverse_move=(
                directional_move
                if directional_move < 0
                else None
            ),

            status=status
        )

    return {

        "signal_id": signal_id,

        "elapsed_minutes":
            elapsed_minutes,

        "updates":
            updates,

        "directional_move":
            directional_move,

        "status":
            status
    }


# ============================================================
# PROCESS ALL PENDING SIGNALS
# ============================================================

def process_pending_signals():
    """
    Process all currently pending signals.
    """

    pending_signals = (
        get_pending_signals()
    )

    if not pending_signals:

        return {
            "processed": 0,
            "updated": 0
        }

    current_spot = get_current_spot()

    processed = 0
    updated = 0

    results = []

    for signal in pending_signals:

        result = process_signal(
            signal,
            current_spot
        )

        processed += 1

        if result["updates"]:

            updated += 1

        results.append(
            result
        )

    return {

        "processed":
            processed,

        "updated":
            updated,

        "current_spot":
            current_spot,

        "results":
            results
    }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("OUTCOME ENGINE")
    print("=" * 70)

    print()
    print(
        "Outcome engine loaded successfully."
    )

    print()
    print("Available functions:")

    print(
        "- get_current_spot()"
    )

    print(
        "- parse_timestamp()"
    )

    print(
        "- calculate_elapsed_minutes()"
    )

    print(
        "- calculate_price_change()"
    )

    print(
        "- calculate_directional_move()"
    )

    print(
        "- process_signal()"
    )

    print(
        "- process_pending_signals()"
    )

    print()
    print("=" * 70)