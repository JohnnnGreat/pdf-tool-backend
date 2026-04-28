import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.middleware import logging_middleware
from app.api.v1.router import router as v1_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        version="1.0.0",
        redoc_url=None,
        swagger_ui_parameters={"persistAuthorization": True},
    )

    # ---------------------------------------------------------------------------
    # Middleware — order matters: outermost first
    # ---------------------------------------------------------------------------
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BaseHTTPMiddleware, dispatch=logging_middleware)

    # ---------------------------------------------------------------------------
    # Global exception handler — consistent error response shape
    # ---------------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("Unhandled exception [request_id=%s] %s %s", request_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. Please try again.", "request_id": request_id},
        )

    # ---------------------------------------------------------------------------
    # Router
    # ---------------------------------------------------------------------------
    app.include_router(v1_router, prefix="/api/v1")

    @app.get("/redoc", include_in_schema=False)
    async def custom_redoc_html():
        return get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - ReDoc",
            redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js",
            with_google_fonts=False,
        )

    # ---------------------------------------------------------------------------
    # Startup events
    # ---------------------------------------------------------------------------
    @app.on_event("startup")
    def create_tables():
        from app.db.base import Base
        from app.db.session import engine
        import app.models  # noqa: F401 — registers all models with Base
        Base.metadata.create_all(bind=engine)

    @app.on_event("startup")
    def validate_config():
        if settings.SECRET_KEY in ("change-me-in-production", "") or len(settings.SECRET_KEY) < 32:
            logger.warning(
                "SECRET_KEY is set to an insecure default. This is acceptable in development "
                "but MUST be changed before deploying to production."
            )

    @app.on_event("startup")
    def check_external_tools():
        import subprocess
        import shutil

        # Tesseract
        try:
            import pytesseract
            if settings.TESSERACT_PATH:
                pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH
            pytesseract.get_tesseract_version()
            logger.info("Tesseract OCR: available")
        except Exception as exc:
            logger.warning("Tesseract OCR not found — OCR endpoints will return 501: %s", exc)

        # LibreOffice
        try:
            lo = settings.LIBREOFFICE_PATH or "soffice"
            lo = lo.strip().strip('"')
            result = subprocess.run([lo, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info("LibreOffice: available (%s)", result.stdout.strip())
            else:
                logger.warning("LibreOffice found but returned non-zero exit code — conversion may fail")
        except Exception as exc:
            logger.warning("LibreOffice not found — document conversion endpoints will fail: %s", exc)

        # Ensure result storage dir exists
        import os as _os
        _os.makedirs(settings.RESULTS_DIR, exist_ok=True)

        # Upload/output directories
        for label, path in (("UPLOAD_DIR", settings.UPLOAD_DIR), ("OUTPUT_DIR", settings.OUTPUT_DIR)):
            disk = shutil.disk_usage(path) if __import__("os").path.exists(path) else None
            if disk:
                free_gb = disk.free / (1024 ** 3)
                if free_gb < 1.0:
                    logger.warning("%s has less than 1GB free (%.1fGB). Processing may fail.", label, free_gb)

    return app
