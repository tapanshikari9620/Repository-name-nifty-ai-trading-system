"""Isolated, versioned variable-chain feature experiment.

This module never writes to the repository's original market database. Run it
only with an explicitly named copy:

python experimental_variable_chain_builder.py --create-copy --database-copy audit_reports\\experimental\\paired_atm_v1.db
python experimental_variable_chain_builder.py --database-copy audit_reports\\experimental\\paired_atm_v1.db
"""

import argparse
import itertools
import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TypedDict
from zoneinfo import ZoneInfo


POLICY_VERSION = "paired_atm_v1"
ELIGIBILITY_TABLE = "experiment_eligibility_paired_atm_v1"
FEATURE_TABLE = "experiment_features_paired_atm_v1"
@dataclass(frozen=True)
class EligibilityPolicy:
    minimum_paired_strikes_each_side_within_points: int = 5
    near_spot_band_points: float = 250.0
    atm_window_strikes_each_side: int = 5
    oi_change_relative_tolerance: float = 1e-9
    oi_change_absolute_tolerance: float = 1e-6
    iv_high_diagnostic_threshold: float = 150.0


DEFAULT_POLICY = EligibilityPolicy()
ORIGINAL_DATABASE = Path(__file__).resolve().parent / "nifty_market_data.db"
REQUIRED_FEATURE_FIELDS = ("oi", "prev_oi", "oi_change", "volume")
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


class SnapshotAssessment(TypedDict):
    eligible: bool
    reasons: list[str]
    warnings: list[str]
    paired_strike_count: int
    strikes_below_spot_within_band: int
    strikes_above_spot_within_band: int
    atm_strike: float | None
    legacy_exact_210: bool
    diagnostics: dict[str, object]
    features: dict[str, object] | None


