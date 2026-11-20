# Audit code changelog

**Audit date:** 2026-10-20

## Evidence-backed changes

| File | Change | Reason / evidence | Validation and compatibility |
|---|---|---|---|
| `dataset_quality.py` | Added a blocking 120-session threshold; count sessions from parseable feature timestamps converted to Asia/Kolkata and inside 09:15–15:30. Open the DB read-only/query-only. Label the result as a research-data gate, not ML/production readiness. | Baseline quality report incorrectly showed READY at 9 sessions because it only warned below 5; user requirement is at least 120 sessions. | `dataset_quality.py` now reports 9/120 and RESEARCH DATA GATE NOT MET. Tests cover 119/120 sessions, IST market-hour counting, and read-only access. No schema or stored data change. |
| `ml_dataset_validation.py` | Excluded the market-feature table’s surrogate `id` via `select_candidate_features()`. | The pre-change validator selected `id` as one of 18 candidate model features. | Validator now reports 17 candidate features and passes all read-only structural checks. New regression test verifies IDs/timestamps are excluded. |
| `qa_final_test.py` | Replaced its “project ready for production” claim with “smoke tests passed; dataset and production readiness not assessed.” | The suite performs smoke/import checks, not comprehensive financial-data, ML-split, or operational validation. | UTF-8 run passes 8 smoke/import checks and now avoids an unsupported readiness claim. |
| `test_ml_readiness.py` | Added four standard-library unit tests for the 120-session gate, IST session counting, read-only access, and feature-column exclusions. | Regression coverage for the above fixes. | `python -m unittest -v test_ml_readiness`: 4/4 passed. |
| `experimental_variable_chain_builder.py` | Added isolated `paired_atm_v1` eligibility/feature evaluation, WAL-consistent database-copy creation, an original-database path refusal, and additive versioned experiment tables. | The legacy historical builder rejects all non-210 chains; structural audit showed 13,280 missing-feature snapshots with paired variable chains. | Copy-only run: 16,293/16,293 option-bearing snapshots eligible, 3,013 pre-existing plus 13,280 newly eligible. No write to original DB; repeat run stable. |
| `test_experimental_variable_chain_builder.py` | Added regression tests for chain structure, eligibility, numeric/health validation, original-path refusal, hand-calculated full/ATM11 formulas, and idempotency. | Protect the experiment without changing the legacy builder or its stored records. | Combined experiment/readiness suite: 16/16 passed; IDE lint and compilation clean. |
| `test_market_snapshot_inspection.py` | Corrected SQLite `Row` key validation to use `.keys()` and fixed movement expectations to skip invalid adjacent pairs without bridging them; added a valid adjacent-pair assertion. | The prior standalone test falsely failed because `sqlite3.Row` membership checks values, and expected movements across invalid intervening observations. | Standalone suite now passes 5/5 without changing market-analysis behavior. |
| `application_health_check.py` | Replaced a Unicode arrow in terminal output with ASCII. | The check raised `UnicodeEncodeError` under the default Windows cp1252 console after completing its DB checks. | Default-console rerun completed successfully; no database behavior changed. |
| `feature_universe_consistency_test.py` | Made the strict global-universe test return a nonzero process status when its printed result is FAIL. | The script found legitimate contract-universe changes but previously exited successfully, which could mislead automation. | The strict test now signals its expected failure; the paired per-snapshot consistency test passes. |
| `pipeline_freshness_coverage_test.py` | Treat any option-bearing raw snapshot missing features as requiring review, rather than only flagging missing exact-210 snapshots. | The prior logic printed coverage PASS while 13,280 option-bearing snapshots had no features. | Rerun now reports `PIPELINE COVERAGE STATUS : REVIEW REQUIRED`; no database data changed. |
| `audit_reports\PROJECT_ARCHITECTURE_AUDIT.md` | Corrected primary application-table count from seven to six and documented two tables in the signal-history DB. | Read-only enumeration found six primary tables and two signal DB tables; SQLite internal tables excluded. | Read-only current table inventory confirmed. |
| `audit_reports\FEATURE_ENGINEERING_AUDIT.md` | Documented the experimental policy, formulas, coverage/rejections, remaining source semantics and isolated regression results. | Record copy-only measurements without treating coverage expansion as ML or rebuild approval. | Experiment results and second-run idempotency recorded. |
| `audit_reports\ML_READINESS_REPORT.md` | Clarified that copy-only coverage across 46 sessions is not part of the original ML dataset and does not meet the 120-session gate. | Avoid confusing experiment coverage with training-data readiness. | Consistent with the read-only database baseline. |
| `audit_reports\VARIABLE_CHAIN_EXPERIMENT.md` | Added a standalone evidence report with versioned rules, per-rule measurements, formulas, feature coverage and validation outcome. | Make the experiment decision and its limits reviewable without conflating it with legacy data. | Matches copy-only run, read-only baseline and regression outputs. |

