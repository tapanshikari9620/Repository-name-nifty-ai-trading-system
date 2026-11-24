"""Canonical paths for the NIFTY Upstox project databases.

All package modules should import these constants instead of deriving paths
from their own module directory or relying on the process working directory.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

def _resolve_database_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()

_market_database = os.environ.get("NIFTY_MARKET_DATABASE")
MARKET_DATABASE_PATH = _resolve_database_path(
    _market_database if _market_database else PROJECT_ROOT / "nifty_market_data.db"
)
SIGNAL_DATABASE_PATH = (PROJECT_ROOT / "nifty_signal_history.db").resolve()
DATABASE_BACKUP_DIR = (PROJECT_ROOT / "backups").resolve()
