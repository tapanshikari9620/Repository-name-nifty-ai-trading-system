# Upstox NIFTY Options Project

This repository contains root-level Python scripts for collecting NIFTY options
market data, storing snapshots in SQLite, calculating historical and live
features, generating historical outcomes, and validating data quality. The
scripts remain in their current locations and continue to use their existing
imports and invocation patterns.

This project does not include an implemented machine-learning training pipeline
or paper-trading system. `main.py` is a starter stub, not an application
orchestrator.

## Capabilities and layout

- **Collection and API:** `option_snapshot_collector.py`, `upstox_api.py`,
  `market_snapshot.py`, `option_snapshot.py`, `collection_health.py`, and
  snapshot validation modules.
- **Historical features and outcomes:** `historical_feature_builder.py`,
  `historical_feature_store.py`, `historical_feature_validation.py`, and
  `historical_outcome_builder.py`.
- **Live analysis and signals:** `feature_engine.py`, `feature_validator.py`,
  `market_analyzer.py`, `evidence_engine.py`, `signal_engine.py`,
  `signal_logger.py`, `outcome_engine.py`, and the `*_live.py` scripts.
- **Quality, validation, and reports:** `dataset_quality.py`,
  `ml_dataset_validation.py`, `leakage_test.py`,
  `pipeline_freshness_coverage_test.py`, database/snapshot inspection scripts,
  and `daily_data_quality_report.py`.
- **Tests and experiments:** `test_*.py`, `*_test.py`, `qa_final_test.py`,
  `verify_fixes.py`, and `experimental_variable_chain_builder.py`. Review a
  script's side effects before running it; filenames alone do not guarantee
  that it is read-only.

SQLite databases, backups, logs, local credentials, audit reports, and IDE or
virtual-environment files are local project data, not package contents.

## Python environment

Python 3.10 or later is required. From the project root, create and activate a
virtual environment in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The existing requirements file lists `requests`, `python-dotenv`, and `tzdata`.
The optional `websocket_test.py` module imports the Upstox SDK, which is not in
the base requirements. To install the package with that optional dependency:

```powershell
python -m pip install ".[websocket]"
```

Installing the project does not start the collector, open a database, make API
requests, or import application modules.

## Environment configuration

`config.py` calls `load_dotenv()` and requires `UPSTOX_ACCESS_TOKEN` when
imported. Put the token in a local root `.env` file and never commit or share
that file. The `.env` file is Git-ignored. Run existing commands from the
project root to preserve current working-directory and `.env` discovery
assumptions.

The historical feature and outcome builders read `NIFTY_MARKET_DATABASE`.
`historical_feature_builder.py` also reads `NIFTY_FEATURE_BATCH_SIZE` (default
`100`). Some validation/reporting scripts also honor
`NIFTY_MARKET_DATABASE`; database environment-variable support is not
centralized, so do not assume every script honors it.

## Existing script commands

Run commands from the project root with the project's environment activated.
These commands preserve the scripts' current root-level invocation style.

### Collection and live analysis

```powershell
python option_snapshot_collector.py
python market_analysis_live.py
python signal_analysis_live.py
python signal_logging_live.py
```

These are operational commands, not harmless smoke tests. The collector can
make live Upstox API requests and write raw records to SQLite. Live analysis
scripts may also make API requests; signal logging writes to its signal-history
database. Run them only when those side effects are intended. `websocket_test.py`
connects at module scope when executed and requires the optional SDK; do not
import it as a test.

### Historical feature and outcome workflow

Historical builders write to SQLite. Use a verified, isolated database copy,
not the production database. In PowerShell, set the staging database before
starting each process:

```powershell
$env:NIFTY_MARKET_DATABASE = "C:\path\to\staging\nifty_market_data_staging.db"
$env:NIFTY_FEATURE_BATCH_SIZE = "100"
python historical_feature_builder.py
python historical_feature_validation.py
python historical_outcome_builder.py
```

The builders retain their existing database-path protections. Confirm the
resolved target is the intended staging copy before running a writer. Do not
assume that setting `NIFTY_MARKET_DATABASE` changes the database target of the
collector, raw snapshot stores, or every other script.

### Validation and reporting

With `NIFTY_MARKET_DATABASE` set to the intended database where supported:

```powershell
python dataset_quality.py
python leakage_test.py
python ml_dataset_validation.py
python pipeline_freshness_coverage_test.py
python daily_data_quality_report.py
python application_health_check.py
```

These scripts report different aspects of the dataset and application; inspect
their configured database paths before use. `database_schema_inspection.py`
and snapshot inspection scripts are also available. A report that passes its
own checks does not by itself establish model-training or trading readiness.

## Tests

The following `unittest` modules use temporary databases for their database
tests and do not require live API calls:

```powershell
python -m unittest test_ml_readiness test_experimental_variable_chain_builder test_historical_feature_builder_variable_chains
```

Other `*_test.py` and QA scripts may access the configured project database,
make network connections, or have other side effects. Review each script
before running it. No model is trained by the unit-test command above.

## Packaging

Packaging metadata uses setuptools and explicitly lists the existing
root-level Python modules. It does not move scripts, create a new import
namespace, define console entry points, or import application code during
installation. The distribution includes the listed Python modules and project
metadata, not local databases, credentials, backups, logs, virtual
environments, generated reports, or IDE files.

To build a wheel and source distribution, install the build frontend in the
active environment and direct outputs outside the repository:

```powershell
python -m pip install build
python -m build --outdir "$env:TEMP\upstox-project-dist"
```

The build command packages code and metadata only; it does not run the
application or validate database contents.

## Database and operational safety

Many scripts use `nifty_market_data.db` or `nifty_signal_history.db`; some
resolve relative paths from the current working directory, while others use
the script directory. Keep running scripts from the project root unless their
existing documentation or code specifies otherwise. The historical builders
have write-target protections, but packaging does not alter or replace them.

Before any collection or historical build, identify the script's resolved
database path and ensure it is the intended target. Back up important data
before planned write operations. Never run a collector or live-analysis
command unless live API access is intended. This repository does not implement
paper trading, and it does not provide a complete model-training workflow.
