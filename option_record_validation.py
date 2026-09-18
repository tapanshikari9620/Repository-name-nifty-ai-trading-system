import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DB_NAME = 'nifty_market_data.db'
NUMERIC_FIELDS = ['strike','ltp','close','volume','oi','prev_oi','oi_change','bid','ask','iv','delta','gamma','vega','theta']

def finite(v):
    if v is None: return False
    try: return math.isfinite(float(v))
    except (TypeError, ValueError): return False

def valid_ts(v):
    if not v: return False
    try:
        datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return True
    except ValueError:
        return False

def main():
    p = Path(DB_NAME)
    if not p.exists():
        print(f'ERROR: Database not found: {p.resolve()}'); return 1
    conn = sqlite3.connect(f'file:{p.resolve()}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA query_only=ON')
        tables = {r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'option_snapshots' not in tables:
            print('ERROR: option_snapshots table not found.'); return 1
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(option_snapshots)')}
        if not {'id','market_snapshot_id'} <= cols:
            print('ERROR: Required columns id and market_snapshot_id are missing.'); return 1
        selected = ', '.join(sorted(cols))
        total = valid = invalid = 0
        reasons = Counter(); examples = []; per_snapshot = defaultdict(lambda: [0,0])
        seen = set()
        for row in conn.execute(f'SELECT {selected} FROM option_snapshots'):
            total += 1; rs = []; sid = row['market_snapshot_id']; per_snapshot[sid][0] += 1
            typ = str(row['option_type']).upper() if 'option_type' in cols and row['option_type'] is not None else ''
            if typ not in {'CE','PE'}: rs.append('invalid_option_type')
            key = row['instrument_key'] if 'instrument_key' in cols else None
            if not key: rs.append('missing_instrument_key')
            if 'expiry' in cols and not row['expiry']: rs.append('missing_expiry')
            for f in NUMERIC_FIELDS:
                if f in cols and not finite(row[f]): rs.append(f'invalid_{f}')
            for f in ('strike','ltp','volume','oi','prev_oi'):
                if f in cols and finite(row[f]) and float(row[f]) < 0: rs.append(f'negative_{f}')
            if 'bid' in cols and 'ask' in cols and finite(row['bid']) and finite(row['ask']) and row['bid'] > row['ask'] and row['bid'] > 0 and row['ask'] > 0:
                rs.append('bid_greater_than_ask')
            ck = (sid, key)
            if key and ck in seen: rs.append('duplicate_snapshot_instrument')
            elif key: seen.add(ck)
            if 'timestamp' in cols and not valid_ts(row['timestamp']): rs.append('invalid_timestamp')
            if rs:
                invalid += 1; per_snapshot[sid][1] += 1
                for x in set(rs): reasons[x] += 1
                if len(examples) < 20: examples.append((row['id'], sid, key, sorted(set(rs))))
            else: valid += 1
        bad_snaps = sum(1 for total_bad in per_snapshot.values() if total_bad[1])
        print('\nOPTION RECORD VALIDATION')
        print('='*80)
        print(f'Total option records          : {total}')
        print(f'Valid option records          : {valid}')
        print(f'Invalid option records        : {invalid}')
        print(f'Snapshots checked             : {len(per_snapshot)}')
        print(f'Snapshots containing invalids : {bad_snaps}')
        print('\nINVALID REASONS')
        print('-'*80)
        print('\n'.join(f'{k:35} : {v}' for k,v in reasons.most_common()) or 'None')
        print('\nINVALID RECORD EXAMPLES')
        print('-'*80)
        print('\n'.join(map(str, examples)) or 'None')
        print('\nFINAL STATUS')
        print('-'*80)
        print('OPTION RECORD VALIDATION STATUS : ' + ('PASS' if invalid == 0 else 'FAIL'))
        return 0 if invalid == 0 else 2
    finally:
        conn.close()

if __name__ == '__main__': raise SystemExit(main())
