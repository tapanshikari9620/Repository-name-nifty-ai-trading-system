import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from experimental_variable_chain_builder import (
    ORIGINAL_DATABASE,
    assess_snapshot,
    run_experiment,
)


def make_market():
    return {
        "id": 7,
        "timestamp_utc": "2026-09-01T05:00:00+00:00",
        "spot_price": 1000.0,
    }


def make_variable_chain():
    rows = []
    timestamp = make_market()["timestamp_utc"]
    expiry = "2026-09-08"
    for index, strike in enumerate(range(750, 1351, 50)):
        ce_oi = 100 + index
        pe_oi = 200 + 2 * index
        ce_change = index - 6
        pe_change = 2 * (6 - index)
        for option_type, oi, change, volume in (
            ("CE", ce_oi, ce_change, index + 1),
            ("PE", pe_oi, pe_change, 2 * (index + 1)),
        ):
            rows.append({
                "market_snapshot_id": 7,
                "timestamp_utc": timestamp,
                "expiry": expiry,
                "strike": float(strike),
                "option_type": option_type,
                "instrument_key": f"{expiry}-{strike}-{option_type}",
                "ltp": 0.0,
                "iv": 0.0,
                "delta": 0.5 if option_type == "CE" else -0.5,
                "gamma": 0.01,
                "theta": -1.0,
                "vega": 1.0,
                "oi": float(oi),
                "prev_oi": float(oi - change),
                "oi_change": float(change),
                "volume": float(volume),
            })
    return rows


def make_healthy_record(rows):
    return {
        "status": "SUCCESS",
        "validation_status": "PASS",
        "option_records": len(rows),
        "expected_option_records": len(rows),
    }


