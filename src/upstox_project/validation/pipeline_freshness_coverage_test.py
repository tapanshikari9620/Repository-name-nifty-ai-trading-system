
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3
import os
from collections import Counter
from pathlib import Path

DB_NAME = str(MARKET_DATABASE_PATH)

def cols(conn, table):
    return {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}

def pick(c, names):
    return next((x for x in names if x in c), None)

def main():
    db=Path(DB_NAME)
    if not db.exists():
        print(f'ERROR: Database not found: {db.resolve()}'); return 1
    conn=sqlite3.connect(f'file:{db.resolve()}?mode=ro', uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    try:
        tables={r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required={'market_snapshots','option_snapshots','market_features','historical_outcomes'}
        if required-tables:
            print('ERROR: Missing tables:', sorted(required-tables)); return 1
        mc,oc,fc,hc=(cols(conn,t) for t in ['market_snapshots','option_snapshots','market_features','historical_outcomes'])
        opt_fk=pick(oc,['market_snapshot_id']); feat_fk=pick(fc,['market_snapshot_id','snapshot_id']); out_fk=pick(hc,['market_snapshot_id','snapshot_id'])
        if not opt_fk or not feat_fk or not out_fk:
            print('ERROR: Required snapshot link column not found.'); return 1
        raw_ids={r['id'] for r in conn.execute('SELECT id FROM market_snapshots')}
        option_counts={r['sid']:r['n'] for r in conn.execute(f'SELECT {opt_fk} sid, COUNT(*) n FROM option_snapshots GROUP BY {opt_fk}')}
        with_options=set(option_counts)
        feature_ids={r['sid'] for r in conn.execute(f'SELECT DISTINCT {feat_fk} sid FROM market_features WHERE {feat_fk} IS NOT NULL')}
        outcome_ids={r['sid'] for r in conn.execute(f'SELECT DISTINCT {out_fk} sid FROM historical_outcomes WHERE {out_fk} IS NOT NULL')}
        raw_with_options=raw_ids & with_options
        missing_all=raw_ids-feature_ids
        missing_eligible=raw_with_options-feature_ids
        exact210={sid for sid in missing_eligible if option_counts.get(sid)==210}
        non210=Counter(option_counts.get(sid,0) for sid in missing_eligible if option_counts.get(sid,0)!=210)
        feature_without_raw=feature_ids-raw_ids
        feature_without_outcome=feature_ids-outcome_ids
        outcome_without_feature=outcome_ids-feature_ids
        print('\n'+'='*82); print('PIPELINE FRESHNESS & COVERAGE TEST - READ ONLY'); print('='*82)
        print('\nRAW DATA\n'+'-'*82)
        print(f'Market snapshots                  : {len(raw_ids)}')
        print(f'Snapshots containing options      : {len(raw_with_options)}')
        print(f'Market snapshots without options  : {len(raw_ids-raw_with_options)}')
        print(f'Option records                    : {sum(option_counts.values())}')
        print('\nFEATURE COVERAGE\n'+'-'*82)
        print(f'Feature snapshots                 : {len(feature_ids)}')
        print(f'Raw snapshots missing features    : {len(missing_all)}')
        print(f'Raw+option snapshots missing feat.: {len(missing_eligible)}')
        print(f'Missing snapshots with exactly 210 : {len(exact210)}')
        print('\nMISSING FEATURE SNAPSHOT OPTION COUNTS\n'+'-'*82)
        if non210:
            for n,q in sorted(non210.items()): print(f'{n:4} option records : {q} snapshots')
        else: print('None')
        print('\nOUTCOME COVERAGE\n'+'-'*82)
        print(f'Outcome snapshots                 : {len(outcome_ids)}')
        print(f'Feature snapshots without outcomes: {len(feature_without_outcome)}')
        print(f'Outcome rows without features     : {len(outcome_without_feature)}')
        print('\nORPHAN / INTEGRITY\n'+'-'*82)
        print(f'Features pointing to missing raw   : {len(feature_without_raw)}')
        print('\nSTATUS\n'+'-'*82)
        if (
            missing_eligible
            or feature_without_raw
            or feature_without_outcome
            or outcome_without_feature
        ):
            print('PIPELINE COVERAGE STATUS : REVIEW REQUIRED')
        else:
            print('PIPELINE COVERAGE STATUS : PASS')
        print('\nThis is READ ONLY. It does not modify the database.')
        return 0
    finally: conn.close()
if __name__=='__main__': raise SystemExit(main())
