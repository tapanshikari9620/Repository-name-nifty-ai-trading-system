# Database and raw-data quality report

**Audit date:** 2026-10-20  
**Database:** `nifty_market_data.db` (read-only); separate `nifty_signal_history.db` also inspected read-only.

## Executive summary

The primary database is structurally readable and currently has no foreign-key violations, duplicate market timestamps, duplicate option contracts per snapshot, or orphaned option/feature/outcome rows in the checks performed. It is nevertheless incomplete for historical modeling: 13,280 of 16,293 option-bearing snapshots have no market features, the existing derived set covers only nine IST trading dates, collection gaps exist, and option quote/Greek fields have substantial zero and extreme-value populations whose source meaning has not been established.

No table was rebuilt, migrated, deleted, or written during this audit.

## Current counts, ranges, and coverage

| Measure | Current result |
|---|---:|
| `market_snapshots` | 16,346 |
| `option_snapshots` | 3,467,828 |
| Market snapshots with options | 16,293 / 16,346 (99.68%) |
| Market snapshots without options | 53 / 16,346 (0.32%) |
| `market_features` | 3,013 / 16,346 market snapshots (18.43%) |
| `option_features` | 632,730 = 210 rows × 3,013 feature snapshots |
| `historical_outcomes` | 3,013; aligned to all 3,013 feature snapshots |
| Option-bearing snapshots without features | 13,280 / 16,293 (81.51%) |
| Feature-covered IST trading sessions | 9 |
| Option-bearing IST trading sessions | 46 |
| Raw option expiries / distinct instrument keys | 10 / 2,072 |

Raw market timestamps span `2026-08-12T11:36:47Z` to `2026-10-19T09:59:38Z`; option data span `2026-08-13` to `2026-10-19`; market features and outcomes span `2026-08-13` to `2026-09-01`. The primary DB’s snapshot rows span 47 IST calendar dates, but only 46 have options; three early records on 2026-08-12 occurred outside regular market hours and have no option data.

The nine feature-covered IST dates and feature rows are: Aug 13 197; Aug 14 335; Aug 17 375; Aug 18 375; Aug 26 375; Aug 27 291; Aug 28 317; Aug 31 373; Sep 1 375. There are no market features/outcomes after Sep 1 even though raw snapshots continue through Oct 19.

## Lineage, duplicates, orphans, and integrity

- SQLite `integrity_check`: `ok`; `foreign_key_check`: zero violations.
- Duplicate market timestamp groups: 0.
- Duplicate `(market_snapshot_id, instrument_key)` groups: 0; null option instrument keys: 0.
- Option rows without a market parent: 0.
- Market-feature or outcome rows without a market parent: 0 in explicit left-join checks.
- Duplicate feature timestamps/source groups: 0.
- All option-row timestamps matched their parent market timestamp in the comparison run; no raw expiry preceded its snapshot date.
- Options comprise 1,733,914 CE and 1,733,914 PE rows; no other option types were found.
- `collection_health`: 16,315 rows (16,272 `SUCCESS`/`PASS`, 43 `FAILED`). The 43 failed health entries have no market-snapshot link. 74 market snapshots have no health entry; this includes the 53 no-option rows and 21 other snapshots.

`option_snapshots` has a foreign key to `market_snapshots`; `market_features`, `option_features`, `historical_outcomes`, and `collection_health` do not. Current orphan counts are zero, but referential integrity for these tables is not enforced by SQLite.

## Missingness, numerical observations, and timestamps

All scanned numeric columns in the raw option table had zero SQL NULLs; stored zeros are present and must not be assumed to mean “missing” without source documentation. Market-feature numeric columns also had zero SQL NULLs. Market spot values were non-null and positive: minimum 22,186.10, maximum 24,435.95. All audited timestamps parsed; raw option/market parent times matched.

