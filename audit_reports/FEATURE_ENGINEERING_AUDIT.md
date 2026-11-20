# Feature engineering audit

**Audit date:** 2026-10-20  
**Relevant modules:** `feature_engine.py`, `historical_feature_builder.py`, `market_analyzer.py`, `historical_feature_validation.py`, `feature_compatibility_audit.py`

## Definitions observed in the historical feature builder

Historical market features are computed from all option rows in one accepted snapshot. OI and volume units are inherited from the API and are not documented in the repository. “Previous OI” is read from Upstox’s `prev_oi` field; the code computes `oi_change = oi - prev_oi`. It does **not** compute change from the preceding stored market snapshot. The source’s exact reference time/semantics for `prev_oi` remain unverified.

| Feature | Current calculation | Inputs / scope | Caveat |
|---|---|---|---|
| `spot_price` | Underlying value stored with snapshot | Source option-chain underlying field | Snapshot value is positive in the audited DB; no independent exchange timestamp is stored. |
| `atm_strike` | Strike minimizing absolute distance to spot | Unique strikes from all option rows | Ties resolve by sorted/input order; no explicit tie policy/version. |
| `total_ce_oi`, `total_pe_oi` | Sum OI by CE/PE | Entire accepted chain | Changes with the available strike universe. |
| `pcr` | Total PE OI / total CE OI; zero when CE OI is not positive | Entire accepted chain | Zero conflates a genuine zero denominator with an invalid ratio. |
| `total_ce_oi_change`, `total_pe_oi_change` | Sum `oi_change` by side | Entire chain, using `oi - prev_oi` | Not an observation-to-observation OI change. |
| `oi_pressure` | PE OI-change total minus CE OI-change total | Entire chain | Deterministic composite of the preceding two fields. |
| `total_ce_volume`, `total_pe_volume` | Sum volume by side | Entire chain | Universe- and source-unit-sensitive. |
| `volume_pressure` | PE volume total minus CE volume total | Entire chain | Deterministic composite of side totals. |
| `support` | Strike of the highest-OI PE row | Entire chain, no ATM/spot restriction | Differs from the live analyzer’s spot-filtered candidate set. |
| `resistance` | Strike of the highest-OI CE row | Entire chain, no ATM/spot restriction | Differs from the live analyzer’s spot-filtered candidate set. |
| `highest_ce_oi`, `highest_pe_oi` | Maximum individual CE/PE OI | Entire chain | No associated strike is stored in the aggregate market feature. |
| `highest_ce_oi_change`, `highest_pe_oi_change` | Maximum individual change value on each side | Entire chain | Selects maximum signed change, not maximum absolute change. |

`option_features` stores per-contract LTP, close, volume, OI/previous OI/change, bid/ask, IV, Greeks and POP. These fields are not currently selected by `ml_dataset_validation.py`’s market-feature dataset. `feature_engine.py` consumes Upstox strike-level records (each may contain both call and put sides); `find_atm()` returns the nearest strike record and `select_atm_strikes()` returns ATM plus N records on either side. Historical selection uses a unique strike set. Both use strike records, not flattened CE/PE side rows.

The live `calculate_option_features()` maps CE/PE LTP, OI, previous OI, volume, IV, delta, gamma, theta and vega per strike, and computes each side’s OI change as OI minus `prev_oi`. Missing/non-numeric fields become zero through the live helper. `select_atm_strikes()` sorts by absolute strike distance and takes `2N+1` records; when strikes are missing, that does not guarantee N strikes on each side, and it does not independently require paired CE/PE sides. The caller must validate the selected window before using it.

## Numeric and feature-universe risks

Both live and historical number helpers can turn missing/invalid values into zero (historical handling also maps non-finite values to zero). This loses the distinction between absent data and a mathematically valid zero; historical feature validation shares the same conversion style and is not an independent check of this behavior. No SQL NULLs were found in scanned option/market-feature numeric columns, but the raw zero populations and Greek extremes in `DATABASE_DATA_QUALITY_REPORT.md` remain unresolved.

Full-chain aggregates are not directly comparable when the chain universe changes. The compatibility audit found median full-chain PCR 0.7348 for existing feature snapshots versus 0.8602 for missing variable-chain snapshots; 21-strike-window medians were 0.8044 and 0.9333. The ATM window retained different shares of full-chain OI: CE 61.22% versus 55.32%, PE 68.72% versus 60.55%. These groups also differ by date/market regime, so this is evidence of universe sensitivity, not a causal estimate of chain-size effect.

