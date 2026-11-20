# ML readiness report

**Audit date:** 2026-10-20  
**Decision:** Exploratory data-quality analysis is permissible; final model training is **not ready**.

## Measured sufficiency and representativeness

- 46 distinct IST dates contain raw option data; only 9 dates contain the existing 3,013 market-feature rows. This is below the explicitly retained minimum of 120 trading sessions.
- The isolated `paired_atm_v1` copy experiment covers 46 option-bearing sessions, but its features are not in the original database or the ML dataset. It does not meet the 120-session gate or establish representative labels.
- Existing feature rows by session range from 197 to 375. The feature set is concentrated in Aug 13–Sep 1, while raw collection continues through Oct 19.
- Valid labels range from 2,451 at 60m to 2,954 at 5m. After label-validity filtering, these are the maximum current row counts; chronological purging/splitting would reduce them further.
- Label balance is strongly horizon-dependent: 5m is 80.1% FLAT; 15m 60.0%; 30m 47.5%; 60m 30.3%. These nine feature sessions do not establish regime coverage.
- Full-chain and 21-strike-window feature distributions differ, and several aggregate feature pairs have high correlation. Both effects need reassessment on stable, representative chain coverage.
- No trustworthy per-session market-regime classification, weekday/expiry-stratified sufficiency estimate, or future usable-sample forecast was established. A session count is necessary, not sufficient, for representativeness.

## Readiness-gate correction

Before this audit’s change, `dataset_quality.calculate_readiness()` only warned below five sessions, so the current set of 3,013 samples and valid labels caused `dataset_quality.py` to print `ML DATASET READINESS : READY` at nine sessions. This conflicted with the project’s 120-session requirement and could mislead downstream decisions.

The report now counts unique parseable `market_features` timestamps in 09:15–15:30 Asia/Kolkata and blocks the research-data gate below `MIN_TRADING_SESSIONS = 120`. The measured current result is **9/120; gate not met**. Connections for this report now use SQLite read-only/query-only mode. Unit tests cover 119 sessions (blocked) and 120 sessions (passes this one configured gate with all other synthetic thresholds met). The report explicitly states that passing this necessary research-data threshold does not establish ML-training or production readiness.

The temporary dataset validator also previously selected the market-feature table’s surrogate `id`. It now excludes `id` alongside source IDs and timestamps. It passes structurally with 17 candidate features, but it still does not perform a train/test split or authorize training.

## ML plan and acceptance prerequisites

Before final training, document and freeze:

- Intended task: NIFTY underlying spot direction, with one explicitly selected horizon and the existing or separately versioned flat threshold.
- Eligible snapshot/feature definitions and chain-coverage policy, including field missingness, quote freshness, and processing/feature version.
- At least 120 valid, distinct feature-covered trading sessions; additional assessment of regimes, class balance, feature drift, and coverage by date/expiry.
- Chronological walk-forward validation with session-aware boundaries, horizon-overlap purging/embargo, and final test isolation.
- Training-only preprocessing, imputation/scaling, feature selection, class weighting, and threshold tuning.
- Majority/prior and simple non-ML baselines; macro-F1/balanced accuracy or other task-appropriate class metrics, confusion matrices, and calibration/uncertainty.
- Separate strategy-level walk-forward assessment incorporating fees, slippage, liquidity, fill assumptions, and risk controls. Prediction accuracy is not profitability.
- Model/data/feature versioning, paper-trading acceptance criteria, monitoring/drift alarms, rollback, and no-live-order safeguards.

No model was trained, no training data were fabricated, and no automated trading was enabled.