| Raw-field observation | Count / range | Interpretation |
|---|---:|---|
| Option LTP equal to zero | 415,426 / 3,467,828 (11.98%) | Could represent no trade/unavailable quote; no source quote timestamp distinguishes these states. |
| IV equal to zero | 984,697 / 3,467,828 (28.40%), present in all 16,293 option-bearing snapshots | Meaning is unverified; do not treat as a valid implied volatility or impute a different value. |
| IV greater than 150 | 189,725 rows in 5,719 snapshots (5.47% of option rows) | High values require source-unit/validity interpretation; 11 rows are at least 999, maximum 999.98. Not automatically declared invalid. |
| Theta less than -100 / -1,000 | 156,174 / 28,018 rows | Minimum -153,967.9901; field units/scaling and source validity are unverified. |
| Bid and ask both zero | 212 rows | Quote absence/semantics are unverified. |
| Bid greater than ask where both positive | 0 | No crossed positive bid/ask pairs found. |
| OI change inconsistent with `oi - prev_oi` | 0 | Arithmetic is consistent; meaning/time reference of source `prev_oi` remains unverified. |
| Delta range | -1 to 1 | No bound violation observed. |
| Volume / OI maxima | 2,433,856,295 / 59,415,200 | Units and acceptable magnitudes are not established by the repository; no arbitrary plausibility cap applied. |

The collector stamps collection time, not an exchange quote time. Thus quote staleness and internal quote-time coherence cannot be measured from the persisted schema. The collector uses a single option-chain response and one local UTC timestamp, which supports common collection-time alignment but does not prove each side’s quote was fresh at that instant.

## Collection cadence and gaps

The collector is configured for 60-second cadence during 09:15–15:30 IST. Across 46 option-bearing sessions, raw snapshot counts ranged from 189 to 376 (median 374); 12 sessions had fewer than 360 snapshots and five had fewer than 300. Within regular market hours, median adjacent interval was about 60 seconds; 16 intervals exceeded 90 seconds, 15 exceeded 120 seconds, and the maximum was 2,964.89 seconds (about 49.4 minutes). No data were fabricated to bridge gaps.

`dataset_quality.py` also reports 12 large gaps and a 668,761-second maximum between feature observations. That continuity calculation spans session closures and must not be interpreted as 12 intraday collector failures; use session-aware interval analysis for collection health.

## Snapshot eligibility assessment

Of 16,346 market snapshots:

- 3,013 are already feature-covered under the legacy fixed-210 rule.
- 13,280 have option rows but no features. The variable-chain audit found all 13,280 structurally paired CE/PE strike sets, one expiry, no duplicate contract keys, parseable times, positive spot, and passing collection-health status. They each have at least 30 strikes below and 42 above spot, and cover at least ±500 and ±1,000 spot points.
- 53 contain no option rows.

The 13,280 variable-chain record-count frequencies are: 166:374; 172:375; 174:1,126; 176:375; 182:746; 184:375; 192:1,846; 208:1,243; 214:739; 216:1,690; 232:748; 242:1,852; 256:744; 276:672; 288:375. Their unique-strike counts range 83–144 (median 107). The legacy builder’s exact-210 (105 CE + 105 PE) check is the demonstrated gate excluding these snapshots.

Structural pairing and breadth do not establish quote freshness or trustworthy Greeks/required numeric semantics. No variable-sized snapshots were admitted and no historical rebuild was run.

## Read-only reproducibility

Use the project virtual environment from the repository root:

```powershell
& .\.venv\Scripts\python.exe .\pipeline_freshness_coverage_test.py
& .\.venv\Scripts\python.exe .\variable_chain_eligibility_audit.py
& .\.venv\Scripts\python.exe .\missing_feature_time_audit.py
& .\.venv\Scripts\python.exe .\feature_compatibility_audit.py
```

These project audit scripts were run against the existing DB and did not alter it. Direct schema/integrity/anomaly probes used SQLite URI `mode=ro` and `PRAGMA query_only=ON`.
