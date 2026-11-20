# Remaining risks and actions

**Audit date:** 2026-10-20

## Prioritized findings

| Severity | Evidence and impact | Status | Recommended next action |
|---|---|---|---|
| **High** | Original DB still has features for only 3,013/16,346 snapshots (9 sessions). The fixed-210 builder excludes 13,280 option-bearing snapshots, creating severe date/coverage bias. | Root cause confirmed. Separately versioned `paired_atm_v1` accepted all 13,280 candidates on an isolated copy; original rows and features were not changed. | Review the eligibility and feature definitions in `FEATURE_ENGINEERING_AUDIT.md`. Do not rebuild the original until source semantics, label representativeness, chronological validation and a migration/recovery plan are approved. |
| **High** | Original dataset has only 9 feature-covered sessions, versus the required 120. Earlier `dataset_quality.py` falsely reported READY. Experimental copy coverage spans 46 sessions but is not the original training dataset and remains below 120. | Gate fixed and tested; dataset still not ready. | Continue collection under the existing schedule, monitor valid feature coverage, and reassess regime/label/feature representativeness at and beyond 120 sessions. |
| **High** | There is no chronological splitter, purge/embargo, training pipeline, or final-test isolation. Labels span up to 60 minutes and adjacent targets overlap. | Unresolved; no final model trained. | Implement and test walk-forward evaluation with horizon-aware purging, session grouping, and training-only preprocessing before model training. |
| **Medium** | Across option rows, 984,697 IVs and 415,426 LTPs are zero; 189,725 IVs exceed 150 and 28,018 theta values exceed the experiment's diagnostic magnitude threshold. These optional fields were not eligibility gates. No exchange quote timestamp or source-validity metadata exists; freshness is unknown. | Unresolved; units/semantics not verified. | Confirm Upstox units/sentinels from authoritative documentation and samples; persist quote age if available and flag stale/invalid values without replacing them with zero. Keep raw data immutable. |
| **Medium** | `safe_number()` behavior can collapse missing/invalid values to zero. Stored feature validators share similar conversion behavior, so current “no null” and pass results do not establish correct missingness semantics. | Unresolved. | Add explicit per-field validity/missingness flags and independently tested strict validation before consuming affected fields. Do not change old feature meaning in place. |
| **Medium** | Historical support/resistance differs from live definitions in 926 support and 29 resistance rows out of 3,013. Chain-universe changes alter full-chain totals/PCR. | Existing definitions remain unchanged; the experiment records separate full-chain and ATM11, unrestricted and spot-filtered versions. | Decide which definition belongs in future signals/training; preserve versioned features and compare only on an isolated copy before regeneration. |
| **Medium** | Derived feature/outcome tables have no FK declarations; feature and option-feature writes are separate, and builders use replacement writes. Current orphan checks are zero, but partial-write recovery and provenance are weak. | No current orphan/duplicate evidence; architectural risk remains. | Add transaction/idempotency and provenance tests; plan an explicit schema migration only after backup/recovery design. |
| **Medium** | 16 intraday intervals exceed 90 seconds (15 exceed 120; maximum 49.4 minutes); 12 of 46 option-bearing sessions have under 360 rows. Exchange quote age is not recorded. | Observed, not filled; the variable-chain experiment does not remove these continuity risks. | Keep gaps explicit, monitor collector health, and exclude target windows crossing gaps under a documented rule. Verify external scheduler operation separately. |
| **Low** | 8 absolute feature correlations >=0.95 among 3,013 rows, but the sample is only nine sessions and some pairs are mechanically related. | Descriptive only. | Reassess redundancy after stable feature definitions and representative coverage; do not prune from this sample alone. |
| **Low** | The standalone `test_market_snapshot_inspection.py` initially reported 3/5 due to two incorrect test assertions (`sqlite3.Row` membership and movement bridging over invalid observations). | Corrected the assertions only; production behavior is unchanged. The test now passes 5/5. | No further action for these test failures; retain adjacent-only movement semantics so invalid observations do not create artificial long-interval movements. |

## Collector and operations

The collector uses GET requests with a 10-second timeout and checks HTTP status/JSON errors, but no explicit retry/backoff is present. It resolves nearest expiry from returned contracts, collects one chain response, applies structural checks, stores one common collection timestamp, checks the expected two side records per strike, validates stored data, and writes health information. Failures are handled by logging and a 10-second loop retry; an incompletely stored new market snapshot may be deleted by collector rollback. Do not run the collector during this audit.

The source schema has no exchange quote timestamp, so “fresh” means only recently collected, not necessarily a fresh exchange quote. The `run_database_backup.bat` path uses `venv`, while this audit used `.venv`; the backup procedure and restore have not been tested. Task Scheduler configuration and process status were not verified.

`signal_logger.py` records heuristic signal observations in a separate DB. No order-placement implementation was found in the project sources searched. Position/exposure limits, daily loss stops, order idempotency, emergency stops, and live execution safeguards therefore remain unverified/not implemented in the discovered code. No live order was placed.

## Unresolved questions before any rebuild or model

1. What are the exact units and sentinel meanings for Upstox IV, theta, volume, OI, `prev_oi`, and zero LTP?
2. Does the source provide exchange quote timestamps/ages elsewhere, and can those be persisted without losing raw provenance?
3. Is `paired_atm_v1`'s five paired strikes per side within 250 points and 11-strike window appropriate for intended features and market conditions?
4. Should support/resistance be full-chain maxima or side-filtered near-spot levels? Which version is used by signals?
5. What horizon/target is the intended ML task, and what are the approved chronological walk-forward/purge/embargo rules?
6. What external job starts/stops the collector and backup process, and has a WAL-consistent restore been exercised?

## Safe next commands

From the repository root, the following checks are read-only:

```powershell
& .\.venv\Scripts\python.exe -m unittest -v test_ml_readiness
& .\.venv\Scripts\python.exe -m unittest -v test_experimental_variable_chain_builder
& .\.venv\Scripts\python.exe .\dataset_quality.py
& .\.venv\Scripts\python.exe .\historical_feature_validation.py
& .\.venv\Scripts\python.exe .\leakage_test.py
& .\.venv\Scripts\python.exe .\ml_dataset_validation.py
```

Do not run `historical_feature_builder.py` or `historical_outcome_builder.py` against the original DB as an experiment. Do not start a second collector if the existing process/schedule is active. The completed `paired_atm_v1` run is copy-only and is not a historical-rebuild approval. Before any historical rebuild, establish a verified backup and recovery plan, review this experiment, and obtain approval. Do not train a final model until data gates and leakage-safe evaluation are independently approved.
