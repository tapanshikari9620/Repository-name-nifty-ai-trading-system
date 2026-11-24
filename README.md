# Upstox NIFTY Options Project

This repository contains package modules under src/upstox_project for collecting NIFTY options
market data, storing snapshots in SQLite, calculating historical and live
features, generating historical outcomes, and validating data quality. The
scripts remain in their current locations and continue to use their existing
imports and invocation patterns.

This project does not include an implemented machine-learning training pipeline
or paper-trading system. `upstox_project.main` is a starter stub, not an application
orchestrator.

## Capabilities and layout

- **Collection and API:** `upstox_project.collector.option_snapshot_collector`, `upstox_project.collector.upstox_api`,
  `upstox_project.collector.market_snapshot`, `upstox_project.collector.option_snapshot`, `upstox_project.collector.collection_health`, and
  snapshot validation modules.
- **Historical features and outcomes:** `upstox_project.features.historical_feature_builder`,
  `upstox_project.database.historical_feature_store`, `upstox_project.features.historical_feature_validation`, and
  `upstox_project.outcomes.historical_outcome_builder`.
- **Live analysis and signals:** `upstox_project.features.feature_engine`, `upstox_project.features.feature_validator`,
  `upstox_project.analysis.market_analyzer`, `upstox_project.analysis.evidence_engine`, `upstox_project.signals.signal_engine`,
  `upstox_project.signals.signal_logger`, `upstox_project.outcomes.outcome_engine`, and the `*_live.py` scripts.
- **Quality, validation, and reports:** `upstox_project.validation.dataset_quality`,
  `upstox_project.validation.ml_dataset_validation`, `upstox_project.validation.leakage_test`,
  `upstox_project.validation.pipeline_freshness_coverage_test`, database/snapshot inspection scripts,
  and `upstox_project.validation.daily_data_quality_report`.
- **Tests and experiments:** `test_*.py`, `*_test.py`, `upstox_project.validation.qa_final_test`,
  `upstox_project.validation.verify_fixes`, and `upstox_project.experiments.experimental_variable_chain_builder`. Review a
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
The optional `upstox_project.tools.websocket_test` module imports the Upstox SDK, which is not in
the base requirements. To install the package with that optional dependency:

```powershell
python -m pip install ".[websocket]"
```

Installing the project does not start the collector, open a database, make API
requests, or import application modules.

## Environment configuration

`upstox_project.collector.config` calls `load_dotenv()` and requires `UPSTOX_ACCESS_TOKEN` when
imported. Put the token in a local root `.env` file and never commit or share
that file. The `.env` file is Git-ignored. Run existing commands from the
project root to preserve current working-directory and `.env` discovery
assumptions.

The historical feature and outcome builders read `NIFTY_MARKET_DATABASE`.
`upstox_project.features.historical_feature_builder` also reads `NIFTY_FEATURE_BATCH_SIZE` (default
`100`). Some validation/reporting scripts also honor
`NIFTY_MARKET_DATABASE`; database environment-variable support is not
centralized, so do not assume every script honors it.

## Package module commands

Run commands from the project root with the project's environment activated.
These commands use package-module invocation paths.

### Collection and live analysis

```powershell
python -m upstox_project.collector.option_snapshot_collector
python -m upstox_project.analysis.market_analysis_live
python -m upstox_project.signals.signal_analysis_live
python -m upstox_project.signals.signal_logging_live
```

These are operational commands, not harmless smoke tests. The collector can
make live Upstox API requests and write raw records to SQLite. Live analysis
scripts may also make API requests; signal logging writes to its signal-history
database. Run them only when those side effects are intended. `upstox_project.tools.websocket_test`
connects at module scope when executed and requires the optional SDK; do not
import it as a test.

### Historical feature and outcome workflow

Historical builders write to SQLite. Use a verified, isolated database copy,
not the production database. In PowerShell, set the staging database before
starting each process:

```powershell
$env:NIFTY_MARKET_DATABASE = "C:\path\to\staging\nifty_market_data_staging.db"
$env:NIFTY_FEATURE_BATCH_SIZE = "100"
python -m upstox_project.features.historical_feature_builder
python -m upstox_project.features.historical_feature_validation
python -m upstox_project.outcomes.historical_outcome_builder
```

The builders retain their existing database-path protections. Confirm the
resolved target is the intended staging copy before running a writer. Do not
assume that setting `NIFTY_MARKET_DATABASE` changes the database target of the
collector, raw snapshot stores, or every other script.

### Validation and reporting

With `NIFTY_MARKET_DATABASE` set to the intended database where supported:

```powershell
python -m upstox_project.validation.dataset_quality
python -m upstox_project.validation.leakage_test
python -m upstox_project.validation.ml_dataset_validation
python -m upstox_project.validation.pipeline_freshness_coverage_test
python -m upstox_project.validation.daily_data_quality_report
python -m upstox_project.validation.application_health_check
```

These scripts report different aspects of the dataset and application; inspect
their configured database paths before use. `upstox_project.database.database_schema_inspection`
and snapshot inspection scripts are also available. A report that passes its
own checks does not by itself establish model-training or trading readiness.

## Tests

The following `unittest` modules use temporary databases for their database
tests and do not require live API calls:

```powershell
python -m unittest discover -s src\upstox_project\tests -t src -v
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
