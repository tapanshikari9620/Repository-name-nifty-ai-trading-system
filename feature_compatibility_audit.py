
import os
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from datetime import datetime


# ============================================================
# FEATURE COMPATIBILITY AUDIT
# READ-ONLY: No database writes or feature generation
# ============================================================

DATABASE_NAME = os.environ.get(
    "NIFTY_MARKET_DATABASE",
    str(Path(__file__).resolve().parent / "nifty_market_data.db"),
)
ATM_WINDOW_STRIKES = 21  # 10 nearby strikes on each side + ATM


def number(value):
    """Return a finite float, or None for invalid/missing values."""
    try:
        if value is None or str(value).strip() == "":
            return None

        result = float(value)

        if not math.isfinite(result):
            return None

        return result
    except (TypeError, ValueError):
        return None


def median_or_none(values):
    values = [v for v in values if v is not None]
    return median(values) if values else None


def show_median(label, values, suffix=""):
    value = median_or_none(values)

    if value is None:
        print(f"{label:<45}: N/A")
    else:
        print(f"{label:<45}: {value:.4f}{suffix}")


def table_exists(connection, name):
    return connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (name,),
    ).fetchone() is not None


def audit_snapshot(market, rows):
    spot = number(market["spot_price"])

    ce_rows = [
        r for r in rows
        if str(r["option_type"]).strip().upper() == "CE"
    ]
    pe_rows = [
        r for r in rows
        if str(r["option_type"]).strip().upper() == "PE"
    ]

    all_strikes = sorted({
        number(r["strike"])
        for r in rows
        if number(r["strike"]) is not None
    })

    ce_strikes = {
        number(r["strike"])
        for r in ce_rows
        if number(r["strike"]) is not None
    }
    pe_strikes = {
        number(r["strike"])
        for r in pe_rows
        if number(r["strike"]) is not None
    }

    paired = bool(ce_strikes) and ce_strikes == pe_strikes

    # Match the builder's ATM selection: nearest available strike.
    atm = None
    if spot is not None and all_strikes:
        atm = min(all_strikes, key=lambda s: abs(s - spot))

    # Standardized comparison window: nearest 21 unique strike levels.
    # This is calculated for audit purposes only; it is NOT written
    # to the database or proposed as a final feature definition.
    window_strikes = set()

    if spot is not None and all_strikes:
        nearest = sorted(all_strikes, key=lambda s: abs(s - spot))
        window_strikes = set(nearest[:ATM_WINDOW_STRIKES])

    window_rows = [
        r for r in rows
        if number(r["strike"]) in window_strikes
    ]

    def total(chain_rows, field):
        values = [number(r[field]) for r in chain_rows]
        invalid = sum(v is None for v in values)
        result = sum(v for v in values if v is not None)
        return result, invalid

    ce_oi, ce_oi_invalid = total(ce_rows, "oi")
    pe_oi, pe_oi_invalid = total(pe_rows, "oi")
    ce_volume, ce_vol_invalid = total(ce_rows, "volume")
    pe_volume, pe_vol_invalid = total(pe_rows, "volume")
    ce_change, ce_change_invalid = total(ce_rows, "oi_change")
    pe_change, pe_change_invalid = total(pe_rows, "oi_change")

    window_ce = [
        r for r in window_rows
        if str(r["option_type"]).strip().upper() == "CE"
    ]
    window_pe = [
        r for r in window_rows
        if str(r["option_type"]).strip().upper() == "PE"
    ]

    window_ce_oi, window_ce_invalid = total(window_ce, "oi")
    window_pe_oi, window_pe_invalid = total(window_pe, "oi")

    full_pcr = pe_oi / ce_oi if ce_oi > 0 else None
    window_pcr = (
        window_pe_oi / window_ce_oi
        if window_ce_oi > 0 else None
    )

    ce_coverage = (
        window_ce_oi / ce_oi
        if ce_oi > 0 else None
    )
    pe_coverage = (
        window_pe_oi / pe_oi
        if pe_oi > 0 else None
    )

    # Existing builder's full-chain highest-OI strike calculations.
    highest_ce = max(
        ce_rows,
        key=lambda r: number(r["oi"])
        if number(r["oi"]) is not None else float("-inf"),
        default=None,
    )
    highest_pe = max(
        pe_rows,
        key=lambda r: number(r["oi"])
        if number(r["oi"]) is not None else float("-inf"),
        default=None,
    )

    return {
        "option_count": len(rows),
        "ce_count": len(ce_rows),
        "pe_count": len(pe_rows),
        "strike_count": len(all_strikes),
        "paired": paired,
        "atm": atm,
        "spot": spot,
        "min_strike": min(all_strikes) if all_strikes else None,
        "max_strike": max(all_strikes) if all_strikes else None,
        "atm_distance": abs(atm - spot) if atm is not None and spot is not None else None,
        "window_count": len(window_strikes),
        "window_ce_count": len(window_ce),
        "window_pe_count": len(window_pe),
        "full_ce_oi": ce_oi,
        "full_pe_oi": pe_oi,
        "full_pcr": full_pcr,
        "window_ce_oi": window_ce_oi,
        "window_pe_oi": window_pe_oi,
        "window_pcr": window_pcr,
        "ce_oi_coverage": ce_coverage,
        "pe_oi_coverage": pe_coverage,
        "full_ce_volume": ce_volume,
        "full_pe_volume": pe_volume,
        "full_ce_oi_change": ce_change,
        "full_pe_oi_change": pe_change,
        "highest_ce_strike": (
            number(highest_ce["strike"]) if highest_ce else None
        ),
        "highest_pe_strike": (
            number(highest_pe["strike"]) if highest_pe else None
        ),
        "invalid_numeric_fields": (
            ce_oi_invalid + pe_oi_invalid
            + ce_vol_invalid + pe_vol_invalid
            + ce_change_invalid + pe_change_invalid
            + window_ce_invalid + window_pe_invalid
        ),
    }


