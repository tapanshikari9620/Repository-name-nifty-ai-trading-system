
from ..database.paths import MARKET_DATABASE_PATH
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import upstox_project.features.historical_feature_builder as feature_builder


DATABASE_NAME = str(MARKET_DATABASE_PATH)
def get_connection(database_name=None):
    database_path = Path(database_name or DATABASE_NAME).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database not found: {database_path}")
    connection = sqlite3.connect(
        database_path.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def contract_key(row):
    expiry = str(row["expiry"]).strip() if row["expiry"] is not None else ""
    strike = feature_builder.finite_number(row["strike"])
    return expiry, strike, row["option_type"]


def audit_feature_snapshots(connection):
    feature_snapshot_ids = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT market_snapshot_id FROM option_features "
            "ORDER BY market_snapshot_id"
        )
    ]
    market_feature_ids = {
        row[0]
        for row in connection.execute(
            "SELECT market_snapshot_id FROM market_features"
        )
    }
    results = []

    for snapshot_id in feature_snapshot_ids:
        market = connection.execute(
            """
            SELECT id, timestamp_utc, spot_price
            FROM market_snapshots
            WHERE id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        raw_rows = connection.execute(
            "SELECT * FROM option_snapshots WHERE market_snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        feature_rows = connection.execute(
            "SELECT * FROM option_features WHERE market_snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        market_feature = connection.execute(
            """
            SELECT timestamp_utc, spot_price
            FROM market_features
            WHERE market_snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        errors = []

        if market is None:
            errors.append("Market snapshot is missing.")
        else:
            errors.extend(
                feature_builder.validate_snapshot_records(market, raw_rows)
            )
        if market_feature is None:
            errors.append("Market feature row is missing.")
        elif market is not None:
            if (
                feature_builder.parse_timestamp(market_feature["timestamp_utc"])
                != feature_builder.parse_timestamp(market["timestamp_utc"])
            ):
                errors.append("Market feature timestamp does not match raw snapshot.")
            if market_feature["spot_price"] != market["spot_price"]:
                errors.append("Market feature spot price differs from raw snapshot.")

        raw_keys = [contract_key(row) for row in raw_rows]
        feature_keys = [contract_key(row) for row in feature_rows]
        raw_contracts = set(raw_keys)
        feature_contracts = set(feature_keys)

        if len(raw_keys) != len(raw_contracts):
            errors.append("Raw snapshot contains duplicate contracts.")
        if len(feature_keys) != len(feature_contracts):
            errors.append("Feature snapshot contains duplicate contracts.")

        missing = raw_contracts - feature_contracts
        unexpected = feature_contracts - raw_contracts
        if missing:
            errors.append(f"{len(missing)} raw contracts have no feature row.")
        if unexpected:
            errors.append(f"{len(unexpected)} feature rows have no raw contract.")

        raw_by_contract = {
            contract_key(row): row
            for row in raw_rows
        }
        for feature in feature_rows:
            key = contract_key(feature)
            raw = raw_by_contract.get(key)
            if raw is None:
                continue
            if market is None or (
                feature_builder.parse_timestamp(feature["timestamp_utc"])
                != feature_builder.parse_timestamp(market["timestamp_utc"])
            ):
                errors.append("Feature timestamp does not match market snapshot.")
                break

        feature_ce = {
            key[1] for key in feature_contracts if key[2] == "CE"
        }
        feature_pe = {
            key[1] for key in feature_contracts if key[2] == "PE"
        }
        results.append({
            "market_snapshot_id": snapshot_id,
            "raw_count": len(raw_rows),
            "feature_count": len(feature_rows),
            "feature_ce_count": sum(
                row["option_type"] == "CE" for row in feature_rows
            ),
            "feature_pe_count": sum(
                row["option_type"] == "PE" for row in feature_rows
            ),
            "paired": bool(feature_ce) and feature_ce == feature_pe,
            "errors": sorted(set(errors)),
        })

    orphan_raw = connection.execute(
        """
        SELECT COUNT(*)
        FROM option_snapshots o
        LEFT JOIN market_snapshots m ON m.id = o.market_snapshot_id
        WHERE m.id IS NULL
        """
    ).fetchone()[0]
    missing_option_features = market_feature_ids - set(feature_snapshot_ids)
    return results, orphan_raw, missing_option_features


def main(database_name=None):
    with closing(get_connection(database_name)) as connection:
        results, orphan_raw, missing_option_features = (
            audit_feature_snapshots(connection)
        )

    failed = [
        item for item in results
        if item["errors"] or not item["paired"]
    ]
    count_distribution = {}
    for result in results:
        count_distribution[result["feature_count"]] = (
            count_distribution.get(result["feature_count"], 0) + 1
        )

    print("=" * 72)
    print("VARIABLE-SIZED FEATURE UNIVERSE CONSISTENCY TEST")
    print("READ-ONLY — raw contract count may vary by snapshot")
    print("=" * 72)
    print(f"Feature snapshots checked : {len(results)}")
    print(f"Invalid snapshots          : {len(failed)}")
    print(f"Orphan raw option rows     : {orphan_raw}")
    print("Feature row counts:")
    for record_count, count in sorted(count_distribution.items()):
        print(f"  {record_count:>4} contracts : {count} snapshots")

    for result in failed[:50]:
        print(
            f"FAIL snapshot={result['market_snapshot_id']} "
            f"raw={result['raw_count']} features={result['feature_count']}"
        )
        for error in result["errors"]:
            print(f"  - {error}")
        if not result["paired"]:
            print("  - CE and PE strikes are not paired.")

    if missing_option_features:
        print(
            "Market feature snapshots without option features: "
            f"{len(missing_option_features)}"
        )
    passed = not failed and orphan_raw == 0 and not missing_option_features
    print("=" * 72)
    print(
        "FEATURE UNIVERSE CONSISTENCY STATUS : "
        + ("PASS" if passed else "FAIL")
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
