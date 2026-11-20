# NIFTY project architecture audit

**Audit date:** 2026-10-20  
**Scope:** Repository and SQLite inspection; the original databases were opened read-only. No feature/outcome rebuild, model training, collector run, migration, or order execution was performed.

## Overall status

The repository has a working market-data collector, historical feature and outcome builders, live signal-analysis modules, and read-only quality checks. It is not an end-to-end ML/trading application: `main.py` is a starter stub, no model-training or chronological-split implementation was found, and no broker order-placement call was found. The application is therefore **not ready for final model training or live trading**. Continue collection only under the existing controlled schedule; do not use the current features as a final training dataset.

The raw database passed SQLite `integrity_check` (`ok`) and `foreign_key_check` (zero violations). It contains 16,346 market snapshots and 3,467,828 option records, while derived feature/outcome tables cover only 3,013 snapshots. The original `nifty_market_data.db` and `nifty_signal_history.db` were not modified.

## Repository inventory

The project root contains the following application modules and scripts. The list is grouped by role; it does not imply that every diagnostic/test script is safe to run.

| Group | Files and observed role |
|---|---|
| Configuration/API/collection | `config.py` (configuration loaded from local environment), `upstox_api.py` (contract/expiry and option-chain HTTP GETs), `option_snapshot_collector.py` (60-second market-hours collection loop, validation, health logging), `collection_health.py` (collection health persistence), `market_snapshot.py` (underlying snapshot persistence), `option_snapshot.py` (raw option records and schema/index initialization), `option_snapshot_validation.py`, `market_snapshot_validation.py` |
| Feature analysis | `feature_engine.py` (live option-chain parsing and ATM-window calculations), `historical_feature_builder.py` (fixed-210 historical eligibility, aggregate feature generation, storage and integrity checks), `historical_feature_store.py`, `feature_validator.py`, `market_analyzer.py`, `option_chain.py`, `option_analysis.py` |
| Outcomes/signals | `historical_outcome_builder.py` (historical spot labels and persistence), `outcome_engine.py`, `outcome_live.py`, `signal_engine.py` (heuristic signals), `signal_logger.py` (separate local signal-history DB), `evidence_engine.py`, `evidence_analysis_live.py`, `signal_analysis_live.py`, `signal_logging_live.py`, `market_analysis_live.py`, `market_snapshot_live.py` |
| Data inspection/readiness | `database_schema_inspection.py`, `market_snapshot_inspection.py`, `option_snapshot_inspection.py`, `option_snapshot_inspection_v2.py`, `daily_data_quality_report.py`, `dataset_quality.py`, `historical_feature_validation.py`, `ml_dataset_validation.py`, `leakage_test.py`, `application_health_check.py` |
| Audits/tests | `pipeline_freshness_coverage_test.py`, `missing_feature_time_audit.py`, `variable_chain_eligibility_audit.py`, `feature_compatibility_audit.py`, `feature_universe_consistency_test.py`, `feature_universe_pair_consistency_test.py`, `check_option_features_schema.py`, `option_record_validation.py`, `option_snapshot_test.py`, `market_snapshot_test.py`, `feature_test_live.py`, `feature_validation_live.py`, `test_market_snapshot_inspection.py`, `qa_final_test.py`, `verify_fixes.py`, `websocket_test.py`, `test_ml_readiness.py`, `test_experimental_variable_chain_builder.py` |
| Isolated experiment | `experimental_variable_chain_builder.py` (`paired_atm_v1`; creates and writes only to an explicitly named database copy) |
| Other | `main.py` (PyCharm sample stub, not an orchestrator), `display.py`, `database_backup.py`, `requirements.txt`, `run_database_backup.bat`, historical `QA_SUMMARY.txt` and `QA_COMPLETION_SUMMARY.txt` |

`.env` exists but was not read or copied into reports. The working tree was already dirty when the audit began; existing staged/unstaged audit-script edits were preserved.

## Current data lifecycle and execution order

1. `option_snapshot_collector.run_collector()` applies the existing weekday/09:15–15:30 IST gate and 60-second cadence.
2. `upstox_api.get_option_chain()` fetches the nearest-expiry contracts and option chain using HTTP GET. The collector checks the response structure, extracts spot, and stamps a single UTC collection time.
3. `market_snapshot.store_snapshot()` writes the market row. `option_snapshot.store_option_snapshot()` initializes its schema if needed, then writes the CE/PE side records. These writes are not one atomic transaction across both tables. The collector validates stored counts/records and logs success/failure in `collection_health`; on a failed new collection it attempts to delete that just-created partial snapshot.
4. `historical_feature_builder.build_historical_features()` loads raw rows and health records, rejects snapshots not marked complete under the fixed 210-record/105 CE/105 PE rule, applies structural/health checks, calculates full-chain market aggregates, and stores market and option features separately.
5. `historical_outcome_builder.build_historical_outcomes()` uses eligible feature snapshot IDs and future underlying spot snapshots to build 5/15/30/60-minute labels, then stores them.
6. `dataset_quality.py`, `historical_feature_validation.py`, `ml_dataset_validation.py`, and `leakage_test.py` report on derived data. `ml_dataset_validation.py` constructs temporary read-only datasets; it does not train a model.
7. Live signal analysis and logging are separate. `signal_logger.py` writes to `nifty_signal_history.db`. No broker order-placement implementation was found. External Windows Task Scheduler configuration was not available for verification.

`signal_engine.py` is a hand-coded evidence score with fixed strength, score-difference, and confidence thresholds; its documentation says confidence is not statistical probability and the module is not a validated strategy. It does not select contracts or place orders.

## Database schema and relationships

