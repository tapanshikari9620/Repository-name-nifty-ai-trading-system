# Variable-chain eligibility and feature experiment

**Date:** 2026-10-20  
**Policy version:** `paired_atm_v1`  
**Scope:** Experimental feature generation on a separate SQLite backup copy only. No model training, outcome rebuild, live API, or order execution.

## Decision and data boundary

`historical_feature_builder.py` retains its exact-210-record rule. The new experiment is implemented in `experimental_variable_chain_builder.py`, refuses the original database path, and writes only `experiment_eligibility_paired_atm_v1` and `experiment_features_paired_atm_v1` in `audit_reports\experimental\paired_atm_v1.db`. This path is ignored by Git. Experimental records were not transferred to `nifty_market_data.db`.

The copy was made with SQLite's backup API from a read-only source connection. Its six application-table counts matched the source before the experiment; both source and copy passed `PRAGMA integrity_check`. After two experiment runs, the six raw/legacy application-table counts still matched the source and both copy-only experiment tables had stable row counts. The original was opened read-only for post-run verification and retained its baseline counts and coverage.

## Eligibility policy

One market snapshot is eligible only if every rule below passes. Rejection reasons are persisted as stable reason codes; a missing collection-health record is a warning.

| Rule | `paired_atm_v1` acceptance condition |
|---|---|
| Market time and spot | Market timestamp parses with a timezone offset; spot is finite and greater than zero. |
| Option time | Every option timestamp parses with a timezone offset and identifies the same instant as its market snapshot. This is collection-time coherence only; it does not prove quote freshness. |
| Expiry | Every row has one valid ISO expiry; there is exactly one expiry and it is not before the snapshot date in `Asia/Kolkata`. |
| Contract structure | Only CE/PE; positive finite strikes; exactly equal CE and PE strike sets; no duplicate `(expiry, strike, option_type)` and no missing or duplicate instrument key. |
| Near-spot coverage | At least five paired strike levels strictly below and five strictly above spot, each within 250 underlying points. |
| ATM feature window | Sort paired strikes; select the nearest to spot, breaking an equal-distance tie toward the lower strike, and five paired strike levels on either side. All 11 must exist, yielding 22 contracts. |
| Required numerical fields | OI, previous OI, OI change and volume must be finite. OI, previous OI and volume must be nonnegative. OI change may be negative but must match `OI - prev_OI` within `1e-6` absolute and `1e-9` relative tolerance. Zero is not treated as missing. |
| Collection health | If present, status must be `SUCCESS`, validation status `PASS`, and any available option counts must agree with the actual row count. Missing health does not fail eligibility. |
| Optional quote/Greek fields | LTP, IV, delta, gamma, theta and vega do not gate aggregate-feature eligibility. Missing/zero/extreme values are diagnostics only pending verified source semantics. |

The ±250-point limit and five paired levels per side were selected because the structural audit found all 13,280 option-bearing candidates had at least that measured paired coverage. The additional 11-level rule prevents an otherwise eligible chain from producing a partial ATM-window aggregate. These are experiment thresholds, not approved production or strategy thresholds.

## Formula definitions and comparability

Each aggregate is emitted separately for `full_*` (all paired strikes in the eligible snapshot) and `atm11_*` (the 11 selected paired strike levels). No existing `market_features` value is updated.

| Feature | Formula; units | Required fields and missing behavior | Coverage comparability |
|---|---|---|---|
| `total_ce_oi`, `total_pe_oi` | Sum side OI; source OI units. | Finite nonnegative OI; missing/invalid row rejects; no imputation. | Full-chain depends on chain extent. ATM11 is fixed-count but depends on strike spacing and contract data. |
| `pcr` | PE OI total / CE OI total; dimensionless. | OI totals; `null` if CE total is zero. Legacy builder returns `0.0` in that case. | Full-chain depends on scope; ATM11 is more consistent, not invariant. |
| `total_ce_oi_change`, `total_pe_oi_change` | Sum stored OI change by side; source OI units. | Finite OI, previous OI, change; change must equal OI minus previous OI. | Scope-sensitive; full-chain totals change with chain extent. |
| `oi_pressure` | PE OI-change total minus CE OI-change total; source OI units. | Side change totals. | Scope-sensitive derived feature. |
| `total_ce_volume`, `total_pe_volume` | Sum side volume; source volume units. | Finite nonnegative volume; missing/invalid rejects. | Full-chain depends on extent; ATM11 fixed-count but spacing/source sensitive. |
| `volume_pressure` | PE volume total minus CE volume total; source volume units. | Side volume totals. | Scope-sensitive derived feature. |
| `highest_ce_oi`, `highest_pe_oi` | Maximum individual OI on the side; source OI units. | Finite nonnegative OI. | Full maxima may change as outer strikes appear; ATM11 maxima are window-bounded. |
| `highest_ce_oi_change`, `highest_pe_oi_change` | Maximum signed (not absolute) individual OI change; source OI units. | Valid OI, previous OI and change. | Full maxima may change with extent; ATM11 maxima are window-bounded. |
| `historical_support`, `historical_resistance` | Strike of maximum-OI PE, CE respectively, without spot restriction; strike points. | Side, strike and OI. Equal OI ties choose lower strike. | Full levels can move with chain extent; ATM11 levels are window-bounded. |
| `live_support`, `live_resistance` | Max-OI PE strike at/below spot and CE strike at/above spot; if no candidate, fall back to unrestricted scope maximum; strike points. | Above fields plus positive spot. | Spot-filtered, but still chain- and fallback-dependent. |
| Metadata | Snapshot spot, nearest paired ATM strike, full/ATM11 counts and ATM11 low/high strike bounds. | Valid spot, strike and paired structure. | Counts expose universe change; ATM11 count is fixed while strike spacing can vary. |

