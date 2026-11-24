
from ..database.paths import MARKET_DATABASE_PATH
import os
import sqlite3
from pathlib import Path

DB_PATH = str(MARKET_DATABASE_PATH)

def main():
    database_path = Path(DB_PATH).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database not found: {database_path}")

    conn = sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    print("=" * 70)
    print("OPTION_FEATURES TABLE SCHEMA")
    print("=" * 70)

    columns = conn.execute("""
        PRAGMA table_info(option_features)
    """).fetchall()

    for column in columns:
        print(
            f"Column ID : {column[0]}\n"
            f"Name      : {column[1]}\n"
            f"Type      : {column[2]}\n"
            f"Not Null  : {column[3]}\n"
            f"Default   : {column[4]}\n"
            f"Primary Key: {column[5]}\n"
            + "-" * 50
        )

    print("\nSAMPLE ROW")
    print("=" * 70)

    row = conn.execute("""
        SELECT *
        FROM option_features
        LIMIT 1
    """).fetchone()

    if row:
        for column, value in zip(columns, row):
            print(f"{column[1]} = {value}")
    else:
        print("No rows found.")

    conn.close()


if __name__ == "__main__":
    main()
