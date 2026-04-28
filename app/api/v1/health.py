import logging
import shutil
import subprocess

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    checks: dict[str, str] = {}
    overall = "ok"

    # Database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Health check — database unreachable: %s", exc)
        checks["database"] = "degraded"
        overall = "degraded"

    # Tesseract
    try:
        import pytesseract
        if settings.TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH
        pytesseract.get_tesseract_version()
        checks["tesseract"] = "ok"
    except Exception as exc:
        logger.warning("Health check — Tesseract unavailable: %s", exc)
        checks["tesseract"] = "degraded"
        overall = "degraded"

    # LibreOffice
    try:
        lo = settings.LIBREOFFICE_PATH or "soffice"
        lo = lo.strip().strip('"')
        result = subprocess.run([lo, "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            checks["libreoffice"] = "ok"
        else:
            checks["libreoffice"] = "degraded"
            overall = "degraded"
    except Exception as exc:
        logger.warning("Health check — LibreOffice unavailable: %s", exc)
        checks["libreoffice"] = "degraded"
        overall = "degraded"

    # Disk space — warn if less than 1 GB free in upload/output dirs
    for label, path in (("upload_dir", settings.UPLOAD_DIR), ("output_dir", settings.OUTPUT_DIR)):
        try:
            usage = shutil.disk_usage(path)
            free_gb = usage.free / (1024 ** 3)
            checks[label] = "ok" if free_gb >= 1.0 else f"low ({free_gb:.1f}GB free)"
            if free_gb < 1.0:
                overall = "degraded"
        except Exception as exc:
            logger.warning("Health check — disk usage check failed for %s: %s", path, exc)
            checks[label] = "unknown"

    return {"status": overall, "version": "1.0.0", "checks": checks}