def finite_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number: float = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def parse_aware_timestamp(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.utcoffset() is None:
        return None
    return timestamp


def _required_numeric_reasons(rows, policy):
    reasons = set()
    for row in rows:
        values = {
            name: finite_number(row[name])
            for name in REQUIRED_FEATURE_FIELDS
        }
        for name, value in values.items():
            if value is None:
                reasons.add(f"INVALID_REQUIRED_NUMERIC:{name}")

        for name in ("oi", "prev_oi", "volume"):
            value = values[name]
            if value is not None and value < 0:
                reasons.add(f"NEGATIVE_REQUIRED_NUMERIC:{name}")

        oi = values["oi"]
        prev_oi = values["prev_oi"]
        oi_change = values["oi_change"]
        if oi is not None and prev_oi is not None and oi_change is not None:
            expected = oi - prev_oi
            if not math.isclose(
                oi_change,
                expected,
                rel_tol=policy.oi_change_relative_tolerance,
                abs_tol=policy.oi_change_absolute_tolerance,
            ):
                reasons.add("OI_CHANGE_INCONSISTENT")
    return reasons


def _quote_diagnostics(rows, health, policy) -> dict[str, int | bool | str]:
    diagnostic = {
        "quote_freshness": "UNKNOWN",
        "quote_timestamp_available": False,
        "ltp_missing_or_nonfinite": 0,
        "ltp_zero": 0,
        "iv_missing_or_nonfinite": 0,
        "iv_zero": 0,
        "iv_above_150_diagnostic_only": 0,
        "theta_extreme_diagnostic_only": 0,
        "delta_outside_minus1_to_1_diagnostic_only": 0,
        "gamma_negative_diagnostic_only": 0,
        "vega_negative_diagnostic_only": 0,
        "collection_health": "MISSING",
    }

    if health is not None:
        diagnostic["collection_health"] = (
            f"{health['status'] or 'UNKNOWN'}/"
            f"{health['validation_status'] or 'UNKNOWN'}"
        )

    for row in rows:
        ltp = finite_number(row["ltp"])
        iv = finite_number(row["iv"])
        theta = finite_number(row["theta"])
        delta = finite_number(row["delta"])
        gamma = finite_number(row["gamma"])
        vega = finite_number(row["vega"])
        diagnostic["ltp_missing_or_nonfinite"] += int(ltp is None)
        diagnostic["ltp_zero"] += int(ltp == 0)
        diagnostic["iv_missing_or_nonfinite"] += int(iv is None)
        diagnostic["iv_zero"] += int(iv == 0)
        if iv is not None:
            diagnostic["iv_above_150_diagnostic_only"] += int(
                iv > policy.iv_high_diagnostic_threshold
            )
        if theta is not None:
            diagnostic["theta_extreme_diagnostic_only"] += int(
                abs(theta) > 1000
            )
        diagnostic["delta_outside_minus1_to_1_diagnostic_only"] += int(
            delta is not None and not -1 <= delta <= 1
        )
        diagnostic["gamma_negative_diagnostic_only"] += int(
            gamma is not None and gamma < 0
        )
        diagnostic["vega_negative_diagnostic_only"] += int(
            vega is not None and vega < 0
        )
    return diagnostic


def _sum_field(rows, option_type, field):
    return sum(float(row[field]) for row in rows if row["option_type"] == option_type)


def _max_strike(rows, option_type, field, predicate=None):
    candidates = [
        row for row in rows
        if row["option_type"] == option_type
        and (predicate is None or predicate(row))
    ]
    if not candidates:
        return None
    winner = max(
        candidates,
        key=lambda row: (float(row[field]), -float(row["strike"])),
    )
    return float(winner["strike"])


def _aggregate_features(rows, spot, scope, window_bounds=None):
    ce_oi = _sum_field(rows, "CE", "oi")
    pe_oi = _sum_field(rows, "PE", "oi")
    ce_change = _sum_field(rows, "CE", "oi_change")
    pe_change = _sum_field(rows, "PE", "oi_change")
    ce_volume = _sum_field(rows, "CE", "volume")
    pe_volume = _sum_field(rows, "PE", "volume")
    ce_max_oi = max(float(row["oi"]) for row in rows if row["option_type"] == "CE")
    pe_max_oi = max(float(row["oi"]) for row in rows if row["option_type"] == "PE")
    ce_max_change = max(
        float(row["oi_change"]) for row in rows if row["option_type"] == "CE"
    )
    pe_max_change = max(
        float(row["oi_change"]) for row in rows if row["option_type"] == "PE"
    )

    pcr = pe_oi / ce_oi if ce_oi > 0 else None
    result = {
        f"{scope}_total_ce_oi": ce_oi,
        f"{scope}_total_pe_oi": pe_oi,
        f"{scope}_pcr": pcr,
        f"{scope}_total_ce_oi_change": ce_change,
        f"{scope}_total_pe_oi_change": pe_change,
        f"{scope}_oi_pressure": pe_change - ce_change,
        f"{scope}_total_ce_volume": ce_volume,
        f"{scope}_total_pe_volume": pe_volume,
        f"{scope}_volume_pressure": pe_volume - ce_volume,
        f"{scope}_highest_ce_oi": ce_max_oi,
        f"{scope}_highest_pe_oi": pe_max_oi,
        f"{scope}_highest_ce_oi_change": ce_max_change,
        f"{scope}_highest_pe_oi_change": pe_max_change,
        f"{scope}_historical_support": _max_strike(rows, "PE", "oi"),
        f"{scope}_historical_resistance": _max_strike(rows, "CE", "oi"),
        f"{scope}_live_support": _max_strike(
            rows, "PE", "oi",
            predicate=lambda row: float(row["strike"]) <= spot,
        ),
        f"{scope}_live_resistance": _max_strike(
            rows, "CE", "oi",
            predicate=lambda row: float(row["strike"]) >= spot,
        ),
    }
    if result[f"{scope}_live_support"] is None:
        result[f"{scope}_live_support"] = result[f"{scope}_historical_support"]
    if result[f"{scope}_live_resistance"] is None:
        result[f"{scope}_live_resistance"] = result[f"{scope}_historical_resistance"]
    if window_bounds is not None:
        result[f"{scope}_window_low_strike"] = window_bounds[0]
        result[f"{scope}_window_high_strike"] = window_bounds[1]
    return result


def _make_features(rows, spot, policy):
    strikes = sorted({float(row["strike"]) for row in rows})
    atm_index = min(
        range(len(strikes)),
        key=lambda index: (abs(strikes[index] - spot), strikes[index]),
    )
    window_side = policy.atm_window_strikes_each_side
    if (
        atm_index < window_side
        or len(strikes) - atm_index - 1 < window_side
    ):
        raise ValueError("ATM window does not have the required strikes on both sides")

    window_strikes = set(
        strikes[atm_index - window_side:atm_index + window_side + 1]
    )
    window_rows = [
        row for row in rows
        if float(row["strike"]) in window_strikes
    ]
    features = {
        "feature_definition_version": POLICY_VERSION,
        "spot_price": spot,
        "atm_strike": strikes[atm_index],
        "paired_strike_count": len(strikes),
        "full_chain_option_count": len(rows),
        "atm11_strike_count": len(window_strikes),
        "atm11_option_count": len(window_rows),
    }
    features.update(_aggregate_features(rows, spot, "full"))
    features.update(
        _aggregate_features(
            window_rows,
            spot,
            "atm11",
            window_bounds=(strikes[atm_index - window_side],
                          strikes[atm_index + window_side]),
        )
    )
    return features


def assess_snapshot(
    market,
    rows,
    health=None,
    policy=DEFAULT_POLICY,
) -> SnapshotAssessment:
    """Return a deterministic eligibility decision and separate feature views."""
    reasons = set()
    warnings = set()
    timestamp = parse_aware_timestamp(market["timestamp_utc"])
    if timestamp is None:
        reasons.add("INVALID_OR_TIMEZONE_NAIVE_MARKET_TIMESTAMP")

    spot = finite_number(market["spot_price"])
    if spot is None or spot <= 0:
        reasons.add("INVALID_OR_NONPOSITIVE_SPOT")

    if not rows:
        reasons.add("NO_OPTION_RECORDS")

    seen_contracts = set()
    seen_instruments = set()
    expiries = set()
    call_strikes = set()
    put_strikes = set()
    for row in rows:
        expiry = row["expiry"]
        try:
            parsed_expiry = date.fromisoformat(str(expiry))
            if parsed_expiry.isoformat() != str(expiry):
                raise ValueError
        except (TypeError, ValueError):
            reasons.add("INVALID_EXPIRY")
            continue
        expiries.add(parsed_expiry)
        market_date = (
            timestamp.astimezone(MARKET_TIMEZONE).date()
            if timestamp is not None else None
        )
        if market_date is not None and parsed_expiry < market_date:
            reasons.add("EXPIRY_BEFORE_SNAPSHOT_DATE")

        option_type = row["option_type"]
        if option_type not in ("CE", "PE"):
            reasons.add("INVALID_OPTION_TYPE")
            continue

        strike = finite_number(row["strike"])
        if strike is None or strike <= 0:
            reasons.add("INVALID_STRIKE")
            continue
        if option_type == "CE":
            call_strikes.add(strike)
        else:
            put_strikes.add(strike)

        contract_key = (parsed_expiry.isoformat(), strike, option_type)
        if contract_key in seen_contracts:
            reasons.add("DUPLICATE_CONTRACT")
        seen_contracts.add(contract_key)

        instrument_key = row["instrument_key"]
        if not isinstance(instrument_key, str) or not instrument_key.strip():
            reasons.add("MISSING_INSTRUMENT_KEY")
        elif instrument_key in seen_instruments:
            reasons.add("DUPLICATE_INSTRUMENT_KEY")
        seen_instruments.add(instrument_key)

        option_timestamp = parse_aware_timestamp(row["timestamp_utc"])
        if option_timestamp is None:
            reasons.add("INVALID_OR_TIMEZONE_NAIVE_OPTION_TIMESTAMP")
        elif timestamp is not None and option_timestamp != timestamp:
            reasons.add("OPTION_MARKET_TIMESTAMP_MISMATCH")

    if len(expiries) != 1:
        reasons.add("EXPIRY_NOT_UNIQUE")

    if call_strikes != put_strikes:
        reasons.add("CE_PE_STRIKES_NOT_PAIRED")

    if rows:
        reasons.update(_required_numeric_reasons(rows, policy))

    if health is None:
        warnings.add("COLLECTION_HEALTH_MISSING")
    else:
        if (
            str(health["status"]).upper() != "SUCCESS"
            or str(health["validation_status"]).upper() != "PASS"
        ):
            reasons.add("COLLECTION_HEALTH_NOT_PASS")

        actual = finite_number(health["option_records"])
        expected = finite_number(health["expected_option_records"])
        if actual is not None and actual != len(rows):
            reasons.add("HEALTH_OPTION_COUNT_MISMATCH")
        if expected is not None and actual is not None and expected != actual:
            reasons.add("HEALTH_EXPECTED_COUNT_MISMATCH")

    paired_strikes = sorted(call_strikes & put_strikes)
    atm_strike = None
    lower_near_spot = 0
    upper_near_spot = 0
    if spot is not None and paired_strikes:
        spot_price = spot
        atm_index = min(
            range(len(paired_strikes)),
            key=lambda index: (
                abs(paired_strikes[index] - spot_price),
                paired_strikes[index],
            ),
        )
        atm_strike = paired_strikes[atm_index]
        lower_near_spot = sum(
            0 < spot_price - strike <= policy.near_spot_band_points
            for strike in paired_strikes
        )
        upper_near_spot = sum(
            0 < strike - spot_price <= policy.near_spot_band_points
            for strike in paired_strikes
        )
        if (
            lower_near_spot
            < policy.minimum_paired_strikes_each_side_within_points
            or upper_near_spot
            < policy.minimum_paired_strikes_each_side_within_points
        ):
            reasons.add("INSUFFICIENT_NEAR_SPOT_PAIRED_COVERAGE")
        if (
            atm_index < policy.atm_window_strikes_each_side
            or len(paired_strikes) - atm_index - 1
            < policy.atm_window_strikes_each_side
        ):
            reasons.add("INSUFFICIENT_ATM_WINDOW_STRIKES")

    diagnostics = _quote_diagnostics(rows, health, policy)
    features = None
    if not reasons:
        if spot is None:
            raise RuntimeError("Eligible snapshot unexpectedly has invalid spot.")
        features = _make_features(rows, spot, policy)

    return {
        "eligible": not reasons,
        "reasons": sorted(reasons),
        "warnings": sorted(warnings),
        "paired_strike_count": len(paired_strikes),
        "strikes_below_spot_within_band": lower_near_spot,
        "strikes_above_spot_within_band": upper_near_spot,
        "atm_strike": atm_strike,
        "legacy_exact_210": (
            len(rows) == 210
            and sum(row["option_type"] == "CE" for row in rows) == 105
            and sum(row["option_type"] == "PE" for row in rows) == 105
        ),
        "diagnostics": diagnostics,
        "features": features,
    }


def _is_original_database(database_path):
    candidate = Path(database_path).resolve()
    original = ORIGINAL_DATABASE.resolve()
    if candidate == original:
        return True
    try:
        return candidate.exists() and original.exists() and candidate.samefile(original)
    except OSError:
        return False


def create_database_copy(source_path, destination_path):
    source = Path(source_path).resolve()
    destination = Path(destination_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source database not found: {source}")
    if _is_original_database(destination):
        raise ValueError("The experiment destination cannot be the original database.")
    if destination == source or destination.exists():
        raise FileExistsError(
            f"Experiment database must be a new, separate path: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(
        f"{source.as_uri()}?mode=ro",
        uri=True,
    )
    destination_connection = sqlite3.connect(str(destination))
    try:
        source_tables = [
            row[0] for row in source_connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        source_counts = {
            table: source_connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
            for table in source_tables
        }
        source_connection.backup(destination_connection)
        destination_connection.commit()
        integrity = destination_connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Experiment copy failed integrity check: {integrity}")
        destination_counts = {
            table: destination_connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
            for table in source_tables
        }
        if source_counts != destination_counts:
            raise RuntimeError("Experiment copy table counts do not match the source.")
    finally:
        destination_connection.close()
        source_connection.close()
    return {
        "path": str(destination),
        "table_counts": source_counts,
        "integrity": integrity,
    }


def _create_experiment_tables(connection):
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ELIGIBILITY_TABLE} (
            market_snapshot_id INTEGER PRIMARY KEY,
            policy_version TEXT NOT NULL,
            eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
            legacy_exact_210 INTEGER NOT NULL CHECK (legacy_exact_210 IN (0, 1)),
            option_count INTEGER NOT NULL,
            paired_strike_count INTEGER NOT NULL,
            near_spot_below_count INTEGER NOT NULL,
            near_spot_above_count INTEGER NOT NULL,
            atm_strike REAL,
            rejection_reasons_json TEXT NOT NULL,
            warning_codes_json TEXT NOT NULL,
            diagnostics_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FEATURE_TABLE} (
            market_snapshot_id INTEGER PRIMARY KEY,
            policy_version TEXT NOT NULL,
            features_json TEXT NOT NULL
        )
        """
    )


def run_experiment(database_path, policy=DEFAULT_POLICY):
    """Build additive, versioned experiment tables on a database copy only."""
    database = Path(database_path).resolve()
    if _is_original_database(database):
        raise ValueError(
            "Refusing to run on nifty_market_data.db; provide a separate copy."
        )
    if not database.is_file():
        raise FileNotFoundError(f"Experiment database not found: {database}")

    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    try:
        required_tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = {"market_snapshots", "option_snapshots"} - required_tables
        if missing:
            raise RuntimeError(
                "Experiment database is missing tables: "
                + ", ".join(sorted(missing))
            )
        _create_experiment_tables(connection)

        markets = {
            row["id"]: dict(row)
            for row in connection.execute(
                "SELECT id, timestamp_utc, spot_price FROM market_snapshots"
            )
        }
        feature_ids = set()
        if "market_features" in required_tables:
            feature_ids = {
                row[0] for row in connection.execute(
                    "SELECT market_snapshot_id FROM market_features"
                )
            }

        health_by_id = {}
        if "collection_health" in required_tables:
            for row in connection.execute(
                """
                SELECT h.market_snapshot_id, h.status, h.validation_status,
                       h.option_records, h.expected_option_records
                FROM collection_health h
                JOIN (
                    SELECT market_snapshot_id, MAX(id) AS latest_id
                    FROM collection_health
                    WHERE market_snapshot_id IS NOT NULL
                    GROUP BY market_snapshot_id
                ) latest ON latest.latest_id = h.id
                """
            ):
                health_by_id[row["market_snapshot_id"]] = dict(row)

        option_cursor = connection.execute(
            """
            SELECT market_snapshot_id, timestamp_utc, expiry, strike,
                   option_type, instrument_key, ltp, iv, delta, gamma, theta,
                   vega, oi, prev_oi, oi_change, volume
            FROM option_snapshots
            ORDER BY market_snapshot_id, strike, option_type
            """
        )

        eligibility_records = []
        feature_records = []
        reason_counts = Counter()
        warning_counts = Counter()
        diagnostic_totals = Counter()
        legacy_eligible = 0
        existing_eligible = 0
        new_eligible = 0
        processed_ids = set()

        for snapshot_id, group in itertools.groupby(
            option_cursor,
            key=lambda row: row["market_snapshot_id"],
        ):
            rows = [dict(row) for row in group]
            market = markets.get(snapshot_id)
            if market is None:
                continue
            processed_ids.add(snapshot_id)
            result = assess_snapshot(
                market, rows, health_by_id.get(snapshot_id), policy
            )
            eligibility_records.append(
                _eligibility_record(snapshot_id, result, len(rows))
            )
            for reason in result["reasons"]:
                reason_counts[reason] += 1
            for warning in result["warnings"]:
                warning_counts[warning] += 1
            for name, value in result["diagnostics"].items():
                if isinstance(value, int) and not isinstance(value, bool):
                    diagnostic_totals[name] += value
            if result["eligible"]:
                if result["features"] is None:
                    raise RuntimeError(
                        "Eligible snapshot has no generated feature record."
                    )
                feature_records.append(
                    (
                        snapshot_id,
                        POLICY_VERSION,
                        json.dumps(
                            result["features"],
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                    )
                )
                legacy_eligible += result["legacy_exact_210"]
                if snapshot_id in feature_ids:
                    existing_eligible += 1
                else:
                    new_eligible += 1

        for snapshot_id, market in markets.items():
            if snapshot_id in processed_ids:
                continue
            result = assess_snapshot(
                market, [], health_by_id.get(snapshot_id), policy
            )
            eligibility_records.append(
                _eligibility_record(snapshot_id, result, 0)
            )
            for reason in result["reasons"]:
                reason_counts[reason] += 1
            for warning in result["warnings"]:
                warning_counts[warning] += 1

        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            f"""
            INSERT INTO {ELIGIBILITY_TABLE} (
                market_snapshot_id, policy_version, eligible,
                legacy_exact_210, option_count, paired_strike_count,
                near_spot_below_count, near_spot_above_count, atm_strike,
                rejection_reasons_json, warning_codes_json, diagnostics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_snapshot_id) DO UPDATE SET
                policy_version=excluded.policy_version,
                eligible=excluded.eligible,
                legacy_exact_210=excluded.legacy_exact_210,
                option_count=excluded.option_count,
                paired_strike_count=excluded.paired_strike_count,
                near_spot_below_count=excluded.near_spot_below_count,
                near_spot_above_count=excluded.near_spot_above_count,
                atm_strike=excluded.atm_strike,
                rejection_reasons_json=excluded.rejection_reasons_json,
                warning_codes_json=excluded.warning_codes_json,
                diagnostics_json=excluded.diagnostics_json
            """,
            eligibility_records,
        )
        connection.executemany(
            f"""
            INSERT INTO {FEATURE_TABLE} (
                market_snapshot_id, policy_version, features_json
            ) VALUES (?, ?, ?)
            ON CONFLICT(market_snapshot_id) DO UPDATE SET
                policy_version=excluded.policy_version,
                features_json=excluded.features_json
            """,
            feature_records,
        )
        connection.commit()

        return {
            "policy_version": POLICY_VERSION,
            "market_snapshots": len(markets),
            "option_bearing_snapshots": len(processed_ids),
            "eligible_snapshots": len(feature_records),
            "eligible_existing_feature_snapshots": existing_eligible,
            "newly_eligible_snapshots": new_eligible,
            "legacy_exact_210_eligible_snapshots": legacy_eligible,
            "rejected_snapshots": len(markets) - len(feature_records),
            "reason_counts": dict(sorted(reason_counts.items())),
            "warning_counts": dict(sorted(warning_counts.items())),
            "quote_diagnostic_totals": dict(sorted(diagnostic_totals.items())),
            "eligibility_rows_written": len(eligibility_records),
            "feature_rows_written": len(feature_records),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _eligibility_record(snapshot_id, result, option_count):
    return (
        snapshot_id,
        POLICY_VERSION,
        int(result["eligible"]),
        int(result["legacy_exact_210"]),
        option_count,
        result["paired_strike_count"],
        result["strikes_below_spot_within_band"],
        result["strikes_above_spot_within_band"],
        result["atm_strike"],
        json.dumps(result["reasons"], separators=(",", ":")),
        json.dumps(result["warnings"], separators=(",", ":")),
        json.dumps(
            result["diagnostics"],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-copy",
        required=True,
        help="An isolated SQLite copy; the original database is explicitly refused.",
    )
    parser.add_argument(
        "--create-copy",
        action="store_true",
        help="Create a new WAL-consistent copy from --source before running anything.",
    )
    parser.add_argument(
        "--source",
        default=str(ORIGINAL_DATABASE),
        help="Source database used only by --create-copy.",
    )
    args = parser.parse_args()
    if args.create_copy:
        print(json.dumps(
            create_database_copy(args.source, args.database_copy),
            indent=2,
            sort_keys=True,
        ))
        return
    print(json.dumps(
        run_experiment(args.database_copy),
        indent=2,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
