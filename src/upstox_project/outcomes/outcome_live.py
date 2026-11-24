import sys

from upstox_project.outcomes.outcome_engine import (
    process_pending_signals
)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("LIVE OUTCOME ENGINE TEST")
    print("=" * 70)

    result = process_pending_signals()

    print()
    print("=" * 70)
    print("OUTCOME RESULT")
    print("=" * 70)

    print(
        f"Signals processed : "
        f"{result.get('processed', 0)}"
    )

    print(
        f"Signals updated   : "
        f"{result.get('updated', 0)}"
    )

    if result.get(
        "current_spot"
    ) is not None:

        print(
            f"Current NIFTY     : "
            f"{result['current_spot']:.2f}"
        )

    for item in result.get(
        "results",
        []
    ):

        print()
        print(
            f"Signal ID : "
            f"{item['signal_id']}"
        )

        print(
            f"Elapsed   : "
            f"{item['elapsed_minutes']:.2f} minutes"
        )

        print(
            f"Updates   : "
            f"{item['updates']}"
        )

        print(
            f"Direction : "
            f"{item['directional_move']:.2f}"
        )

        print(
            f"Status    : "
            f"{item['status']}"
        )

    print()
    print("=" * 70)
    print(
        "LIVE OUTCOME ENGINE COMPLETED"
    )
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