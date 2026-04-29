# =============================================================================
# Stage 1 — Python dependency builder
# Compiles packages that need gcc/g++ so they are NOT in the final image.
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    pkg-config \
    libcairo2-dev \
    libffi-dev \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal --default-toolchain stable

ENV PATH="/root/.cargo/bin:${PATH}"
ENV CARGO_HOME="/root/.cargo"
ENV CARGO_TARGET_DIR="/tmp/rust-target"
ENV PDFIUM_AUTO_CACHE_DIR="/tmp/pdfium-cache"

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir maturin && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt && \
    pip install --prefix=/install --no-cache-dir "gunicorn==21.2.0"

COPY Cargo.toml Cargo.lock pyproject.toml README.md ./
COPY rust_converter/ ./rust_converter/
COPY src/ ./src/

RUN python -m maturin build --release --interpreter python --out /dist && \
    pip install --prefix=/install --no-cache-dir /dist/rust_converter-*.whl


# =============================================================================
# Stage 2 — Production runtime image
# Only runtime system packages, no build tools.
# =============================================================================
FROM python:3.11-slim AS runtime

# Install system-level runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PostgreSQL client (pg_isready for health/entrypoint check)
    postgresql-client \
    libpq5 \
    # LibreOffice for document conversion (Word, Excel, PPT ↔ PDF)
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    # Tesseract OCR engine + English language pack
    tesseract-ocr \
    tesseract-ocr-eng \
    # Poppler utilities — used by pdf2image
    poppler-utils \
    # Common fonts (needed by LibreOffice for rendering)
    fonts-liberation \
    fonts-dejavu-core \
    fonts-noto \
    # curl for HEALTHCHECK
    curl \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Copy compiled Python packages from builder stage
COPY --from=builder /install /usr/local

# Create a non-root user for security
RUN groupadd --gid 1001 docforge && \
    useradd --uid 1001 --gid docforge --shell /bin/bash --create-home docforge

WORKDIR /app

ENV PDFIUM_AUTO_CACHE_DIR="/home/docforge/.cache/pdfium-auto"

# Create directories for file processing, owned by our app user
RUN mkdir -p uploads outputs /home/docforge/.cache/pdfium-auto && \
    chown -R docforge:docforge /app /home/docforge/.cache

# Copy application source
COPY --chown=docforge:docforge app/           ./app/
COPY --chown=docforge:docforge alembic/       ./alembic/
COPY --chown=docforge:docforge templates/     ./templates/
COPY --chown=docforge:docforge run.py         ./run.py
COPY --chown=docforge:docforge alembic.ini    ./alembic.ini
COPY --chown=docforge:docforge requirements.txt ./requirements.txt

# Copy and prepare the entrypoint script
COPY --chown=docforge:docforge scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER docforge

EXPOSE 8000

# Liveness check — fails if app is down or DB is unreachable
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]

# 4 workers by default; override via GUNICORN_WORKERS env var in compose/k8s
CMD ["sh", "-c", "gunicorn run:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${GUNICORN_WORKERS:-4} \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile -"]
