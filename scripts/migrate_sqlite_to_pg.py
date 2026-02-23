#!/usr/bin/env python3
"""
Direct SQLite → PostgreSQL migration script.
Much faster than Django loaddata: uses COPY protocol, commits per table, resumable.

Usage:
    python scripts/migrate_sqlite_to_pg.py --table companies_company
    python scripts/migrate_sqlite_to_pg.py --all
"""
import os
import sys
import sqlite3
import argparse
from pathlib import Path

from dotenv import load_dotenv
import psycopg

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = str(BASE_DIR / "db.sqlite3")

# FK-safe insertion order (parents before children)
ALL_TABLES = [
    "auth_group",
    "auth_user",
    "auth_user_groups",
    "auth_user_user_permissions",
    "companies_financialmetric",
    "companies_company",
    "companies_emailverificationtoken",
    "companies_follow",
    "companies_alertpreference",
    "companies_notification",
    "companies_filing",
    "companies_financial",
    "companies_note",
    "companies_notecompany",
    "companies_discussionthread",
    "companies_discussionmessage",
    "companies_chatsession",
    "companies_chatmessage",
    "companies_savedscreen",
]


def get_columns(sqlite_conn, table):
    cur = sqlite_conn.execute(f'PRAGMA table_info("{table}")')
    return [row[1] for row in cur.fetchall()]


def migrate_table(sqlite_conn, pg_dsn, table, batch_size=2000):
    # Check table exists in SQLite
    cur = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    if not cur.fetchone():
        print(f"  Skipping — not in SQLite")
        return 0

    cols = get_columns(sqlite_conn, table)
    cols_quoted = ", ".join(f'"{c}"' for c in cols)

    total = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"  {total:,} rows to insert")
    if total == 0:
        return 0

    inserted = 0
    with psycopg.connect(pg_dsn) as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(f'DELETE FROM "{table}"')

            data_cur = sqlite_conn.execute(f'SELECT {cols_quoted} FROM "{table}"')

            with cur.copy(f'COPY "{table}" ({cols_quoted}) FROM STDIN') as copy:
                while True:
                    rows = data_cur.fetchmany(batch_size)
                    if not rows:
                        break
                    for row in rows:
                        copy.write_row(row)
                    inserted += len(rows)
                    print(f"  {inserted:,}/{total:,}", end="\r", flush=True)

            # Reset auto-increment sequence
            if "id" in cols:
                cur.execute(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE(MAX(id), 1)
                    ) FROM "{table}"
                """)

        pg_conn.commit()

    print(f"  {inserted:,}/{total:,} — done")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL via COPY")
    parser.add_argument("--table", help="Single table to migrate (e.g. companies_company)")
    parser.add_argument("--all", action="store_true", help="Migrate all tables")
    parser.add_argument("--sqlite", default=SQLITE_PATH, help="Path to SQLite DB")
    args = parser.parse_args()

    if not args.table and not args.all:
        print("Specify --table TABLE_NAME or --all")
        print("Tables:", ", ".join(ALL_TABLES))
        sys.exit(1)

    pg_dsn = os.environ.get("DATABASE_URL")
    if not pg_dsn:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    tables = [args.table] if args.table else ALL_TABLES
    sqlite_conn = sqlite3.connect(args.sqlite)

    total_rows = 0
    for table in tables:
        print(f"\n[{table}]")
        try:
            n = migrate_table(sqlite_conn, pg_dsn, table, batch_size=2000)
            total_rows += n
        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()

    sqlite_conn.close()
    print(f"\nDone. Total rows inserted: {total_rows:,}")


if __name__ == "__main__":
    main()
