import sqlite3
from datetime import datetime, timezone

DATABASE_NAME = "nifty_market_data.db"
MAX_FUTURE_DELAY_SECONDS = 90.0
HORIZONS = {"5m": 5, "15m": 15, "30m": 30, "60m": 60}

def parse_ts(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None

def get_connection():
    conn = sqlite3.connect(f"file:{DATABASE_NAME}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn

def main():
    print("=" * 70)
    print("LOOK-AHEAD / DATA LEAKAGE TEST")
    print("=" * 70)
    print("\nDatabase mode : READ-ONLY")
    print("No database changes will be made.\n")

    conn = get_connection()
    failures = []
    checked = {h: 0 for h in HORIZONS}

    try:
        total = conn.execute("SELECT COUNT(*) FROM historical_outcomes").fetchone()[0]
        features = conn.execute("SELECT COUNT(*) FROM market_features").fetchone()[0]
        print(f"Historical outcome rows : {total}")
        print(f"Market feature rows    : {features}\n")

        rows = conn.execute("""
            SELECT market_snapshot_id, timestamp_utc,
                   outcome_5m_timestamp, outcome_5m_valid, outcome_5m_delay_seconds,
                   outcome_15m_timestamp, outcome_15m_valid, outcome_15m_delay_seconds,
                   outcome_30m_timestamp, outcome_30m_valid, outcome_30m_delay_seconds,
                   outcome_60m_timestamp, outcome_60m_valid, outcome_60m_delay_seconds
            FROM historical_outcomes
            ORDER BY timestamp_utc, market_snapshot_id
        """).fetchall()

        print("TEST 1 - FUTURE OUTCOME TIMING")
        print("-" * 70)
        for row in rows:
            source = parse_ts(row["timestamp_utc"])
            if source is None:
                failures.append(f"invalid source timestamp id={row['market_snapshot_id']}")
                continue

            for h, minutes in HORIZONS.items():
                valid = row[f"outcome_{h}_valid"]
                future = parse_ts(row[f"outcome_{h}_timestamp"])
                delay = row[f"outcome_{h}_delay_seconds"]

                if valid == 1:
                    checked[h] += 1
                    expected = minutes * 60
                    if future is None:
                        failures.append(f"{h}: valid but missing timestamp id={row['market_snapshot_id']}")
                        continue
                    delta = (future - source).total_seconds()
                    if delta < expected:
                        failures.append(f"{h}: future timestamp before target id={row['market_snapshot_id']} delta={delta:.2f}s")
                    if delta > expected + MAX_FUTURE_DELAY_SECONDS:
                        failures.append(f"{h}: delay >90s id={row['market_snapshot_id']} delta={delta:.2f}s")
                    if delay is None or delay < 0 or delay > MAX_FUTURE_DELAY_SECONDS:
                        failures.append(f"{h}: invalid delay={delay} id={row['market_snapshot_id']}")
                elif future is not None:
                    failures.append(f"{h}: unavailable but has future timestamp id={row['market_snapshot_id']}")

        for h in HORIZONS:
            print(f"Valid {h:>3} outcomes checked : {checked[h]}")

        print("\nTEST 2 - FEATURE / OUTCOME SOURCE ALIGNMENT")
        print("-" * 70)
        joined = conn.execute("""
            SELECT mf.market_snapshot_id, mf.timestamp_utc AS feature_ts,
                   ho.timestamp_utc AS outcome_ts
            FROM market_features mf
            JOIN historical_outcomes ho
              ON ho.market_snapshot_id = mf.market_snapshot_id
        """).fetchall()
        for row in joined:
            if parse_ts(row["feature_ts"]) != parse_ts(row["outcome_ts"]):
                failures.append(f"feature/source timestamp mismatch id={row['market_snapshot_id']}")
        print(f"Joined feature/outcome rows : {len(joined)}")

        print("\nTEST 3 - CROSS-DATE CONTAMINATION")
        print("-" * 70)
        cross_date = 0
        for row in rows:
            source = parse_ts(row["timestamp_utc"])
            if source is None:
                continue
            for h in HORIZONS:
                if row[f"outcome_{h}_valid"] != 1:
                    continue
                future = parse_ts(row[f"outcome_{h}_timestamp"])
                if future and future.date() != source.date():
                    cross_date += 1
                    failures.append(
                        f"{h}: cross-date outcome id={row['market_snapshot_id']} "
                        f"{source.isoformat()} -> {future.isoformat()}"
                    )
        print(f"Cross-date violations : {cross_date}")

        print("\nRESULT SUMMARY")
        print("-" * 70)
        print(f"Total violations : {len(failures)}")
        if failures:
            print("\nFIRST 50 FAILURES")
            for item in failures[:50]:
                print("FAIL :", item)
            print("\nLEAKAGE TEST STATUS : FAIL")
            raise SystemExit(1)

        print("LEAKAGE TEST STATUS : PASS")
        print("No timing, source-alignment, or cross-date violations detected.")
        print("=" * 70)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
