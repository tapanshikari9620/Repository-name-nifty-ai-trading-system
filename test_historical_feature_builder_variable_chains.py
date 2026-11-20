import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import historical_feature_builder as builder
import historical_feature_validation as feature_validation
import historical_outcome_builder as outcome_builder
from feature_universe_consistency_test import (
    audit_feature_snapshots,
    get_connection as get_read_only_connection,
)


DATABASE_SCHEMA = """
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
    instrument_key TEXT,
    ltp REAL,
    close_price REAL,
    volume REAL,
    oi REAL,
    prev_oi REAL,
    oi_change REAL,
    bid_price REAL,
    bid_qty REAL,
    ask_price REAL,
    ask_qty REAL,
    iv REAL,
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,
    pop REAL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(market_snapshot_id, instrument_key)
);
CREATE TABLE collection_health (
    id INTEGER PRIMARY KEY,
    market_snapshot_id INTEGER,
    status TEXT NOT NULL,
    validation_status TEXT
);
CREATE TABLE market_features (
    id INTEGER PRIMARY KEY,
    market_snapshot_id INTEGER NOT NULL UNIQUE,
    timestamp_utc TEXT NOT NULL,
    spot_price REAL NOT NULL,
    atm_strike REAL,
    support REAL,
    resistance REAL,
    total_ce_oi REAL,
    total_pe_oi REAL,
    pcr REAL,
    total_ce_oi_change REAL,
    total_pe_oi_change REAL,
    oi_pressure REAL,
    total_ce_volume REAL,
    total_pe_volume REAL,
    volume_pressure REAL,
    highest_ce_oi REAL,
    highest_pe_oi REAL,
    highest_ce_oi_change REAL,
    highest_pe_oi_change REAL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE option_features (
    id INTEGER PRIMARY KEY,
    market_snapshot_id INTEGER NOT NULL,
    timestamp_utc TEXT NOT NULL,
    expiry TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL,
    ltp REAL,
    close_price REAL,
    volume REAL,
    oi REAL,
    prev_oi REAL,
    oi_change REAL,
    bid_price REAL,
    bid_qty REAL,
    ask_price REAL,
    ask_qty REAL,
    iv REAL,
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,
    pop REAL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(market_snapshot_id, expiry, strike, option_type)
);
"""

BASE_TIMESTAMP = datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc)
EXPIRY = "2026-09-08"
SPOT = 22000.0


class VariableChainFeatureBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.test_database = Path(self.temporary_directory.name) / "features.db"
        self.original_database = builder.DATABASE_NAME
        self.original_validation_database = feature_validation.DATABASE_NAME
        self.original_outcome_database = outcome_builder.DATABASE_NAME
        builder.DATABASE_NAME = str(self.test_database)
        feature_validation.DATABASE_NAME = str(self.test_database)
        outcome_builder.DATABASE_NAME = str(self.test_database)
        self.addCleanup(
            setattr,
            builder,
            "DATABASE_NAME",
            self.original_database,
        )
        self.addCleanup(
            setattr,
            feature_validation,
            "DATABASE_NAME",
            self.original_validation_database,
        )
        self.addCleanup(
            setattr,
            outcome_builder,
            "DATABASE_NAME",
            self.original_outcome_database,
        )

        self.assertNotEqual(
            Path(builder.DATABASE_NAME).resolve(),
            Path(self.original_database).resolve(),
        )
        with closing(sqlite3.connect(self.test_database)) as connection:
            with connection:
                connection.executescript(DATABASE_SCHEMA)
                self._insert_valid_snapshot(connection, 1, 210)
                self._insert_valid_snapshot(connection, 2, 208)
                self._insert_valid_snapshot(connection, 3, 216)
                self._insert_valid_snapshot(connection, 4, 288)
                self._insert_valid_snapshot(connection, 5, 166)
                self._insert_invalid_snapshots(connection)

    def test_builders_refuse_to_create_missing_database_paths(self):
        missing_database = Path(self.temporary_directory.name) / "missing.db"

        for module in (builder, outcome_builder):
            original_database = module.DATABASE_NAME
            try:
                module.DATABASE_NAME = str(missing_database)
                with self.assertRaises(FileNotFoundError):
                    module.get_connection()
            finally:
                module.DATABASE_NAME = original_database

        self.assertFalse(missing_database.exists())

    def test_write_connection_must_match_configured_database(self):
        mismatched_database = Path(self.temporary_directory.name) / "other.db"
        with closing(sqlite3.connect(mismatched_database)) as connection:
            with self.assertRaisesRegex(
                RuntimeError,
                "does not match the configured isolated database path",
            ):
                builder.assert_safe_write_target(connection)

    def test_outcome_write_connection_must_match_configured_database(self):
        mismatched_database = Path(self.temporary_directory.name) / "other.db"
        with closing(sqlite3.connect(mismatched_database)) as connection:
            with self.assertRaisesRegex(
                RuntimeError,
                "does not match the configured isolated database path",
            ):
                outcome_builder.assert_safe_write_target(connection)

    def test_future_snapshot_search_preserves_timing_and_session_rules(self):
        source_timestamp = datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc)
        same_session_snapshot = {
            "timestamp": source_timestamp + timedelta(minutes=5, seconds=30),
            "spot_price": 22100.0,
        }
        later_snapshot = {
            "timestamp": source_timestamp + timedelta(minutes=6),
            "spot_price": 22200.0,
        }

        result = outcome_builder.find_future_snapshot(
            [same_session_snapshot, later_snapshot],
            source_timestamp,
            5,
        )
        self.assertIs(same_session_snapshot, result["snapshot"])
        self.assertEqual(30.0, result["delay_seconds"])

        next_session_snapshot = {
            "timestamp": datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc),
            "spot_price": 22300.0,
        }
        self.assertIsNone(
            outcome_builder.find_future_snapshot(
                [next_session_snapshot],
                source_timestamp,
                60,
            )
        )

    def test_batch_size_validation_and_continuity_across_page_boundaries(self):
        with self.assertRaises(ValueError):
            builder.build_historical_features(batch_size=0)

        expected_snapshots = builder.load_snapshot_data()
        builder.calculate_continuity(expected_snapshots)
        expected = {
            snapshot["market_snapshot_id"]: (
                snapshot["previous_snapshot_id"],
                snapshot["snapshot_interval_seconds"],
                snapshot["continuous"],
            )
            for snapshot in expected_snapshots
        }

        actual = {}
        previous_valid_snapshot = None
        for offset in range(0, 12, 3):
            page = builder.load_snapshot_data(limit=3, offset=offset)
            previous_valid_snapshot = builder.calculate_continuity(
                page,
                previous_valid_snapshot,
            )
            actual.update({
                snapshot["market_snapshot_id"]: (
                    snapshot["previous_snapshot_id"],
                    snapshot["snapshot_interval_seconds"],
                    snapshot["continuous"],
                )
                for snapshot in page
            })

        self.assertEqual(expected, actual)

    def _insert_market(self, connection, snapshot_id):
        timestamp = (BASE_TIMESTAMP + timedelta(seconds=30 * snapshot_id)).isoformat()
        connection.execute(
            """
            INSERT INTO market_snapshots (id, timestamp_utc, spot_price)
            VALUES (?, ?, ?)
            """,
            (snapshot_id, timestamp, SPOT),
        )
        return timestamp

    @staticmethod
    def _option(timestamp, snapshot_id, strike, option_type, serial, **updates):
        row = {
            "market_snapshot_id": snapshot_id,
            "timestamp_utc": timestamp,
            "expiry": EXPIRY,
            "strike": strike,
            "option_type": option_type,
            "instrument_key": (
                f"TEST-{snapshot_id}-{strike}-{option_type}-{serial}"
            ),
            "ltp": 10.0,
            "close_price": 9.0,
            "volume": 10.0 if option_type == "CE" else 20.0,
            "oi": (
                100.0 + serial if option_type == "CE"
                else 200.0 + serial
            ),
            "prev_oi": 98.0 + serial,
            "oi_change": 2.0 if option_type == "CE" else 3.0,
            "bid_price": 9.5,
            "bid_qty": 5.0,
            "ask_price": 10.5,
            "ask_qty": 6.0,
            "iv": 20.0,
            "delta": 0.5 if option_type == "CE" else -0.5,
            "gamma": 0.01,
            "theta": -1.0,
            "vega": 2.0,
            "pop": 0.6,
            "created_at_utc": timestamp,
        }
        row.update(updates)
        return row

    def _insert_rows(self, connection, rows):
        columns = tuple(rows[0])
        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(
            f"""
            INSERT INTO option_snapshots ({", ".join(columns)})
            VALUES ({placeholders})
            """,
            [tuple(row[column] for column in columns) for row in rows],
        )

    def _insert_valid_snapshot(self, connection, snapshot_id, record_count):
        timestamp = self._insert_market(connection, snapshot_id)
        strike_count = record_count // 2
        start = SPOT - ((strike_count - 1) / 2.0) * 50
        rows = []
        serial = 0
        for index in range(strike_count):
            strike = start + index * 50
            for option_type in ("CE", "PE"):
                rows.append(
                    self._option(
                        timestamp,
                        snapshot_id,
                        strike,
                        option_type,
                        serial,
                        **(
                            {
                                field: None
                                for field in (
                                    "ltp",
                                    "close_price",
                                    "bid_price",
                                    "bid_qty",
                                    "ask_price",
                                    "ask_qty",
                                    "iv",
                                    "delta",
                                    "gamma",
                                    "theta",
                                    "vega",
                                    "pop",
                                )
                            }
                            if snapshot_id == 5 and serial == 0
                            else {
                                "delta": (
                                    0.5
                                    if option_type == "CE"
                                    else -0.5
                                )
                            }
                        ),
                    )
                )
                serial += 1
        self._insert_rows(connection, rows)

    def _insert_invalid_snapshots(self, connection):
        cases = {}

        snapshot_id = 6
        timestamp = self._insert_market(connection, snapshot_id)
        cases["unequal"] = [
            self._option(timestamp, snapshot_id, strike, option_type, index)
            for index, (strike, option_type) in enumerate(
                ((SPOT, "CE"), (SPOT + 50, "CE"), (SPOT, "PE"))
            )
        ]

        snapshot_id = 7
        timestamp = self._insert_market(connection, snapshot_id)
        cases["duplicate"] = [
            self._option(timestamp, snapshot_id, strike, option_type, index)
            for index, (strike, option_type) in enumerate(
                ((SPOT, "CE"), (SPOT, "CE"), (SPOT, "PE"))
            )
        ]

        snapshot_id = 8
        timestamp = self._insert_market(connection, snapshot_id)
        cases["timestamp"] = [
            self._option(timestamp, snapshot_id, strike, option_type, index)
            for index, (strike, option_type) in enumerate(
                ((SPOT, "CE"), (SPOT, "PE"))
            )
        ]
        cases["timestamp"][0]["timestamp_utc"] = (
            datetime.fromisoformat(timestamp) + timedelta(seconds=1)
        ).isoformat()

        snapshot_id = 9
        timestamp = self._insert_market(connection, snapshot_id)
        cases["expiry"] = [
            self._option(timestamp, snapshot_id, SPOT, option_type, index)
            for index, option_type in enumerate(("CE", "PE"))
        ]
        cases["expiry"][0]["expiry"] = "2026-09-15"

        snapshot_id = 10
        timestamp = self._insert_market(connection, snapshot_id)
        cases["missing_numeric"] = [
            self._option(
                timestamp,
                snapshot_id,
                SPOT,
                option_type,
                index,
                oi=None if option_type == "CE" else 200.0,
            )
            for index, option_type in enumerate(("CE", "PE"))
        ]

        snapshot_id = 11
        timestamp = self._insert_market(connection, snapshot_id)
        cases["invalid_numeric"] = [
            self._option(
                timestamp,
                snapshot_id,
                SPOT,
                option_type,
                index,
                iv="not-a-number" if option_type == "CE" else 20.0,
            )
            for index, option_type in enumerate(("CE", "PE"))
        ]

        self._insert_rows(
            connection,
            [row for rows in cases.values() for row in rows],
        )
        self._insert_market(connection, 12)

    def test_variable_counts_are_eligible_and_invalid_snapshots_are_explained(self):
        snapshots = {
            snapshot["market_snapshot_id"]: snapshot
            for snapshot in builder.load_snapshot_data()
        }
        valid_ids = {1, 2, 3, 4, 5}
        invalid_ids = {6, 7, 8, 9, 10, 11, 12}

        self.assertEqual(valid_ids, {
            snapshot_id
            for snapshot_id, snapshot in snapshots.items()
            if snapshot["complete"]
        })
        self.assertEqual(invalid_ids, {
            snapshot_id
            for snapshot_id, snapshot in snapshots.items()
            if not snapshot["complete"]
        })
        self.assertTrue(any("matching strike coverage" in reason
                            for reason in snapshots[6]["validation_errors"]))
        self.assertTrue(any("Duplicate option contract" in reason
                            for reason in snapshots[7]["validation_errors"]))
        self.assertTrue(any("timestamp does not match" in reason
                            for reason in snapshots[8]["validation_errors"]))
        self.assertTrue(any("exactly one non-empty expiry" in reason
                            for reason in snapshots[9]["validation_errors"]))
        self.assertTrue(any("missing required numeric field 'oi'" in reason
                            for reason in snapshots[10]["validation_errors"]))
        self.assertTrue(any("field 'iv' is not a finite number" in reason
                            for reason in snapshots[11]["validation_errors"]))
        self.assertTrue(any("no option records" in reason
                            for reason in snapshots[12]["validation_errors"]))
        self.assertEqual(0, len(snapshots[5]["validation_errors"]))

    def test_snapshot_link_spot_and_strike_validation(self):
        timestamp = BASE_TIMESTAMP.isoformat()
        market = {
            "id": 20,
            "timestamp_utc": timestamp,
            "spot_price": SPOT,
        }
        rows = [
            self._option(timestamp, 20, SPOT, option_type, index)
            for index, option_type in enumerate(("CE", "PE"))
        ]
        for index, row in enumerate(rows):
            row["id"] = index + 1

        mismatched_link = [dict(row) for row in rows]
        mismatched_link[0]["market_snapshot_id"] = 21
        self.assertTrue(any(
            "links to a different market snapshot" in reason
            for reason in builder.validate_snapshot_records(
                market,
                mismatched_link,
            )
        ))

        self.assertTrue(any(
            "spot price" in reason
            for reason in builder.validate_snapshot_records(
                dict(market, spot_price=0),
                rows,
            )
        ))

        invalid_strike = [dict(row) for row in rows]
        invalid_strike[0]["strike"] = 0
        self.assertTrue(any(
            "invalid strike" in reason
            for reason in builder.validate_snapshot_records(
                market,
                invalid_strike,
            )
        ))

    def test_build_preserves_existing_rows_and_integrity_matches_raw_contracts(self):
        with closing(sqlite3.connect(self.test_database)) as connection:
            with connection:
                timestamp = connection.execute(
                    "SELECT timestamp_utc FROM market_snapshots WHERE id = 2"
                ).fetchone()[0]
                raw_option = connection.execute(
                    """
                    SELECT expiry, strike, option_type
                    FROM option_snapshots
                    WHERE market_snapshot_id = 2
                    ORDER BY id
                    LIMIT 1
                    """
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO market_features (
                        market_snapshot_id, timestamp_utc, spot_price, pcr, created_at_utc
                    ) VALUES (2, ?, ?, 777.0, 'preserve-market-row')
                    """,
                    (timestamp, SPOT),
                )
                connection.execute(
                    """
                    INSERT INTO option_features (
                        market_snapshot_id, timestamp_utc, expiry, strike,
                        option_type, ltp, created_at_utc
                    ) VALUES (2, ?, ?, ?, ?, 777.0, 'preserve-option-row')
                    """,
                    (timestamp, raw_option[0], raw_option[1], raw_option[2]),
                )

        result = builder.build_historical_features(batch_size=3)
        self.assertEqual(12, result["total_snapshots"])
        self.assertEqual(5, result["complete_snapshots"])
        self.assertEqual(7, result["skipped_incomplete"])
        self.assertEqual(4, result["market_features_created"])
        self.assertEqual(5, result["processed_snapshots"])
        self.assertEqual(4, result["batches_processed"])
        self.assertEqual(7, result["rejected_snapshots"])

        with closing(sqlite3.connect(self.test_database)) as connection:
            option_counts = dict(
                connection.execute(
                    """
                    SELECT market_snapshot_id, COUNT(*)
                    FROM option_features
                    GROUP BY market_snapshot_id
                    """
                ).fetchall()
            )
            self.assertEqual(
                {1: 210, 2: 208, 3: 216, 4: 288, 5: 166},
                option_counts,
            )
            preserved_market = connection.execute(
                """
                SELECT pcr, created_at_utc
                FROM market_features
                WHERE market_snapshot_id = 2
                """
            ).fetchone()
            self.assertEqual((777.0, "preserve-market-row"), preserved_market)

            preserved_option = connection.execute(
                """
                SELECT ltp, created_at_utc
                FROM option_features
                WHERE market_snapshot_id = 2
                  AND expiry = ?
                  AND strike = ?
                  AND option_type = ?
                """,
                raw_option,
            ).fetchone()
            self.assertEqual((777.0, "preserve-option-row"), preserved_option)

            market_210 = connection.execute(
                """
                SELECT atm_strike, total_ce_oi, total_pe_oi, pcr,
                       total_ce_oi_change, total_pe_oi_change,
                       total_ce_volume, total_pe_volume
                FROM market_features
                WHERE market_snapshot_id = 1
                """
            ).fetchone()
            self.assertEqual(SPOT, market_210[0])
            self.assertAlmostEqual(21420.0, market_210[1])
            self.assertAlmostEqual(32025.0, market_210[2])
            self.assertAlmostEqual(32025.0 / 21420.0, market_210[3])
            self.assertAlmostEqual(210.0, market_210[4])
            self.assertAlmostEqual(315.0, market_210[5])
            self.assertAlmostEqual(1050.0, market_210[6])
            self.assertAlmostEqual(2100.0, market_210[7])

            missing_optional = connection.execute(
                """
                SELECT ltp, close_price, iv, delta, gamma, theta, vega, pop,
                       bid_price, bid_qty, ask_price, ask_qty
                FROM option_features
                WHERE market_snapshot_id = 5
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
            self.assertEqual((None,) * 12, missing_optional)

        integrity = builder.verify_feature_integrity()
        self.assertEqual(0, integrity["market_duplicates"])
        self.assertEqual(0, integrity["option_duplicates"])
        self.assertEqual(0, integrity["orphan_option_features"])
        self.assertEqual(0, integrity["missing_option_features"])
        self.assertEqual(0, integrity["incomplete_feature_snapshots"])
        with closing(get_read_only_connection(self.test_database)) as connection:
            audited, orphan_raw, missing_feature_rows = (
                audit_feature_snapshots(connection)
            )
        self.assertEqual(5, len(audited))
        self.assertTrue(all(not result["errors"] for result in audited))
        self.assertEqual(0, orphan_raw)
        self.assertEqual(set(), missing_feature_rows)

        second_result = builder.build_historical_features(batch_size=2)
        self.assertEqual(0, second_result["market_features_created"])
        self.assertEqual(0, second_result["option_features_created"])
        integrity_after_repeat = builder.verify_feature_integrity()
        self.assertEqual(0, integrity_after_repeat["incomplete_feature_snapshots"])
        count_validation = feature_validation.validate_option_feature_counts()
        self.assertEqual(5, count_validation["snapshots"])
        self.assertEqual([], count_validation["invalid"])
        self.assertTrue(
            feature_validation.calculate_raw_metrics(1, SPOT)["valid"]
        )
        self.assertFalse(
            feature_validation.calculate_raw_metrics(6, SPOT)["valid"]
        )
        with closing(sqlite3.connect(self.test_database)) as connection:
            self.assertEqual(
                1088,
                connection.execute(
                    "SELECT COUNT(*) FROM option_features"
                ).fetchone()[0],
            )

        outcome_builder.initialize_outcome_table()
        source = {
            "id": 4,
            "timestamp_utc": (BASE_TIMESTAMP + timedelta(seconds=120)).isoformat(),
            "spot_price": SPOT,
        }
        outcomes = {
            horizon: {
                "price": 22100.0,
                "timestamp": source["timestamp_utc"],
                "change_points": 100.0,
                "return_pct": 0.45,
                "direction": "BULLISH",
                "delay_seconds": 0.0,
                "valid": True,
            }
            for horizon in ("5m", "15m", "30m", "60m")
        }
        outcome_builder.store_outcome(source, EXPIRY, outcomes)
        outcomes["5m"]["price"] = 1.0
        outcome_builder.store_outcome(source, EXPIRY, outcomes)
        with closing(sqlite3.connect(self.test_database)) as connection:
            row = connection.execute(
                """
                SELECT outcome_5m_price, created_at_utc
                FROM historical_outcomes
                WHERE market_snapshot_id = 4
                """
            ).fetchone()
            self.assertEqual(22100.0, row[0])
            self.assertEqual(1, connection.execute(
                "SELECT COUNT(*) FROM historical_outcomes"
            ).fetchone()[0])

    def test_interrupted_batch_resume_is_idempotent(self):
        def stop_after_first_batch(progress):
            if progress["batch"] == 1:
                raise RuntimeError("simulated interruption")

        with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
            builder.build_historical_features(
                batch_size=4,
                progress_callback=stop_after_first_batch,
            )

        with closing(sqlite3.connect(self.test_database)) as connection:
            committed = connection.execute(
                "SELECT COUNT(*) FROM market_features"
            ).fetchone()[0]
            self.assertEqual(4, committed)

        resumed = builder.build_historical_features(batch_size=2)
        self.assertEqual(5, resumed["processed_snapshots"])
        self.assertEqual(1, resumed["market_features_created"])

        with closing(sqlite3.connect(self.test_database)) as connection:
            self.assertEqual(
                5,
                connection.execute(
                    "SELECT COUNT(*) FROM market_features"
                ).fetchone()[0],
            )
            duplicate_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT market_snapshot_id
                    FROM market_features
                    GROUP BY market_snapshot_id
                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
            self.assertEqual(0, duplicate_count)

        integrity = builder.verify_feature_integrity()
        self.assertEqual(0, integrity["market_duplicates"])
        self.assertEqual(0, integrity["option_duplicates"])
        self.assertEqual(0, integrity["missing_option_features"])
        self.assertEqual(0, integrity["incomplete_feature_snapshots"])


if __name__ == "__main__":
    unittest.main()