class VariableChainEligibilityTests(unittest.TestCase):

    def test_complete_and_variable_chains_are_eligible(self):
        variable = make_variable_chain()
        result = assess_snapshot(
            make_market(), variable, make_healthy_record(variable)
        )
        self.assertTrue(result["eligible"], result["reasons"])
        self.assertFalse(result["legacy_exact_210"])

        complete = []
        timestamp = make_market()["timestamp_utc"]
        expiry = "2026-09-08"
        strikes = range(500, 1550, 10)
        for strike in strikes:
            for option_type in ("CE", "PE"):
                complete.append({
                    "market_snapshot_id": 7,
                    "timestamp_utc": timestamp,
                    "expiry": expiry,
                    "strike": float(strike),
                    "option_type": option_type,
                    "instrument_key": f"{expiry}-{strike}-{option_type}",
                    "ltp": 1.0,
                    "iv": 20.0,
                    "delta": 0.5,
                    "gamma": 0.01,
                    "theta": -1.0,
                    "vega": 1.0,
                    "oi": 100.0,
                    "prev_oi": 90.0,
                    "oi_change": 10.0,
                    "volume": 10.0,
                })
        result = assess_snapshot(
            make_market(), complete, make_healthy_record(complete)
        )
        self.assertTrue(result["eligible"], result["reasons"])
        self.assertTrue(result["legacy_exact_210"])

    def test_asymmetric_chain_is_rejected(self):
        rows = make_variable_chain()
        rows.pop()
        result = assess_snapshot(
            make_market(), rows, make_healthy_record(rows)
        )
        self.assertIn("CE_PE_STRIKES_NOT_PAIRED", result["reasons"])

    def test_duplicate_contract_and_instrument_are_rejected(self):
        rows = make_variable_chain()
        rows.append(rows[0].copy())
        result = assess_snapshot(
            make_market(), rows, make_healthy_record(rows)
        )
        self.assertIn("DUPLICATE_CONTRACT", result["reasons"])
        self.assertIn("DUPLICATE_INSTRUMENT_KEY", result["reasons"])

    def test_multiple_expiries_are_rejected(self):
        rows = make_variable_chain()
        rows[0]["expiry"] = "2026-09-15"
        result = assess_snapshot(
            make_market(), rows, make_healthy_record(rows)
        )
        self.assertIn("EXPIRY_NOT_UNIQUE", result["reasons"])

    def test_missing_and_invalid_required_values_are_rejected(self):
        for field, value, expected_reason in (
            ("oi", None, "INVALID_REQUIRED_NUMERIC:oi"),
            ("volume", float("inf"), "INVALID_REQUIRED_NUMERIC:volume"),
            ("prev_oi", -1.0, "NEGATIVE_REQUIRED_NUMERIC:prev_oi"),
            ("oi_change", 999.0, "OI_CHANGE_INCONSISTENT"),
        ):
            with self.subTest(field=field):
                rows = make_variable_chain()
                rows[0][field] = value
                result = assess_snapshot(
                    make_market(), rows, make_healthy_record(rows)
                )
                self.assertIn(expected_reason, result["reasons"])

    def test_inadequate_atm_coverage_is_rejected(self):
        rows = make_variable_chain()
        kept = {750, 850, 950, 1000, 1050, 1150, 1250}
        rows = [row for row in rows if row["strike"] in kept]
        result = assess_snapshot(
            make_market(), rows, make_healthy_record(rows)
        )
        self.assertIn("INSUFFICIENT_NEAR_SPOT_PAIRED_COVERAGE", result["reasons"])
        self.assertIn("INSUFFICIENT_ATM_WINDOW_STRIKES", result["reasons"])

    def test_missing_health_and_zero_or_extreme_optional_quotes_are_explicit(self):
        rows = make_variable_chain()
        for row in rows:
            row["ltp"] = 1.0
        rows[0]["ltp"] = 0.0
        rows[1]["ltp"] = 1.0
        rows[0]["iv"] = 999.98
        rows[0]["theta"] = -100000.0
        result = assess_snapshot(make_market(), rows, health=None)
        self.assertTrue(result["eligible"], result["reasons"])
        self.assertIn("COLLECTION_HEALTH_MISSING", result["warnings"])
        self.assertEqual("UNKNOWN", result["diagnostics"]["quote_freshness"])
        self.assertEqual(1, result["diagnostics"]["ltp_zero"])
        self.assertEqual(1, result["diagnostics"]["iv_above_150_diagnostic_only"])
        self.assertEqual(1, result["diagnostics"]["theta_extreme_diagnostic_only"])

    def test_invalid_timestamp_and_spot_are_rejected_explicitly(self):
        rows = make_variable_chain()
        bad_timestamp = make_market()
        bad_timestamp["timestamp_utc"] = "2026-09-01 05:00:00"
        result = assess_snapshot(
            bad_timestamp, rows, make_healthy_record(rows)
        )
        self.assertIn(
            "INVALID_OR_TIMEZONE_NAIVE_MARKET_TIMESTAMP",
            result["reasons"],
        )

        bad_spot = make_market()
        bad_spot["spot_price"] = float("nan")
        result = assess_snapshot(bad_spot, rows, make_healthy_record(rows))
        self.assertIn("INVALID_OR_NONPOSITIVE_SPOT", result["reasons"])

    def test_failed_collection_health_is_rejected(self):
        rows = make_variable_chain()
        health = make_healthy_record(rows)
        health["validation_status"] = "FAIL"
        result = assess_snapshot(make_market(), rows, health)
        self.assertIn("COLLECTION_HEALTH_NOT_PASS", result["reasons"])

    def test_independent_feature_calculation_for_full_and_atm11_views(self):
        rows = make_variable_chain()
        result = assess_snapshot(
            make_market(), rows, make_healthy_record(rows)
        )
        features = result["features"]
        if features is None:
            self.fail("Eligible snapshot must contain feature values.")

        # Independent arithmetic for indices 0..12 and ATM indices 0..10.
        self.assertEqual(1378.0, features["full_total_ce_oi"])
        self.assertEqual(2756.0, features["full_total_pe_oi"])
        self.assertEqual(2.0, features["full_pcr"])
        self.assertEqual(0.0, features["full_total_ce_oi_change"])
        self.assertEqual(0.0, features["full_total_pe_oi_change"])
        self.assertEqual(0.0, features["full_oi_pressure"])
        self.assertEqual(91.0, features["full_total_ce_volume"])
        self.assertEqual(182.0, features["full_total_pe_volume"])
        self.assertEqual(91.0, features["full_volume_pressure"])
        self.assertEqual(112.0, features["full_highest_ce_oi"])
        self.assertEqual(224.0, features["full_highest_pe_oi"])
        self.assertEqual(6.0, features["full_highest_ce_oi_change"])
        self.assertEqual(12.0, features["full_highest_pe_oi_change"])
        self.assertEqual(1155.0, features["atm11_total_ce_oi"])
        self.assertEqual(2310.0, features["atm11_total_pe_oi"])
        self.assertEqual(2.0, features["atm11_pcr"])
        self.assertEqual(-11.0, features["atm11_total_ce_oi_change"])
        self.assertEqual(22.0, features["atm11_total_pe_oi_change"])
        self.assertEqual(33.0, features["atm11_oi_pressure"])
        self.assertEqual(66.0, features["atm11_total_ce_volume"])
        self.assertEqual(132.0, features["atm11_total_pe_volume"])
        self.assertEqual(66.0, features["atm11_volume_pressure"])
        self.assertEqual(110.0, features["atm11_highest_ce_oi"])
        self.assertEqual(220.0, features["atm11_highest_pe_oi"])
        self.assertEqual(4.0, features["atm11_highest_ce_oi_change"])
        self.assertEqual(12.0, features["atm11_highest_pe_oi_change"])
        self.assertEqual(1350.0, features["full_historical_support"])
        self.assertEqual(1350.0, features["full_historical_resistance"])
        self.assertEqual(1250.0, features["atm11_historical_support"])
        self.assertEqual(1250.0, features["atm11_historical_resistance"])
        self.assertEqual(1000.0, features["full_live_support"])
        self.assertEqual(1350.0, features["full_live_resistance"])
        self.assertEqual(1000.0, features["atm11_live_support"])
        self.assertEqual(1250.0, features["atm11_live_resistance"])
        self.assertEqual(750.0, features["atm11_window_low_strike"])
        self.assertEqual(1250.0, features["atm11_window_high_strike"])

    def test_original_database_path_is_refused(self):
        with self.assertRaises(ValueError):
            run_experiment(ORIGINAL_DATABASE)

    def test_experiment_writes_are_idempotent_on_isolated_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "experiment.db"
            connection = sqlite3.connect(database)
            connection.executescript("""
                CREATE TABLE market_snapshots (
                    id INTEGER PRIMARY KEY,
                    timestamp_utc TEXT NOT NULL,
                    spot_price REAL NOT NULL
                );
                CREATE TABLE option_snapshots (
                    id INTEGER PRIMARY KEY,
                    market_snapshot_id INTEGER NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    expiry TEXT NOT NULL,
                    strike REAL NOT NULL,
                    option_type TEXT NOT NULL,
                    instrument_key TEXT NOT NULL,
                    ltp REAL, iv REAL, delta REAL, gamma REAL, theta REAL, vega REAL,
                    oi REAL, prev_oi REAL, oi_change REAL, volume REAL
                );
                CREATE TABLE collection_health (
                    id INTEGER PRIMARY KEY,
                    market_snapshot_id INTEGER,
                    status TEXT,
                    validation_status TEXT,
                    option_records INTEGER,
                    expected_option_records INTEGER
                );
                CREATE TABLE market_features (
                    market_snapshot_id INTEGER PRIMARY KEY
                );
                INSERT INTO market_snapshots VALUES
                    (7, '2026-09-01T05:00:00+00:00', 1000.0);
            """)
            rows = make_variable_chain()
            connection.executemany(
                """
                INSERT INTO option_snapshots (
                    market_snapshot_id, timestamp_utc, expiry, strike,
                    option_type, instrument_key, ltp, iv, delta, gamma,
                    theta, vega, oi, prev_oi, oi_change, volume
                ) VALUES (
                    :market_snapshot_id, :timestamp_utc, :expiry, :strike,
                    :option_type, :instrument_key, :ltp, :iv, :delta, :gamma,
                    :theta, :vega, :oi, :prev_oi, :oi_change, :volume
                )
                """,
                rows,
            )
            connection.execute(
                "INSERT INTO collection_health VALUES (1, 7, 'SUCCESS', 'PASS', ?, ?)",
                (len(rows), len(rows)),
            )
            connection.commit()
            connection.close()

            first = run_experiment(database)
            connection = sqlite3.connect(database)
            first_json = connection.execute(
                "SELECT features_json FROM experiment_features_paired_atm_v1"
            ).fetchone()[0]
            connection.close()

            second = run_experiment(database)
            connection = sqlite3.connect(database)
            second_json = connection.execute(
                "SELECT features_json FROM experiment_features_paired_atm_v1"
            ).fetchone()[0]
            eligibility_count = connection.execute(
                "SELECT COUNT(*) FROM experiment_eligibility_paired_atm_v1"
            ).fetchone()[0]
            feature_count = connection.execute(
                "SELECT COUNT(*) FROM experiment_features_paired_atm_v1"
            ).fetchone()[0]
            connection.close()

            self.assertEqual(1, first["eligible_snapshots"])
            self.assertEqual(1, second["eligible_snapshots"])
            self.assertEqual(first_json, second_json)
            self.assertEqual(1, eligibility_count)
            self.assertEqual(1, feature_count)
            self.assertEqual(
                1155.0,
                json.loads(second_json)["atm11_total_ce_oi"],
            )


if __name__ == "__main__":
    unittest.main()
