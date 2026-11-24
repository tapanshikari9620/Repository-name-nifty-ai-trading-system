import sqlite3
import tempfile
import unittest
from pathlib import Path

import upstox_project.validation.dataset_quality as dataset_quality
from upstox_project.validation.ml_dataset_validation import select_candidate_features


class DatasetReadinessTests(unittest.TestCase):

    def test_session_count_uses_ist_market_dates_and_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "session-test.db"
            connection = sqlite3.connect(database_path)
            connection.execute(
                "CREATE TABLE market_features (timestamp_utc TEXT)"
            )
            connection.executemany(
                "INSERT INTO market_features VALUES (?)",
                [
                    ("2026-01-05T03:45:00+00:00",),
                    ("2026-01-05T10:00:00+00:00",),
                    ("2026-01-05T03:44:59+00:00",),
                    ("2026-01-06T10:00:01+00:00",),
                    ("2026-01-06T03:45:00+00:00",),
                    ("2026-01-07T04:00:00",),
                    ("not-a-timestamp",),
                ],
            )
            connection.commit()
            connection.close()

            original_database_name = dataset_quality.DATABASE_NAME
            self.addCleanup(
                setattr,
                dataset_quality,
                "DATABASE_NAME",
                original_database_name,
            )
            dataset_quality.DATABASE_NAME = str(database_path)

            self.assertEqual(3, dataset_quality.get_trading_sessions())

            read_only_connection = dataset_quality.get_connection()
            with self.assertRaises(sqlite3.OperationalError):
                read_only_connection.execute(
                    "INSERT INTO market_features VALUES ('2026-01-08')"
                )
            read_only_connection.close()

    @staticmethod
    def readiness_inputs(trading_sessions):
        distribution = {
            "BULLISH": 100,
            "BEARISH": 100,
            "FLAT": 300,
        }
        return {
            "total_features": 1000,
            "outcome_counts": {
                "5m": 500,
                "15m": 500,
                "30m": 500,
                "60m": 500,
            },
            "distributions": {
                horizon: distribution.copy()
                for horizon in ("5m", "15m", "30m", "60m")
            },
            "trading_sessions": trading_sessions,
            "alignment": {
                "missing_outcomes": 0,
                "orphan_outcomes": 0,
            },
            "continuity": {
                "large_gaps": 0,
            },
        }

    def test_readiness_blocks_below_120_trading_sessions(self):
        report = dataset_quality.calculate_readiness(
            **self.readiness_inputs(119)
        )

        self.assertFalse(report["ready"])
        self.assertIn(
            "Insufficient trading sessions (119/120).",
            report["problems"],
        )

    def test_readiness_allows_configured_threshold_at_120_sessions(self):
        report = dataset_quality.calculate_readiness(
            **self.readiness_inputs(120)
        )

        self.assertTrue(report["ready"])
        self.assertEqual([], report["problems"])


class CandidateFeatureTests(unittest.TestCase):

    def test_database_identifiers_and_timestamps_are_not_features(self):
        columns = [
            "id",
            "market_snapshot_id",
            "timestamp_utc",
            "created_at_utc",
            "spot_price",
            "pcr",
        ]

        self.assertEqual(
            ["spot_price", "pcr"],
            select_candidate_features(columns),
        )


if __name__ == "__main__":
    unittest.main()