`nifty_market_data.db` has six application tables:

| Table | Rows | Key/relationship summary |
|---|---:|---|
| `market_snapshots` | 16,346 | Integer primary key; timestamp index. |
| `option_snapshots` | 3,467,828 | Integer primary key; FK `market_snapshot_id -> market_snapshots.id` with cascade delete; unique `(market_snapshot_id, instrument_key)` index plus timestamp, parent, and contract indexes. |
| `collection_health` | 16,315 | Integer primary key and timestamp/status indexes; no FK to market rows. |
| `market_features` | 3,013 | Integer primary key; unique `market_snapshot_id` and timestamp index; no declared FK. |
| `option_features` | 632,730 | Integer primary key; unique `(market_snapshot_id, expiry, strike, option_type)` plus timestamp and contract indexes; no declared FK. |
| `historical_outcomes` | 3,013 | Integer primary key; unique `market_snapshot_id` and timestamp index; no declared FK. |

The derived tables have unique source identifiers in the current schema, but the feature/outcome relationships rely on application logic rather than foreign keys. Current orphan checks found zero orphans. `nifty_signal_history.db` is separate and contains two application tables (`market_snapshots` with seven rows and `signal_snapshots` with one row); it is a signal log, not the historical training database. This corrects the earlier count discrepancy: the primary database has six application tables, not seven; SQLite internal tables are excluded.

## Safe-to-run and mutating operations

The audit used these read-only diagnostics: `pipeline_freshness_coverage_test.py`, `variable_chain_eligibility_audit.py`, `missing_feature_time_audit.py`, `feature_compatibility_audit.py`, `historical_feature_validation.py`, `leakage_test.py`, `ml_dataset_validation.py`, and `dataset_quality.py`. The latter two now explicitly use read-only/query-only access. `qa_final_test.py` and `test_market_snapshot_inspection.py` were also run; their database paths only read snapshots.

Do **not** treat the following as read-only: `option_snapshot_collector.py`, schema initializers in `market_snapshot.py`/`option_snapshot.py`/`collection_health.py`, `historical_feature_builder.py`, `historical_outcome_builder.py`, signal logging/update functions, and `database_backup.py` (writes a backup). `experimental_variable_chain_builder.py --create-copy` creates a new ignored DB copy; its experiment mode writes two additive tables only to the explicitly named copy and refuses the original database path. Live/API scripts may call Upstox. The backup batch file invokes `venv\Scripts\python.exe`; the audit interpreter was `.venv\Scripts\python.exe`, so the batch environment was not verified.

Not run: feature/outcome builders, collector, live/API scripts, backup/restore, and diagnostics with unverified side effects (including `option_record_validation.py` and other `*_live.py`/`*_test.py` scripts). The original DB was not used for an experimental rebuild. The audit did not inspect every line of every peripheral UI/live script; those paths remain outside the verified execution trace.

## Baseline and tests

- `PRAGMA integrity_check`: `ok`; `PRAGMA foreign_key_check`: 0 rows.
- Existing read-only feature validation: 3,013/3,013 market-feature rows passed its current checks; option-feature count was exactly 210 for each of those snapshots.
- Isolated `paired_atm_v1` regression tests: 12 experiment tests plus four readiness tests passed. On a separate DB copy the experiment added 16,293 feature rows (including 13,280 variable-chain snapshots); original feature coverage remains 3,013 snapshots/9 sessions. The experiment is not a historical rebuild approval.
- Existing leakage test passed its implemented checks. Independent reconstruction of all stored outcome values/timestamps/directions found zero mismatches and zero cross-date outcomes. This does not validate chronological train/test splitting.
- `qa_final_test.py` initially failed to print its Unicode checkmarks under Windows cp1252. With `PYTHONUTF8=1`, its 8 module smoke/import checks passed. Its previous “ready for production” message was not supported by those checks and was replaced with a statement that readiness is not assessed.
- `test_market_snapshot_inspection.py` initially returned 3/5 because two assertions were inconsistent with `sqlite3.Row` key semantics and adjacent-only movement handling. The assertions were corrected without changing production behavior; the rerun passed 5/5.
- New `test_ml_readiness.py`: 4 tests passed, including IST market-hour session counting and read-only DB access. `dataset_quality.py` now reports 9/120 and RESEARCH DATA GATE NOT MET. `ml_dataset_validation.py` passes with 17 candidate columns after excluding the surrogate `id`.

## Principal findings

| Severity | Finding | Status |
|---|---|---|
| High | 13,280 option-bearing snapshots have variable chain sizes and are excluded by the exact-210 historical builder gate. Structural/health checks pass for these snapshots, but field semantics/freshness are not yet sufficient to approve rebuilding. | Root cause confirmed; rebuild/policy deferred. |
| High | Dataset readiness previously passed at 9 feature-covered sessions because the code only warned below five. | Fixed: the 120-session threshold is now a blocking gate, and dates are counted in IST market hours. |
| High | There is no chronological validation/split/purge implementation or final training pipeline. Overlapping horizons and same-session dependence remain downstream leakage risks. | Unresolved; no final model trained. |
| Medium | `id` was included among candidate model inputs. | Fixed and regression-tested. |
| Medium | Feature helpers can normalize missing/invalid inputs to zero; IV/theta ranges need source interpretation and quotes lack exchange timestamps for freshness tests. | Unresolved; no field definitions changed. |
| Medium | Historical and live support/resistance definitions differ; derived tables have no FK constraints; feature and option-feature writes are separate. | Unresolved; no schema or feature migration. |

The historical QA text files make older production-readiness claims based on an earlier/smaller dataset. They were left intact but must not be used as current readiness evidence.
