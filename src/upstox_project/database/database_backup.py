
from ..database.paths import PROJECT_ROOT, MARKET_DATABASE_PATH, DATABASE_BACKUP_DIR
import sqlite3
from datetime import datetime
from pathlib import Path


BASE_DIR = PROJECT_ROOT
DATABASE_NAME = MARKET_DATABASE_PATH
BACKUP_DIR = DATABASE_BACKUP_DIR


def check_database_integrity(database_path):
    connection = sqlite3.connect(str(database_path))
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        return result is not None and result[0] == "ok"
    finally:
        connection.close()


def create_database_backup():
    if not DATABASE_NAME.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_NAME}"
        )

    if DATABASE_NAME.stat().st_size == 0:
        raise RuntimeError("Database file exists but is empty.")

    print("Checking source database integrity...")

    if not check_database_integrity(DATABASE_NAME):
        raise RuntimeError("Source database integrity check FAILED.")

    print("Source integrity : PASS")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = (
        BACKUP_DIR
        / f"nifty_market_data_{timestamp}.db"
    )

    source = sqlite3.connect(str(DATABASE_NAME))
    destination = sqlite3.connect(str(backup_path))

    try:
        with destination:
            source.backup(destination)
    finally:
        destination.close()
        source.close()

    if not backup_path.exists():
        raise RuntimeError("Backup file was not created.")

    backup_size = backup_path.stat().st_size

    if backup_size == 0:
        raise RuntimeError("Backup file was created but is empty.")

    print("Checking backup integrity...")

    if not check_database_integrity(backup_path):
        try:
            backup_path.unlink()
        except OSError:
            pass
        raise RuntimeError("Backup integrity check FAILED.")

    print("Backup integrity : PASS")

    source_size = DATABASE_NAME.stat().st_size

    print(
        f"Source size      : {source_size / (1024 * 1024):.2f} MB"
    )
    print(
        f"Backup size      : {backup_size / (1024 * 1024):.2f} MB"
    )
    print(f"Backup file      : {backup_path}")

    return backup_path


def get_backup_summary():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    backups = sorted(
        BACKUP_DIR.glob("nifty_market_data_*.db")
    )

    return {
        "count": len(backups),
        "latest": backups[-1] if backups else None,
    }


if __name__ == "__main__":

    print()
    print("=" * 70)
    print("NIFTY DATABASE BACKUP")
    print("=" * 70)
    print()
    print(f"Source database : {DATABASE_NAME}")
    print(f"Backup folder   : {BACKUP_DIR}")
    print()

    try:
        backup_path = create_database_backup()
        summary = get_backup_summary()

        print()
        print("=" * 70)
        print("BACKUP STATUS : SUCCESS")
        print("=" * 70)
        print()
        print(f"Backup created  : {backup_path.name}")
        print(f"Total backups   : {summary['count']}")
        print()
        print("Database backup completed and verified successfully.")
        print()
        print("=" * 70)

    except Exception as error:

        print()
        print("=" * 70)
        print("BACKUP STATUS : FAILED")
        print("=" * 70)
        print()
        print(f"Error type    : {type(error).__name__}")
        print(f"Error message : {error}")
        print()
        print("=" * 70)

        raise SystemExit(1)