Within the 3,013 legacy feature rows, exploratory absolute Pearson correlations >=0.95 included: spot/ATM strike (0.99336), CE/PE total volume (0.99210), PE OI/PE highest OI (0.96303), total PE OI/PE OI change (0.95466), total CE OI change/highest CE OI change (0.97049), and several peak-OI/peak-change pairs (0.95406–0.99031). Do not remove features solely from this small, nine-session sample; review redundancy after a representative dataset exists.

Stored historical support/resistance differs from the live `market_analyzer.py` definition: it chooses unrestricted full-chain maxima, while the live analyzer filters PE support to strikes at/below spot and CE resistance to strikes at/above spot. Independent comparison differed for support in 926/3,013 rows and resistance in 29/3,013. These definitions must be reconciled or versioned; do not overwrite historical features silently.

## Variable-chain root cause and isolated experiment

`historical_feature_builder.py` hard-codes 210 total records, 105 CE and 105 PE. The completeness check also requires one expiry, valid timestamp, no duplicate contract key and paired strike sets. The 13,280 missing option-bearing snapshots pass the structural checks and collection-health gate; the builder does not accept them solely because their actual record count is not 210. Its integrity checker separately expects 210 option-feature rows per feature snapshot.

This establishes exact-210 as the root cause of the large unprocessed population. An isolated experiment implemented `paired_atm_v1` in `experimental_variable_chain_builder.py`; it does not alter the legacy builder or original DB. The experiment uses `audit_reports\experimental\paired_atm_v1.db`, a verified SQLite backup copy. Its policy requires:

1. Timezone-aware market and option timestamps that identify the same instant; finite positive spot; one valid, non-expired (relative to IST snapshot date) expiry.
2. CE/PE-only option types, finite positive strikes, exactly paired strike sets, no duplicate `(expiry, strike, side)` contracts, and nonempty unique instrument keys.
3. At least five paired strike levels strictly below and five strictly above spot within 250 points, plus the nearest paired strike and five paired levels on each side (11 strikes / 22 option rows). An equal-distance ATM tie resolves to the lower strike.
4. Finite OI, previous OI, OI change and volume; OI, previous OI and volume must be nonnegative; `oi_change` must agree with `oi - prev_oi` within `1e-6` absolute and `1e-9` relative tolerance. Zero values remain valid values.
5. If collection health exists, it must be `SUCCESS/PASS` and any available record counts must agree. Missing health is a warning, not evidence of failure. LTP, IV and Greeks are optional diagnostics, not eligibility gates.

The experiment wrote only two additive versioned tables in the copy: per-snapshot eligibility/reasons/diagnostics and JSON features. It did not copy experimental features into the original. All 13,280 previously missing option-bearing snapshots passed; all 3,013 legacy snapshots passed; 53 market snapshots with no option rows were rejected (`NO_OPTION_RECORDS`, also `EXPIRY_NOT_UNIQUE`). There were no other rejection reasons among option-bearing rows. Of the 74 missing-health warnings across the full market-snapshot table, 53 were optionless snapshots and 21 were older already-featured snapshots; none of the 13,280 candidates lacked health. Quote freshness remains `UNKNOWN`: the stored option timestamp is the collection timestamp, not an exchange quote timestamp.

### Versioned feature views

The experiment retains two disjoint scopes: `full_*` uses all eligible paired CE/PE strike rows; `atm11_*` uses the 11 paired strike levels centered by the rule above. Neither overwrites the existing historical feature columns.

