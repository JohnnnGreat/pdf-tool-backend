#!/bin/bash
# Production entrypoint — waits for PostgreSQL, then starts the app.
set -e

echo "==> [entrypoint] Waiting for PostgreSQL to be ready..."

# Extract host and port from DATABASE_URL
# Expected format: postgresql://user:pass@host:port/dbname
DB_HOST=$(echo "$DATABASE_URL" | sed -e 's|.*@||' -e 's|:.*||' -e 's|/.*||')
DB_PORT=$(echo "$DATABASE_URL" | sed -e 's|.*:||' -e 's|/.*||')
DB_PORT=${DB_PORT:-5432}

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -q; do
    echo "==> [entrypoint] PostgreSQL is not ready yet — retrying in 2s..."
    sleep 2
done

echo "==> [entrypoint] PostgreSQL is ready."
echo "==> [entrypoint] Running database migrations..."
alembic upgrade head
echo "==> [entrypoint] Migrations complete."
echo "==> [entrypoint] Starting application..."
exec "$@"
