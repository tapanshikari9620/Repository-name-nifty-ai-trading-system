import sqlite3
from collections import Counter

DB_PATH = "nifty_market_data.db"

EXPECTED_TOTAL = 210
EXPECTED_CE = 105
EXPECTED_PE = 105


def main():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("210-CONTRACT FEATURE UNIVERSE CONSISTENCY TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. Feature snapshot count
    # ---------------------------------------------------------
    feature_snapshots = conn.execute("""
        SELECT COUNT(DISTINCT snapshot_id)
        FROM option_features
    """).fetchone()[0]

    option_feature_rows = conn.execute("""
        SELECT COUNT(*)
        FROM option_features
    """).fetchone()[0]

    expected_rows = feature_snapshots * EXPECTED_TOTAL

    print(f"\nFeature snapshots        : {feature_snapshots}")
    print(f"Option feature rows      : {option_feature_rows}")
    print(f"Expected rows            : {expected_rows}")

    # ---------------------------------------------------------
    # 2. Check every snapshot has exactly 210 records
    # ---------------------------------------------------------
    counts = conn.execute("""
        SELECT snapshot_id, COUNT(*) AS cnt
        FROM option_features
        GROUP BY snapshot_id
    """).fetchall()

    wrong_count_snapshots = [
        (row["snapshot_id"], row["cnt"])
        for row in counts
        if row["cnt"] != EXPECTED_TOTAL
    ]

    print(f"\nSnapshots with exactly 210 : "
          f"{len(counts) - len(wrong_count_snapshots)}")

    print(f"Snapshots with wrong count  : "
          f"{len(wrong_count_snapshots)}")

    if wrong_count_snapshots:
        print("\nWRONG COUNT DETAILS:")
        for snapshot_id, count in wrong_count_snapshots[:20]:
            print(f"  Snapshot {snapshot_id}: {count} records")

    # ---------------------------------------------------------
    # 3. CE / PE distribution
    # ---------------------------------------------------------
    type_counts = conn.execute("""
        SELECT option_type, COUNT(*) AS cnt
        FROM option_features
        GROUP BY option_type
    """).fetchall()

    print("\nOPTION TYPE DISTRIBUTION")

    for row in type_counts:
        print(f"{row['option_type']} : {row['cnt']}")

    # ---------------------------------------------------------
    # 4. Check CE/PE count per snapshot
    # ---------------------------------------------------------
    wrong_ce_pe = []

    for row in counts:
        snapshot_id = row["snapshot_id"]

        ce = conn.execute("""
            SELECT COUNT(*)
            FROM option_features
            WHERE snapshot_id = ?
              AND option_type = 'CE'
        """, (snapshot_id,)).fetchone()[0]

        pe = conn.execute("""
            SELECT COUNT(*)
            FROM option_features
            WHERE snapshot_id = ?
              AND option_type = 'PE'
        """, (snapshot_id,)).fetchone()[0]

        if ce != EXPECTED_CE or pe != EXPECTED_PE:
            wrong_ce_pe.append((snapshot_id, ce, pe))

    print(f"\nSnapshots with 105 CE + 105 PE : "
          f"{len(counts) - len(wrong_ce_pe)}")

    print(f"Snapshots with wrong CE/PE       : "
          f"{len(wrong_ce_pe)}")

    if wrong_ce_pe:
        print("\nWRONG CE/PE DETAILS:")
        for snapshot_id, ce, pe in wrong_ce_pe[:20]:
            print(
                f"  Snapshot {snapshot_id}: "
                f"CE={ce}, PE={pe}"
            )

    # ---------------------------------------------------------
    # 5. Duplicate contract check
    # ---------------------------------------------------------
    duplicate_rows = conn.execute("""
        SELECT snapshot_id, instrument_key, COUNT(*) AS cnt
        FROM option_features
        GROUP BY snapshot_id, instrument_key
        HAVING COUNT(*) > 1
    """).fetchall()

    print(f"\nDuplicate feature contracts : {len(duplicate_rows)}")

    if duplicate_rows:
        print("\nDUPLICATES:")
        for row in duplicate_rows[:20]:
            print(
                f"  Snapshot {row['snapshot_id']} | "
                f"{row['instrument_key']} | "
                f"count={row['cnt']}"
            )

    # ---------------------------------------------------------
    # 6. Check contract universe consistency
    # ---------------------------------------------------------
    snapshots = [
        row["snapshot_id"]
        for row in counts
        if row["cnt"] == EXPECTED_TOTAL
    ]

    reference_snapshot = snapshots[0] if snapshots else None

    missing_contracts = 0
    extra_contracts = 0
    inconsistent_snapshots = 0

    if reference_snapshot is not None:

        reference_contracts = {
            row["instrument_key"]
            for row in conn.execute("""
                SELECT instrument_key
                FROM option_features
                WHERE snapshot_id = ?
            """, (reference_snapshot,))
        }

        print(
            f"\nReference snapshot       : {reference_snapshot}"
        )

        print(
            f"Reference contracts      : "
            f"{len(reference_contracts)}"
        )

        for snapshot_id in snapshots[1:]:

            current_contracts = {
                row["instrument_key"]
                for row in conn.execute("""
                    SELECT instrument_key
                    FROM option_features
                    WHERE snapshot_id = ?
                """, (snapshot_id,))
            }

            missing = reference_contracts - current_contracts
            extra = current_contracts - reference_contracts

            if missing or extra:
                inconsistent_snapshots += 1
                missing_contracts += len(missing)
                extra_contracts += len(extra)

    print(f"\nSnapshots with inconsistent universe : "
          f"{inconsistent_snapshots}")

    print(f"Missing contracts                     : "
          f"{missing_contracts}")

    print(f"Extra contracts                       : "
          f"{extra_contracts}")

    # ---------------------------------------------------------
    # 7. Expiry consistency
    # ---------------------------------------------------------
    expiry_issues = []

    for snapshot_id in snapshots:

        expiries = {
            row["expiry"]
            for row in conn.execute("""
                SELECT DISTINCT expiry
                FROM option_features
                WHERE snapshot_id = ?
            """, (snapshot_id,))
        }

        if len(expiries) != 1:
            expiry_issues.append((snapshot_id, expiries))

    print(f"\nSnapshots with expiry inconsistency : "
          f"{len(expiry_issues)}")

    # ---------------------------------------------------------
    # FINAL RESULT
    # ---------------------------------------------------------
    failures = []

    if option_feature_rows != expected_rows:
        failures.append("Total feature row count mismatch")

    if wrong_count_snapshots:
        failures.append("Some snapshots do not contain exactly 210 records")

    if wrong_ce_pe:
        failures.append("Some snapshots do not contain 105 CE + 105 PE")

    if duplicate_rows:
        failures.append("Duplicate feature contracts found")

    if inconsistent_snapshots:
        failures.append("Contract universe changed between snapshots")

    if expiry_issues:
        failures.append("Expiry inconsistency found")

    print("\n" + "=" * 70)

    if failures:
        print("FEATURE UNIVERSE CONSISTENCY STATUS : FAIL")

        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")

    else:
        print("FEATURE UNIVERSE CONSISTENCY STATUS : PASS")
        print("\nAll feature snapshots consistently represent")
        print("the same 210-contract option universe.")

    print("=" * 70)

    conn.close()


if __name__ == "__main__":
    main()