| Feature fields (each scope) | Formula / units | Required inputs and missing behavior | Comparability when chain coverage changes |
|---|---|---|---|
| `total_ce_oi`, `total_pe_oi` | Sum OI for the named side; source OI units. | Finite nonnegative OI; rejected if missing/invalid; never imputed. | Full-chain totals depend strongly on chain extent; ATM11 totals use a fixed row count but still depend on strike spacing and contract data. |
| `pcr` | PE OI total / CE OI total; dimensionless. | Same OI inputs. Null if CE total is zero (legacy builder instead stores 0.0). | Universe-sensitive for `full`; more comparable in `atm11`, but not invariant. |
| `total_ce_oi_change`, `total_pe_oi_change` | Sum stored `oi_change` by side; source OI units. | Finite OI, `prev_oi`, `oi_change`; change may be negative but must equal OI minus previous OI within policy tolerance. | Scope-sensitive; `full` totals vary with chain extent. |
| `oi_pressure` | PE OI-change total minus CE OI-change total; source OI units. | Same as side OI-change totals. | Scope-sensitive; deterministic composite, not independent evidence. |
| `total_ce_volume`, `total_pe_volume` | Sum volume by side; source volume units. | Finite, nonnegative volume; missing/invalid rejects. | Full-chain totals depend on chain extent; ATM11 is fixed-count but still source/spacing-sensitive. |
| `volume_pressure` | PE volume total minus CE volume total; source volume units. | Same as side volume totals. | Scope-sensitive; deterministic composite. |
| `highest_ce_oi`, `highest_pe_oi` | Maximum individual OI by side; source OI units. | Finite nonnegative OI. | Full-chain maxima can shift with added strikes; ATM11 maxima are bounded to the fixed window. |
| `highest_ce_oi_change`, `highest_pe_oi_change` | Maximum signed (not absolute) individual `oi_change`; source OI units. | Finite and consistent required OI fields. | Full-chain maxima can shift with chain extent; ATM11 maxima are window-bounded. |
| `historical_support`, `historical_resistance` | Strike of maximum-OI PE / CE respectively, unrestricted within the scope; underlying strike points. | Strike, option side and OI. Equal OI ties resolve to the lower strike. | Full-chain levels can change with coverage; ATM11 levels are constrained to the ATM window. |
| `live_support`, `live_resistance` | Max-OI PE strike at/below spot / CE strike at/above spot; fall back to unrestricted scope maximum if no candidate; underlying strike points. | Above inputs plus positive spot. | Spot-filtered and window-bounded for ATM11; still depends on the measured chain universe and fallback. |
| Metadata: `spot_price`, `atm_strike`, strike/option counts and ATM11 window bounds | Snapshot spot and nearest paired strike; counts and strike-point bounds. | Valid spot, strike, paired structure. ATM ties resolve lower. | Counts expose changing full-chain size. ATM11 strike count is fixed; points covered can still vary. |

Full-chain values are not directly comparable when chain extent changes. ATM11 is a more consistent *scope*, not a guarantee of identical information: it remains sensitive to spacing, expiry, spot-centering, source semantics, collection timing and missing/stale quotes. Source units for OI and volume and the precise semantics of `prev_oi` remain unverified.

Historical support/resistance remains the unrestricted max-OI level. Live `market_analyzer.py` filters support to PE strikes at/below spot and resistance to CE strikes at/above spot, with a fallback to the full set. The experiment records both variants separately in both scopes; it does not silently change either historical or live definitions.

The strict `feature_universe_consistency_test.py` reports that the *same global contract set* is not constant across all 3,013 feature snapshots (1,731 differ from its reference contract set). This is expected for a changing option universe, not a per-snapshot CE/PE pairing defect: `feature_universe_pair_consistency_test.py` passes per-snapshot paired-strike, expiry and duplicate checks for all 3,013. The strict script now propagates its printed FAIL as a nonzero process exit code so automation cannot mistake it for a pass.

### Independent checks and tests

The 16-test combined regression run passed: 12 experiment tests plus four readiness tests. The standalone market-inspection suite also passed 5/5 after correcting its test assertions (no production behavior changed). The experiment tests cover complete and variable chains, asymmetric pairing, duplicate contracts/instruments, multiple expiries, required-field missing/invalid/negative/inconsistent values, failed health, timezone-naive timestamps, invalid spot, insufficient ATM coverage, zero/extreme optional quotes, refusal of the original database path and idempotent writes. Hand-calculated fixture assertions independently verify OI/PCR/change/pressure/volume/maxima/support/resistance/window values for full-chain and ATM11 scopes; expected values are not generated by a second call to the production calculation.

The database copy passed `integrity_check`; its six original application-table counts still match the source. The experiment table counts and summary were unchanged on a second run (16,346 eligibility rows and 16,293 feature rows). Baseline feature coverage was 3,013/16,346 snapshots and 9 IST market sessions; copy-only experimental coverage was 16,293/16,346 and 46 sessions, covering all 16,293 option-bearing snapshots. This is a coverage result, **not** proof of quote validity, feature stability, representative labels, ML readiness or approval for historical rebuild.

Further work should add tests for source quote-age metadata when available, complete end-to-end eligibility-to-feature writes on representative real data, feature stability across strike spacing/expiry regimes, and target-window continuity. Existing aggregate unit tests do not validate source-data semantics or establish that all market regimes are represented.
