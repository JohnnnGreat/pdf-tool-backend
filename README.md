# DocForge Backend API

FastAPI-based Python backend for the DocForge PDF/document processing SaaS platform.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Overview](#api-overview)
- [QA Analysis — Issues & Findings](#qa-analysis--issues--findings)
  - [Critical Security Issues](#critical-security-issues)
  - [Architecture Issues](#architecture-issues)
  - [Code Quality Issues](#code-quality-issues)
  - [Missing Features](#missing-features)
  - [API Design Issues](#api-design-issues)
  - [Database & ORM Issues](#database--orm-issues)
  - [Testing Gaps](#testing-gaps)
  - [Performance Issues](#performance-issues)
  - [DevOps & Production Readiness](#devops--production-readiness)
  - [Dependencies](#dependencies)
- [Priority Fix Roadmap](#priority-fix-roadmap)
- [Competitive Analysis — Gaps vs ilovepdf / Smallpdf](#competitive-analysis--gaps-vs-ilovepdf--smallpdf)

---

## Project Overview

DocForge is a PDF and document processing SaaS platform. The backend exposes a REST API (`/api/v1/`) that handles:

- PDF operations: merge, split, compress, rotate, watermark, reorder, unlock, protect
- Format conversion: PDF ↔ Word, Excel, PowerPoint, Images, HTML, Markdown, text
- Image operations: resize, crop, convert, compress, rotate, watermark, OCR
- AI features: chat, summarize, translate, rephrase
- Document generators: invoices, QR codes, barcodes, resumes, certificates
- User management: registration, login, JWT auth, API keys, usage tiers
- Billing: webhook handlers for Paystack, Flutterwave, Lemon Squeezy, Stripe

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.115 |
| Server | Uvicorn 0.34 |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite (dev) / PostgreSQL (prod) |
| PDF Processing | PyMuPDF 1.27, pypdf 5.4 |
| Image Processing | Pillow 12.1 |
| OCR | Tesseract via pytesseract |
| Document Conversion | LibreOffice (soffice) |
| Auth | python-jose (JWT), passlib+bcrypt |
| AI | Groq API |
| Testing | pytest, httpx, pytest-asyncio |

---

## Project Structure

```
pdf-tool-backend/
├── app/
│   ├── __init__.py          # App factory, startup/shutdown events
│   ├── api/
│   │   └── v1/              # 20 route modules (pdf, image, convert, ai, auth, ...)
│   ├── core/
│   │   ├── config.py        # Pydantic settings (reads from .env)
│   │   ├── security.py      # JWT encode/decode, password hashing
│   │   ├── dependencies.py  # FastAPI Depends() helpers
│   │   ├── middleware.py     # CORS, rate limiting middleware
│   │   └── api_key_auth.py  # API key validation + quota tracking
│   ├── db/
│   │   ├── base.py          # SQLAlchemy declarative base
│   │   └── session.py       # Engine + SessionLocal factory
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response DTOs
│   ├── services/            # Business logic (13 services)
│   ├── repositories/        # Data access layer (BaseRepository pattern)
│   └── utils/
│       ├── file_handler.py  # Upload read, save, cleanup
│       ├── rate_limiter.py  # In-memory per-key rate limiting
│       └── cleanup.py       # Temp file cleanup scheduler
├── tests/
│   ├── conftest.py
│   └── api/
│       └── test_health.py   # Only 1 test currently
├── requirements.txt
└── .env                     # DO NOT COMMIT — see Security section
```

---

## Getting Started

### Prerequisites

Install system-level dependencies before running the app:

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr libreoffice poppler-utils

# macOS
brew install tesseract libreoffice poppler
```

### Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configure environment

```bash
cp .env.example .env
# Edit .env and fill in all required values
```

### Run the development server

```bash
uvicorn app:app --reload --port 8000
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values. Never commit `.env`.

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | JWT signing secret (min 32 chars, random) | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes (prod) |
| `GROQ_API_KEY` | Groq AI API key | Yes |
| `TESSERACT_PATH` | Path to tesseract binary | Yes |
| `LIBREOFFICE_PATH` | Path to soffice binary | Yes |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | Yes |
| `MAX_FILE_SIZE_MB` | Max upload size in MB | Yes |

---

## API Overview

Base URL: `/api/v1/`

All authenticated endpoints accept either:
- `Authorization: Bearer <jwt_token>` header
- `X-API-Key: <api_key>` header

| Group | Prefix | Auth Required |
|-------|--------|---------------|
| Health | `/health` | No |
| Auth | `/auth` | No (login/register) |
| Users | `/users` | JWT |
| PDF Tools | `/pdf` | JWT or API Key |
| Images | `/image` | JWT or API Key |
| Convert | `/convert` | JWT or API Key |
| OCR | `/ocr` | JWT or API Key |
| AI | `/ai` | JWT or API Key |
| Generators | `/generate` | JWT or API Key |
| API Keys | `/api-keys` | JWT |
| Billing | `/billing` | JWT |
| Webhooks | `/webhooks` | Signature verified |
| Jobs | `/jobs` | JWT |
| Dashboard | `/dashboard` | JWT |

---

## QA Analysis — Issues & Findings

The following is a comprehensive quality assurance analysis of the backend codebase conducted on 2026-04-27.

---

### Critical Security Issues

#### 1. Exposed Groq API Key in Git
- **File:** `.env:88`
- **Issue:** `GROQ_API_KEY` was committed to git in plaintext.
- **Action:**
  1. Rotate the key immediately in the Groq console
  2. Remove `.env` from git: `git rm --cached .env && git commit`
  3. Clean git history: use BFG Repo Cleaner or `git filter-branch`
  4. Ensure `.env` is in `.gitignore`

#### 2. Weak Default SECRET_KEY
- **File:** `app/core/config.py:9`
- **Code:** `SECRET_KEY: str = "change-me-in-production"`
- **Risk:** If this default ships to production, all JWT tokens are cryptographically weak.
- **Fix:** Add a startup guard that refuses to boot if `SECRET_KEY` equals the default or is shorter than 32 characters.

#### 3. No CSRF Protection
- **Issue:** No CSRF middleware. State-changing operations accept requests from any origin.
- **Fix:** Add CSRF middleware or enforce `SameSite=Strict` on cookies.

#### 4. Subprocess Path Injection Risk
- **File:** `app/services/convert_service.py:15-30`
- **Issue:** `LIBREOFFICE_PATH` from settings is passed directly into `subprocess.run()`. The path parsing (`if lo.startswith('"')`) is fragile.
- **Fix:** Validate the path with `pathlib.Path.resolve()` and check it points to a known executable before use.

#### 5. No Rate Limiting on Auth Endpoints
- **Issue:** `/auth/login` and `/auth/register` have no brute-force protection.
- **Fix:** Apply rate limiting (e.g., 5 requests/minute per IP) on auth routes.

#### 6. JWT Does Not Check `is_active` on Every Request
- **File:** `app/core/dependencies.py:20-30`
- **Issue:** A deactivated user with a valid JWT can still make requests for up to 30 minutes (token TTL).
- **Fix:** Always query the DB for `is_active` status, or store it in the token with a short TTL.

#### 7. No Audit Logging for Security Events
- **Issue:** Failed auth attempts, expired keys, and rate limit violations are not logged.
- **Fix:** Add structured log entries for all security-relevant events.

#### 8. File Upload Decompression Bomb Risk
- **File:** `app/utils/file_handler.py:28-34`
- **Issue:** Only the raw uploaded byte size is checked. A compressed PDF that expands to gigabytes in memory is not caught.
- **Fix:** Stream file processing; enforce limits on decompressed output size.

---

### Architecture Issues

#### 1. No Database Migrations (Alembic Missing)
- **File:** `app/__init__.py:34-39`
- **Code:**
  ```python
  @app.on_event("startup")
  def create_tables():
      Base.metadata.create_all(bind=engine)
  ```
- **Issue:** Tables are auto-created on every startup. There is no versioned migration system.
- **Risk:** Schema changes in production cannot be safely applied, rolled back, or audited.
- **Fix:** Add Alembic. Generate an initial migration from the current models immediately.

#### 2. SQLite Default is Unsafe for Production
- **File:** `app/core/config.py:13`
- **Code:** `DATABASE_URL: str = "sqlite:///./docforge.db"`
- **Issue:** SQLite cannot handle concurrent writes. Two simultaneous uploads will cause database lock errors.
- **Fix:** Default to PostgreSQL. Keep SQLite only for isolated test runs.

#### 3. `lazy="noload"` ORM Bug
- **File:** `app/models/user.py:22-23`
- **Code:**
  ```python
  api_keys = relationship("APIKey", ..., lazy="noload")
  jobs = relationship("ProcessingJob", ..., lazy="noload")
  ```
- **Issue:** `lazy="noload"` means these relationships are never loaded. Any code accessing `user.api_keys` silently gets an empty list instead of actual data.
- **Fix:** Change to `lazy="select"` (default) or use explicit `selectinload()` where needed.

#### 4. No Connection Pool Configuration
- **File:** `app/db/session.py:7-10`
- **Issue:** No `pool_size`, `max_overflow`, or `pool_recycle` configured. Under load, connections will be exhausted.
- **Fix:** Add `pool_size=20, max_overflow=0, pool_recycle=3600` to `create_engine()`.

---

### Code Quality Issues

#### 1. Debug Print Statements in Production Code
- **File:** `app/services/convert_service.py:33-43`
- **Code:**
  ```python
  print(f"DEBUG: LO stdout: {result.stdout}")
  print(f"DEBUG: LO stderr: {result.stderr}")
  print(f"DEBUG: Files in {output_dir}: {os.listdir(output_dir)}")
  ```
- **Fix:** Replace all `print()` calls with `logger.debug()` from the standard `logging` module.

#### 2. Silent Exception Swallowing
- **File:** `app/api/v1/ai.py:46`
- **Code:**
  ```python
  except Exception:
      parsed_history = []
  ```
- **File:** `app/api/v1/webhooks.py` (multiple locations)
- **Issue:** Payment webhook failures are silently swallowed. User plan upgrades can fail without anyone knowing.
- **Fix:** At minimum log the exception; for webhooks, return a 500 so the payment provider retries.

#### 3. No Input Validation on Image Dimensions
- **File:** `app/api/v1/image.py:45-49, 64-79`
- **Issue:** `width`, `height`, `x`, `y` parameters have no `ge`/`le` constraints. Requests for 0px or 100,000px dimensions are accepted.
- **Fix:** Use Pydantic `Field(ge=1, le=10000)` on all dimension parameters.

#### 4. No Validation on Range Strings
- **File:** `app/api/v1/pdf.py:65-79`
- **Issue:** The `ranges` parameter for split-range is a raw string with no validation. Invalid values like `"5-3"` or `"abc"` are only caught deep in the service layer with unclear error messages.
- **Fix:** Add a Pydantic validator that parses and validates the range format before it reaches the service.

#### 5. Inconsistent Error Response Format
- **Issue:** Different endpoints return errors in different shapes — some use `HTTPException(detail=...)`, some return bare exception messages, some provide no error detail at all.
- **Fix:** Implement a global exception handler that normalizes all error responses to a consistent schema.

#### 6. Tesseract Availability Checked Per-Request
- **File:** `app/services/ocr_service.py:11-23`
- **Issue:** Every OCR request calls `pytesseract.get_tesseract_version()` to check if Tesseract is installed. This should be checked once at startup.
- **Fix:** Move the Tesseract check to the startup event and fail fast if it is missing.

---

### Missing Features

| Feature | Current Status | Notes |
|---------|---------------|-------|
| Email verification | `is_verified` column exists but never set to `true` | No verification email sent on registration |
| Password reset | Not implemented | No `/auth/forgot-password` or `/auth/reset-password` endpoints |
| OAuth2 / Social login | Not implemented | Email + password only |
| Audit logging | Not implemented | Required for GDPR / SOC2 compliance |
| WebSocket support | SSE used for AI chat | SSE is one-way; bidirectional chat not supported |
| Webhook signature — Coinbase | Incomplete | Only Paystack, Flutterwave, Lemon Squeezy implemented |
| Request timeouts on long jobs | Not implemented | Malicious users can start jobs and abandon them, tying up resources |
| Soft deletes | Not implemented | User deletion is hard delete; all history is permanently lost |
| Pagination on job listing | Not implemented | No paginated endpoint for browsing job history |
| Batch processing | Service exists | Route verification needed; no frontend UI |

---

### API Design Issues

#### 1. Filename Not RFC 5987 Encoded
- **File:** `app/api/v1/convert.py:22-34`
- **Issue:** `Content-Disposition` header uses raw filename. Special characters and non-ASCII names will break.
- **Fix:** Encode with `urllib.parse.quote(filename)`.

#### 2. Large Responses Not Streamed
- **Issue:** Entire file content is loaded into memory before sending as a response. This blocks the handler and requires memory proportional to file size.
- **Fix:** Use FastAPI's `FileResponse` or `StreamingResponse` for file downloads.

#### 3. No OpenAPI Auth Documentation
- **Issue:** It is not documented in route decorators which endpoints require JWT vs API key vs no auth.
- **Fix:** Add OpenAPI `security` tags to each route group.

#### 4. No Pagination on List Endpoints
- **Issue:** List endpoints (jobs, API keys) return all records without pagination.
- **Fix:** Add `limit` and `offset` (or cursor-based) pagination.

---

### Database & ORM Issues

| Issue | File | Severity |
|-------|------|----------|
| No Alembic migrations | `app/__init__.py` | Critical |
| `lazy="noload"` causes silent empty results | `app/models/user.py` | High |
| No connection pool configuration | `app/db/session.py` | High |
| No database health check in `/health` endpoint | `app/api/v1/health.py` | Medium |
| Hard deletes — no `deleted_at` soft delete | `app/models/` | Medium |
| No `updated_at` on APIKey and ProcessingJob | `app/models/` | Low |
| Monthly request counter reset not thread-safe | `app/core/api_key_auth.py:96-100` | Medium |

---

### Testing Gaps

Current state: **1 test exists** (`test_health_check`). Effective coverage is 0%.

Tests that must be written:

- [ ] User registration — success, duplicate email, invalid email
- [ ] User login — success, wrong password, inactive account
- [ ] JWT validation — expired token, invalid signature, missing token
- [ ] API key creation, rotation, revocation
- [ ] API key rate limiting — per-minute and per-month limits
- [ ] PDF merge — success, invalid file, file too large
- [ ] PDF split — valid ranges, invalid ranges, out-of-bounds pages
- [ ] PDF compress — success, already-minimal file
- [ ] Image resize — valid dimensions, zero dimensions, oversized
- [ ] OCR — valid image, unsupported format, Tesseract unavailable
- [ ] Conversion — PDF to DOCX, DOCX to PDF, LibreOffice unavailable
- [ ] Webhook signature verification — valid signature, tampered payload
- [ ] Error handling — 422 on invalid input, 413 on oversize file, 500 on service crash
- [ ] Concurrent upload handling
- [ ] File cleanup after processing

Additional setup needed:
- Separate test database (SQLite in-memory) so tests do not pollute dev data
- `pytest.ini` with asyncio mode configuration
- Fixtures for authenticated client, test user, test API key

---

### Performance Issues

#### 1. Entire File Loaded Into Memory
- **File:** `app/utils/file_handler.py:37-40`
- **Code:**
  ```python
  content = await file.read()
  validate_file_size(content)
  ```
- **Issue:** A 50MB upload loads 50MB into RAM. 20 concurrent uploads = 1GB RAM minimum.
- **Fix:** Stream file to a temp path on disk, checking size incrementally while writing.

#### 2. In-Memory Rate Limiter Memory Leak
- **File:** `app/utils/rate_limiter.py:13-31`
- **Issue:** `_per_key_timestamps` dict grows indefinitely as new API keys are added. No eviction policy.
- **Fix:** Replace with Redis-backed rate limiting (`slowapi` + Redis, or `aioredis` directly).

#### 3. Blocking Conversion Operations
- **Issue:** LibreOffice conversion is a blocking subprocess call. A 100MB file conversion locks the request handler for the duration.
- **Fix:** Use a job queue (Celery + Redis) for long-running operations. Return a job ID immediately and let the client poll for status.

#### 4. No Response Compression
- **Issue:** Large JSON responses (AI chat, job history) are not gzip-compressed.
- **Fix:** Add `from fastapi.middleware.gzip import GZipMiddleware` to the app.

#### 5. N+1 Risk in API Key Auth
- **File:** `app/core/api_key_auth.py`
- **Issue:** Each request loads the API key and then calls `record_request()`, which may trigger a second query. Under high traffic this compounds.
- **Fix:** Batch request recording or use a write-behind cache.

---

### DevOps & Production Readiness

#### Missing Infrastructure

| Item | Status | Priority |
|------|--------|----------|
| Dockerfile | Missing | Critical |
| docker-compose.yml | Missing | Critical |
| .dockerignore | Missing | High |
| Alembic migrations | Missing | Critical |
| Structured JSON logging | Not implemented | High |
| Request ID / trace ID | Not implemented | High |
| Prometheus metrics | Not implemented | Medium |
| Comprehensive health check | Stub only | High |
| Graceful shutdown handler | Not implemented | Medium |
| HTTPS enforcement / HSTS | Not implemented | High |
| Environment-specific config | Single .env only | Medium |
| Startup validation of external tools | Not implemented | High |

#### Health Check Is a Stub
- **File:** `app/api/v1/health.py`
- **Current:**
  ```python
  def health_check():
      return HealthResponse(status="ok")
  ```
- **Required:** Check database connectivity, Tesseract availability, LibreOffice availability, available disk space. Return `"degraded"` if any dependency is down.

#### No Structured Logging
- **File:** `app/__init__.py:11`
- **Current:** `logging.basicConfig(level=logging.INFO)` — plain text to stdout only.
- **Fix:** Use `python-json-logger` for structured JSON output. Add request ID to every log line via middleware.

#### No Dockerfile
A minimal Dockerfile must include:
- Python 3.11 slim base image
- System packages: `tesseract-ocr libreoffice poppler-utils`
- pip install from requirements.txt
- Uvicorn as the entry point

---

### Dependencies

#### Missing Packages

| Package | Purpose |
|---------|---------|
| `alembic` | Database migrations |
| `python-json-logger` | Structured logging |
| `slowapi` or `aioredis` | Redis-backed rate limiting |
| `prometheus-client` | Metrics endpoint for monitoring |
| `celery` | Async job queue for long-running tasks |

#### Dependency Pinning
- `requirements.txt` pins top-level packages but not transitive dependencies.
- **Fix:** Use `pip-compile` (pip-tools) or migrate to Poetry to lock all transitive deps.

#### System-Level Dependencies
LibreOffice, Tesseract, and Poppler are system packages not managed by pip. They must be:
1. Documented in setup instructions
2. Included in the Dockerfile
3. Validated at application startup

---

## Priority Fix Roadmap

### This Week — Security & Data Safety

- [ ] Rotate the Groq API key in the Groq console
- [ ] Run `git rm --cached .env` and commit; clean git history with BFG
- [ ] Add `.env` to `.gitignore` (verify it stays out)
- [ ] Fix `lazy="noload"` to `lazy="select"` on User relationships — this is causing silent data loss
- [ ] Add startup guard: refuse to boot if `SECRET_KEY` equals default value
- [ ] Replace all `print(f"DEBUG...")` calls with `logger.debug()`

### Next 2 Weeks — Production Readiness

- [ ] Set up Alembic: `pip install alembic && alembic init alembic` — generate initial migration
- [ ] Create Dockerfile and docker-compose.yml (postgres + redis + app services)
- [ ] Implement email verification flow (send email on register, `/auth/verify-email` endpoint)
- [ ] Implement password reset (`/auth/forgot-password` + `/auth/reset-password`)
- [ ] Add comprehensive health check (DB, Tesseract, LibreOffice, disk space)
- [ ] Replace `logging.basicConfig` with structured JSON logging + request ID middleware
- [ ] Add `GZipMiddleware` for response compression
- [ ] Add bounds validation (`Field(ge=1, le=10000)`) on all image dimension parameters

### Next Month — Quality & Features

- [ ] Write test suite: 30+ tests covering auth, file ops, error cases, edge cases
- [ ] Stream file uploads to disk instead of loading entire content into memory
- [ ] Replace in-memory rate limiter with Redis-backed implementation
- [ ] Implement job queue (Celery + Redis) for LibreOffice and long OCR operations
- [ ] Add pagination to all list endpoints
- [ ] Implement soft deletes (`deleted_at`) for users and jobs
- [ ] Add OAuth2 / social login (Google, GitHub)
- [ ] Fix RFC 5987 filename encoding in `Content-Disposition` headers

### Quarter — Scale & Enterprise

- [ ] OpenTelemetry tracing (request ID propagation, distributed trace)
- [ ] Prometheus metrics endpoint + Grafana dashboard
- [ ] Audit logging (GDPR-compliant record of sensitive actions)
- [ ] 2FA / TOTP support
- [ ] SSO / SAML for enterprise tier
- [ ] Performance testing and load testing (Locust or k6)
- [ ] HTTPS enforcement + HSTS headers
- [ ] API versioning strategy for v2

---

## Competitive Analysis — Gaps vs ilovepdf / Smallpdf

To compete with established PDF SaaS platforms, the following features are standard expectations that are currently missing:

| Feature | ilovepdf | Smallpdf | DocForge | Notes |
|---------|----------|----------|---------|-------|
| Batch processing | Yes | Yes | No UI | Backend service exists, needs frontend |
| Before/after size comparison | Yes | Yes | No | Show original vs compressed file size |
| File result history | Yes (2h) | Yes (1h) | No | Let users re-download recent results |
| Shareable download links | Yes | Yes | No | Public link to processed file |
| Progress percentage on long jobs | Yes | Yes | Spinner only | Show real % during OCR/conversion |
| Usage quota display | Yes | Yes | No | "3 of 5 daily conversions used" |
| Related tools suggestions | Yes | Yes | No | Post-processing tool recommendations |
| Developer API | Yes | Yes | No | REST API for developers — major monetization lever |
| Free/pro feature gates | Yes | Yes | No | Pricing page and plan limits not implemented |
| Offline support / PWA | Partial | No | No | Service worker for offline detection |
| 2FA | Yes | Yes | No | Security expectation for paid accounts |
| Mobile-optimized flow | Yes | Yes | Partial | Full upload → process → download on mobile |

---

## Summary

| Category | Status | Risk Level |
|----------|--------|-----------|
| Architecture | Good foundation | Low |
| Security | Critical issues present | Critical |
| Code Quality | Several issues | Medium |
| Missing Features | ~40% of planned features absent | High |
| API Design | Generally good, minor issues | Low |
| Database | Risky (no migrations) | High |
| Testing | Effectively zero coverage | Critical |
| Performance | Unoptimized for production load | High |
| DevOps / Infrastructure | Not production-ready | Critical |
| Competitive Positioning | Significant gaps | High |

The codebase has a solid, well-organized architecture and good separation of concerns. However, it is **not production-ready** due to a critical security leak, missing migrations, zero test coverage, and no containerization. The foundation is strong — with focused effort on the priority roadmap above, it can reach a shippable, competitive state.
