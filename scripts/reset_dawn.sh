#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +a
fi

REDIS_URL=${REDIS_URL:-"redis://127.0.0.1:6379/0"}
POSTGRES_DSN=${POSTGRES_DSN:-""}

if [ -z "$POSTGRES_DSN" ]; then
  echo "POSTGRES_DSN is not set. Add it to .env or export it before running." >&2
  exit 1
fi

if ! command -v redis-cli >/dev/null 2>&1; then
  echo "redis-cli not found. Install Redis CLI to continue." >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found. Install PostgreSQL client tools to continue." >&2
  exit 1
fi

PG_URL="$POSTGRES_DSN"
PG_URL="${PG_URL/postgresql+psycopg2:/postgresql:}"
PG_URL="${PG_URL/postgresql+psycopg:/postgresql:}"
PG_URL="${PG_URL/postgresql+asyncpg:/postgresql:}"

cat <<CONFIRM
This will permanently wipe:
- Redis database at: $REDIS_URL
- Postgres schema 'public' at: $PG_URL

Type RESET to continue:
CONFIRM

read -r CONFIRM_TEXT
if [ "${CONFIRM_TEXT:-}" != "RESET" ]; then
  echo "Aborted."
  exit 1
fi

echo "Flushing Redis…"
redis-cli -u "$REDIS_URL" FLUSHDB

echo "Dropping Postgres schema public…"
psql "$PG_URL" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

cat <<DONE
Done.
Redis flushed and Postgres schema recreated.
DONE