The historical builder's `support` and `resistance` are unrestricted full-chain maxima. Live `market_analyzer.py` filters support to PE strikes at/below spot and resistance to CE strikes at/above spot, falling back to all strikes if the filtered set is empty. The experiment preserves both definitions under separate names and does not alter either existing implementation.

## Measured results

Read-only pre- and post-experiment baseline:

| Measure | Original baseline | Experimental copy |
|---|---:|---:|
| `market_snapshots` | 16,346 | 16,346 |
| `option_snapshots` | 3,467,828 | 3,467,828 |
| Option-bearing snapshots | 16,293 | 16,293 |
| Legacy `market_features` snapshots | 3,013 | 3,013 (unchanged) |
| Feature coverage across market snapshots | 3,013 / 16,346 (18.43%) | 16,293 / 16,346 (99.68%) in the experiment table |
| Feature-covered IST sessions | 9 | 46 |
| Versioned experiment feature rows | — | 16,293 |
| Versioned experiment eligibility rows | — | 16,346 |

Eligibility outcome for the 13,280 previously missing option-bearing snapshots:

| Check | Candidates tested | Accepted | Rejected |
|---|---:|---:|---:|
| Timezone-aware market timestamp and positive finite spot | 13,280 | 13,280 | 0 |
| Coherent option timestamps | 13,280 | 13,280 | 0 |
| One valid, non-expired expiry | 13,280 | 13,280 | 0 |
| Paired CE/PE strikes; no duplicate contract/instrument | 13,280 | 13,280 | 0 |
| Five paired levels on each side within ±250 points | 13,280 | 13,280 | 0 |
| Complete ATM11 paired window | 13,280 | 13,280 | 0 |
| Required finite/nonnegative numeric fields and OI-change consistency | 13,280 | 13,280 | 0 |
| Present collection-health records | 13,280 | 13,280 | 0 missing; all available records passed |
| **Overall** | **13,280** | **13,280** | **0** |

Across all 16,346 market snapshots, 3,013 legacy exact-210 snapshots and 13,280 variable-chain snapshots were eligible. The other 53 snapshots had no option records and were rejected with both `NO_OPTION_RECORDS` and `EXPIRY_NOT_UNIQUE`; reason counts overlap and are not additive. The experiment recorded 74 missing-health warnings over the full table (53 optionless snapshots and 21 pre-existing feature snapshots). There were no missing-health warnings among the 13,280 new candidates.

Across 3,467,828 raw option rows, diagnostics counted 415,426 zero LTP, 984,697 zero IV, 189,725 IV above 150 and 28,018 theta magnitudes above 1,000. These were **not** rejection rules and are not asserted to be erroneous. Quote timestamp availability was false and quote freshness was `UNKNOWN`.

## Validation and interpretation

- `python -m unittest -v test_experimental_variable_chain_builder test_ml_readiness`: **16/16 passed** (12 experiment tests, four readiness tests).
- Hand-calculated fixture expectations independently cover both scopes' side totals, PCR, OI changes and pressure, volumes and pressure, maxima, historical/live support and resistance, and window bounds.
- Tests cover full/variable, asymmetric, duplicate, multiple-expiry, invalid/missing/negative/inconsistent numeric data, insufficient ATM coverage, failed/missing health, optional zero/extreme quote values, timezone-naive timestamp, invalid spot, original-path refusal and repeated deterministic writes.
- PyCharm lint and `py_compile` reported no issues. The database-copy raw counts matched the original; copy integrity passed after two identical experiment runs.
- Original database remains at 3,013 feature snapshots and nine feature-covered IST sessions. No historical feature or outcome builder was run; no model was trained.

**Unresolved before rebuild:** authoritative units and sentinel semantics for OI/volume/IV/Greeks/LTP; exact `prev_oi` reference period; exchange quote timestamps/age; whether the ATM/near-spot thresholds generalize across regimes; feature/label representativeness and chronological purge/embargo design. The result justifies reviewing a future, separately approved rebuild plan; it does not justify rebuilding the original database, copying features into it, or declaring ML readiness.