## Before/after

| Measure | Before | After |
|---|---|---|
| `dataset_quality.py` session gate | Below 5 was only a warning; 9 sessions reported READY. | Below 120 blocks; current 9/120 reports RESEARCH DATA GATE NOT MET. A future pass is explicitly not ML/production approval. |
| Candidate ML columns | 18, including database `id`. | 17, excluding surrogate ID and metadata columns. |
| Smoke-suite conclusion | Printed “PROJECT IS READY FOR PRODUCTION” on shallow test success. | Explicitly states dataset/production readiness is not assessed. |
| Variable-chain feature coverage | 3,013/16,346 market snapshots, covering 9 IST sessions. | Isolated-copy experiment: 16,293/16,346 snapshots, all 16,293 option-bearing snapshots, across 46 sessions. Original remains at baseline coverage. |
| Main database application tables | Audit text reported seven. | Corrected to six; signal-history DB has two. |
| Original databases | Not changed. | Not changed; experimental data is only in the ignored copy `audit_reports\experimental\paired_atm_v1.db`. |

## Unchanged by design

No collector behavior, legacy feature formula, outcome definition, original database schema/raw row, or legacy exact-210 acceptance rule was changed. The separately versioned experimental policy writes only additive tables in the ignored database copy; its features were not transferred to the original. No historical feature/outcome builder was run, no migration was applied, no model was trained, and no order action was taken. Coverage expansion on a copy is not approval for a historical rebuild.

## Test record

- New readiness tests: 4 passed.
- Variable-chain experiment tests: 12 passed; combined with readiness tests, 16 passed.
- `py_compile` and IDE lint for the experimental builder/tests: passed with no reported problems.
- Experiment copy `PRAGMA integrity_check`: `ok`; source raw table counts match the six primary tables before/after the run. Two experiment runs had the same counts/summary and left 16,346 eligibility and 16,293 feature rows.
- `dataset_quality.py`: completed and correctly reports RESEARCH DATA GATE NOT MET at 9/120.
- `ml_dataset_validation.py`: passed; 17 candidate features, zero invalid labels, no future/outcome feature columns, and no model trained.
- `qa_final_test.py`: with `PYTHONUTF8=1`, 8 smoke/import checks passed. It is not a production-readiness test.
- `test_market_snapshot_inspection.py`: initial baseline 3/5; after correcting the two faulty test assertions, standalone run passed 5/5.
- IDE inspection reported existing typing/format/shadow warnings in `dataset_quality.py` and one unused-local warning in `ml_dataset_validation.py`; no syntax/build error was reported. These unrelated pre-existing warnings were not broadened into a refactor.

## Recovery / migration

These changes are Python-only and do not require database migration or regeneration. Variable-chain feature experiments must use a verified copy of the SQLite database, including a consistent WAL-aware backup, and must preserve the original raw database for rollback.
