#!/bin/bash
# Development entrypoint — waits for PostgreSQL, then starts uvicorn with hot reload.
set -e

echo "==> [dev] Waiting for PostgreSQL..."

DB_HOST=$(echo "$DATABASE_URL" | sed -e 's|.*@||' -e 's|:.*||' -e 's|/.*||')
DB_PORT=$(echo "$DATABASE_URL" | sed -e 's|.*:||' -e 's|/.*||')
DB_PORT=${DB_PORT:-5432}

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -q; do
    echo "==> [dev] PostgreSQL not ready — retrying in 2s..."
    sleep 2
done

echo "==> [dev] PostgreSQL is ready."
echo "==> [dev] Building Rust converter extension..."
mkdir -p "${CARGO_TARGET_DIR:-/tmp/rust-target}" "${PDFIUM_AUTO_CACHE_DIR:-/tmp/pdfium-cache}" /tmp/maturin-wheels
rm -f /tmp/maturin-wheels/*.whl
python -m maturin build --release --interpreter python --out /tmp/maturin-wheels
python -m pip install --no-deps --force-reinstall /tmp/maturin-wheels/rust_converter-*.whl
echo "==> [dev] Running database migrations..."
alembic upgrade head
echo "==> [dev] Starting uvicorn with hot reload..."
exec "$@"
