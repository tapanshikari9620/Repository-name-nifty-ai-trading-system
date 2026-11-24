
from ..database.paths import MARKET_DATABASE_PATH
import sqlite3
import os
from pathlib import Path


DATABASE_NAME = str(MARKET_DATABASE_PATH)


def inspect_database():

    database_path = Path(DATABASE_NAME).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database not found: {database_path}")
    connection = sqlite3.connect(
        database_path.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.execute("PRAGMA query_only = ON")

    cursor = connection.cursor()

    print()
    print("=" * 70)
    print("NIFTY DATABASE SCHEMA INSPECTION")
    print("=" * 70)

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """
    )

    tables = cursor.fetchall()

    for table_row in tables:

        table_name = table_row[0]

        print()
        print(
            f"TABLE: {table_name}"
        )

        print("-" * 70)

        cursor.execute(
            f"PRAGMA table_info({table_name})"
        )

        columns = cursor.fetchall()

        for column in columns:

            column_id = column[0]
            column_name = column[1]
            column_type = column[2]
            not_null = column[3]
            default_value = column[4]
            primary_key = column[5]

            print(
                f"{column_id:2d} | "
                f"{column_name:30s} | "
                f"{column_type:12s} | "
                f"NOT NULL={not_null} | "
                f"PK={primary_key} | "
                f"DEFAULT={default_value}"
            )

        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        )

        count = cursor.fetchone()[0]

        print()
        print(
            f"Rows: {count}"
        )

    connection.close()

    print()
    print("=" * 70)


if __name__ == "__main__":

    inspect_database()