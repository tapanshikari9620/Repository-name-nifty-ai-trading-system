import sqlite3


DATABASE_NAME = "nifty_market_data.db"


def inspect_database():

    connection = sqlite3.connect(
        DATABASE_NAME
    )

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