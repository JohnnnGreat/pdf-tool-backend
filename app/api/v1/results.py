"""Results — store processed files for re-download and sharing.

POST /results/save  — upload a result blob; returns a share token + expiry
GET  /results/{token} — download a stored result (no auth required)

Files are stored at RESULTS_DIR/{token}/{filename} and auto-deleted by the
hourly cleanup job after TEMP_FILE_RETENTION_MINUTES.
"""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.utils.rate_limiter import InMemoryRateLimiter, get_client_ip
from fastapi import Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/results", tags=["Results"])

_limiter = InMemoryRateLimiter(requests_per_minute=20, requests_per_hour=120)

_TTL_MINUTES = settings.TEMP_FILE_RETENTION_MINUTES


def _result_dir(token: str) -> str:
    return os.path.join(settings.RESULTS_DIR, token)


def _expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=_TTL_MINUTES)


@router.post("/save")
async def save_result(
    request: Request,
    file: UploadFile = File(...),
    filename: str = Form(...),
):
    """Upload a processed result blob. Returns a share token and expiry."""
    _limiter.check(get_client_ip(request))

    # Limit result size — same as general upload cap
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        return JSONResponse({"detail": "File too large."}, status_code=413)

    token = secrets.token_urlsafe(24)
    result_dir = _result_dir(token)
    os.makedirs(result_dir, exist_ok=True)

    # Sanitise filename
    safe_name = os.path.basename(filename) or "result"
    file_path = os.path.join(result_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    expires = _expires_at()
    logger.debug("Result saved: token=%s filename=%s expires=%s", token, safe_name, expires.isoformat())

    return {
        "share_token": token,
        "expires_at": expires.isoformat(),
        "download_url": f"/api/v1/results/{token}",
    }


@router.get("/{token}")
def download_result(token: str):
    """Download a stored result by share token. No authentication required."""
    result_dir = _result_dir(token)
    if not os.path.isdir(result_dir):
        return JSONResponse({"detail": "Result not found or has expired."}, status_code=404)

    files = [f for f in os.listdir(result_dir) if os.path.isfile(os.path.join(result_dir, f))]
    if not files:
        return JSONResponse({"detail": "Result not found or has expired."}, status_code=404)

    file_path = os.path.join(result_dir, files[0])
    filename = files[0]
    encoded = quote(filename)

    return FileResponse(
        file_path,
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Cache-Control": "private, max-age=3600",
        },
    )