def print_group_summary(label, records):
    print(f"\n{label}")
    print("-" * 72)
    print(f"Snapshots: {len(records)}")

    if not records:
        return

    show_median("Median option records", [r["option_count"] for r in records])
    show_median("Median unique strike levels", [r["strike_count"] for r in records])
    show_median("Median CE records", [r["ce_count"] for r in records])
    show_median("Median PE records", [r["pe_count"] for r in records])

    enough = sum(
        r["window_count"] >= ATM_WINDOW_STRIKES
        for r in records
    )
    paired = sum(r["paired"] for r in records)

    print(
        f"Snapshots with paired CE/PE strikes: "
        f"{paired} / {len(records)}"
    )
    print(
        f"Snapshots with at least {ATM_WINDOW_STRIKES} strike levels: "
        f"{enough} / {len(records)}"
    )

    show_median("Median full-chain PCR", [r["full_pcr"] for r in records])
    show_median("Median ATM-window PCR", [r["window_pcr"] for r in records])
    show_median(
        "Median CE OI retained in ATM window",
        [r["ce_oi_coverage"] for r in records],
        " (fraction)",
    )
    show_median(
        "Median PE OI retained in ATM window",
        [r["pe_oi_coverage"] for r in records],
        " (fraction)",
    )
    show_median(
        "Median distance from spot to ATM strike",
        [r["atm_distance"] for r in records],
    )

    invalid = sum(r["invalid_numeric_fields"] for r in records)
    print(f"Invalid numeric values in audited fields: {invalid}")


def main():
    db_path = Path(DATABASE_NAME).resolve()

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return

    connection = sqlite3.connect(
        db_path.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    try:
        for table in ("market_snapshots", "option_snapshots", "market_features"):
            if not table_exists(connection, table):
                print(f"ERROR: Required table missing: {table}")
                return

        print("=" * 72)
        print("FEATURE COMPATIBILITY AUDIT")
        print("READ-ONLY — DATABASE WILL NOT BE MODIFIED")
        print("=" * 72)
        print(f"Database: {db_path}")
        print(f"ATM comparison window: {ATM_WINDOW_STRIKES} nearest strike levels")

        feature_ids = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT market_snapshot_id FROM market_features"
            ).fetchall()
        }

        markets = connection.execute(
            """
            SELECT id, timestamp_utc, spot_price
            FROM market_snapshots
            ORDER BY timestamp_utc, id
            """
        ).fetchall()

        options_by_snapshot = defaultdict(list)

        option_rows = connection.execute(
            """
            SELECT market_snapshot_id, expiry, strike, option_type,
                   oi, oi_change, volume
            FROM option_snapshots
            ORDER BY market_snapshot_id
            """
        ).fetchall()

        for row in option_rows:
            options_by_snapshot[row["market_snapshot_id"]].append(row)

        existing = []
        missing = []
        count_distribution = Counter()
        invalid_timestamps = 0
        no_option_snapshots = 0

        for market in markets:
            snapshot_id = market["id"]
            rows = options_by_snapshot.get(snapshot_id, [])

            if not rows:
                no_option_snapshots += 1
                continue

            try:
                timestamp = datetime.fromisoformat(
                    str(market["timestamp_utc"])
                )
                if timestamp is None:
                    invalid_timestamps += 1
            except (TypeError, ValueError):
                invalid_timestamps += 1

            result = audit_snapshot(market, rows)
            result["snapshot_id"] = snapshot_id
            result["timestamp_utc"] = market["timestamp_utc"]

            count_distribution[result["option_count"]] += 1

            if snapshot_id in feature_ids:
                existing.append(result)
            else:
                missing.append(result)

        print("\nDATABASE COUNTS")
        print("-" * 72)
        print(f"Market snapshots: {len(markets)}")
        print(f"Snapshots containing options: {len(existing) + len(missing)}")
        print(f"Snapshots with existing market features: {len(existing)}")
        print(f"Snapshots missing market features: {len(missing)}")
        print(f"Snapshots without options: {no_option_snapshots}")
        print(f"Unparseable timestamps: {invalid_timestamps}")

        print_group_summary("EXISTING FEATURE SNAPSHOTS", existing)
        print_group_summary("MISSING FEATURE SNAPSHOTS", missing)

        print("\nMISSING SNAPSHOTS BY OPTION COUNT")
        print("-" * 72)
        for count, total in sorted(count_distribution.items()):
            group = [
                r for r in missing
                if r["option_count"] == count
            ]
            if not group:
                continue

            paired = sum(r["paired"] for r in group)
            enough = sum(
                r["window_count"] >= ATM_WINDOW_STRIKES
                for r in group
            )

            print(
                f"{count:>4} records | {len(group):>5} missing snapshots "
                f"| paired={paired:>5} "
                f"| >= {ATM_WINDOW_STRIKES} strikes={enough:>5}"
            )

        print("\n" + "=" * 72)
        print("INTERPRETATION NOTES")
        print("- Full-chain totals use every option row in each snapshot.")
        print("- ATM-window metrics use the nearest 21 unique strike levels.")
        print("- PCR differences can reflect the strike universe, not a bug.")
        print("- OI coverage shows how much full-chain OI lies in that window.")
        print("- This audit does not establish that either feature method is best.")
        print("- No database tables or rows were modified.")
        print("=" * 72)
        print("AUDIT COMPLETE — READ-ONLY")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
