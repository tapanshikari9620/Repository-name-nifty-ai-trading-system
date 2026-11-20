# Outcome and leakage audit

**Audit date:** 2026-10-20  
**Relevant modules:** `historical_outcome_builder.py`, `outcome_engine.py`, `leakage_test.py`, `ml_dataset_validation.py`

## Historical outcome definitions

`historical_outcome_builder.py` labels the underlying NIFTY spot, not an option/futures price. For each source snapshot and horizon (5, 15, 30, 60 minutes), it selects the first later market snapshot at or after the target time, provided the observation is no more than 90 seconds late. The return is `(future_spot - source_spot) / source_spot * 100`; return >= +0.05% is `BULLISH`, <= -0.05% is `BEARISH`, otherwise `FLAT`. If no eligible future snapshot exists, the outcome is `UNAVAILABLE` with `valid=0` and null future price/time/return fields. No trading costs, fees, or slippage are included.

The 90-second late tolerance limits but does not eliminate variability in the realized horizon. There is no explicit session/date predicate in the selection function. However, because the first future observation must be within 90 seconds of the target, overnight/market-close observations cannot currently satisfy the window. A full independent reconstruction of all stored valid labels found zero price, timestamp, return/direction mismatches and zero cross-date outcomes.

| Horizon | Valid / 3,013 | Coverage | BULLISH | BEARISH | FLAT | Unavailable |
|---|---:|---:|---:|---:|---:|---:|
| 5m | 2,954 | 98.04% | 265 (9.0%) | 323 (10.9%) | 2,366 (80.1%) | 59 |
| 15m | 2,854 | 94.72% | 489 (17.1%) | 653 (22.9%) | 1,712 (60.0%) | 159 |
| 30m | 2,703 | 89.71% | 623 (23.0%) | 797 (29.5%) | 1,283 (47.5%) | 310 |
| 60m | 2,451 | 81.35% | 768 (31.3%) | 940 (38.4%) | 743 (30.3%) | 562 |

The strong FLAT majority at 5m is a class-imbalance concern. These are research direction labels, not option returns or evidence of profitability. Do not map unavailable labels to FLAT or directional classes.

## Leakage audit

**Observed protections:** Features in `market_features` are derived from the source snapshot; no forward price/label column is part of that table. The temporary dataset builder selects valid horizon direction as `target` and excludes outcome price, return, timestamp, delay, and other outcome fields from X. The `id` surrogate key had been admitted as a candidate feature; it is now explicitly excluded and covered by a regression test. The read-only dataset validator passes with 17 candidate aggregate features, no future/label name matches, aligned source timestamps, zero duplicate feature timestamps, and no invalid labels among valid rows.

**Unverified or absent safeguards:**

- No model training, split, preprocessing, scaling, imputation, feature selection, or threshold-tuning pipeline was found. Consequently, no leakage-safe chronological split has been demonstrated.
- The existing `leakage_test.py` checks a limited set of source timing/date invariants; it does not verify train/validation/test data flow, temporal split ordering, preprocessing fit scope, duplicates across splits, or horizon overlap.
- A random row split would mix highly dependent same-session samples. With 5–60-minute overlapping targets, samples near a split boundary can share future price windows. Any future evaluation needs chronological walk-forward folds plus horizon-aware purging/embargo and session grouping as appropriate.
- No final test-set isolation, model-level normalization or imputation protocol, expiry-specific holdout, or threshold-tuning policy exists in the discovered code.
- No forward-looking rolling feature was identified in the current aggregate historical feature calculation, but a future feature pipeline needs explicit as-of timestamp tests.

## Required validation design before training

1. Freeze and version the target and feature definitions, including the 90-second execution-point tolerance and the ±0.05% flat band.
2. Build an eligible sample manifest keyed by stable snapshot ID and timestamp; exclude unavailable labels per horizon without recoding them.
3. Use chronological walk-forward evaluation. Keep complete sessions in one fold where feasible and purge training examples whose target windows overlap the next fold; embargo at least the maximum target horizon where temporal dependence warrants it.
4. Fit transformations, imputers, scalers, and selectors only on each training fold. Tune thresholds only within training/validation folds, never on the final test period.
5. Report class-aware predictive metrics and calibration separately from trading returns. Compare simple persistence/class-prior baselines and include transaction costs, slippage, and execution assumptions only in a separate strategy evaluation.

No final model was trained. The current outcome table passed the independent formula reconstruction, but it is not a leakage-safe training/evaluation dataset by itself.
