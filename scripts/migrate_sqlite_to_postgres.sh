#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   export DATABASE_URL='postgresql://...'
#   ./scripts/migrate_sqlite_to_postgres.sh

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set"
  exit 1
fi

SQLITE_PATH="${SQLITE_PATH:-db.sqlite3}"
if [[ ! -f "$SQLITE_PATH" ]]; then
  echo "SQLite file not found: $SQLITE_PATH"
  exit 1
fi

if command -v pgloader >/dev/null 2>&1; then
  echo "Using pgloader for fast SQLite -> Postgres migration"
  pgloader "$SQLITE_PATH" "$DATABASE_URL"
else
  echo "pgloader not installed; falling back to Django dump/loaddata (slower)"
  python3 manage.py dumpdata \
    --exclude contenttypes \
    --exclude auth.permission \
    > /tmp/tearsheet_dump.json

  DATABASE_URL="$DATABASE_URL" python3 manage.py migrate --noinput
  DATABASE_URL="$DATABASE_URL" python3 manage.py loaddata /tmp/tearsheet_dump.json
fi

echo "Migration finished."
