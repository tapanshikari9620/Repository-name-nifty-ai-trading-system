import os
from contextlib import closing
from pathlib import Path

from feature_universe_consistency_test import (
    audit_feature_snapshots,
    get_connection,
)


DATABASE_NAME = os.environ.get(
    "NIFTY_MARKET_DATABASE",
    str(Path(__file__).resolve().parent / "nifty_market_data.db"),
)


def main(database_name=None):
    with closing(get_connection(database_name or DATABASE_NAME)) as connection:
        results, orphan_raw, missing_option_features = (
            audit_feature_snapshots(connection)
        )

    pairing_failures = [
        result for result in results if not result["paired"]
    ]
    malformed = [result for result in results if result["errors"]]
    variable_counts = {
        result["feature_count"]
        for result in results
    }

    print("=" * 75)
    print("VARIABLE-SIZED CE/PE PAIR CONSISTENCY TEST")
    print("READ-ONLY — strike range and chain size may vary")
    print("=" * 75)
    print(f"Feature snapshots checked : {len(results)}")
    print(f"Distinct feature row counts: {len(variable_counts)}")
    print(f"CE/PE parity failures     : {len(pairing_failures)}")
    print(f"Other structural failures : {len(malformed)}")
    print(f"Orphan raw option rows    : {orphan_raw}")
    print(f"Market features without options: {len(missing_option_features)}")

    for result in pairing_failures[:50]:
        print(
            f"FAIL snapshot={result['market_snapshot_id']} "
            f"feature_rows={result['feature_count']} "
            f"CE={result['feature_ce_count']} "
            f"PE={result['feature_pe_count']}"
        )

    passed = (
        not pairing_failures
        and not malformed
        and orphan_raw == 0
        and not missing_option_features
    )
    print("=" * 75)
    print(
        "FEATURE UNIVERSE PAIR CONSISTENCY STATUS : "
        + ("PASS" if passed else "FAIL")
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
