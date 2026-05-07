#!/bin/bash
# Production entrypoint — waits for PostgreSQL, then starts the app.
set -e

echo "==> [entrypoint] Waiting for PostgreSQL to be ready..."

until python -c "
import psycopg2, os, sys
try:
    psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=3)
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    echo "==> [entrypoint] PostgreSQL is not ready yet — retrying in 2s..."
    sleep 2
done

echo "==> [entrypoint] PostgreSQL is ready."
echo "==> [entrypoint] Running database migrations..."
alembic upgrade head
echo "==> [entrypoint] Migrations complete."
echo "==> [entrypoint] Starting application..."
exec "$@"
