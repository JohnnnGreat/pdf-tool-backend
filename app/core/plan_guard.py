"""plan_guard — optional JWT quota enforcement for tool endpoints.

Applied as a router-level dependency on all tool routers. For authenticated
users it checks their monthly operation quota and increments the counter.
Unauthenticated requests pass through — they are still subject to IP-based
rate limiting via the per-router _rl() calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.api_key import TIER_LIMITS, TIER_ORDER

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# URL path suffix (last two segments) → (tool_slug, tool_name, category)
_TOOL_MAP: dict[str, tuple[str, str, str]] = {
    # PDF tools
    "pdf/merge":           ("pdf-merge",         "Merge PDF",           "pdf"),
    "pdf/split":           ("pdf-split",          "Split PDF",           "pdf"),
    "pdf/split-range":     ("pdf-split-range",    "Split PDF by Range",  "pdf"),
    "pdf/compress":        ("pdf-compress",       "Compress PDF",        "pdf"),
    "pdf/rotate":          ("pdf-rotate",         "Rotate PDF",          "pdf"),
    "pdf/delete-pages":    ("pdf-delete-pages",   "Delete Pages",        "pdf"),
    "pdf/reorder":         ("pdf-reorder",        "Reorder Pages",       "pdf"),
    "pdf/extract-pages":   ("pdf-extract-pages",  "Extract Pages",       "pdf"),
    "pdf/page-numbers":    ("pdf-page-numbers",   "Add Page Numbers",    "pdf"),
    "pdf/watermark":       ("pdf-watermark",      "Add Watermark",       "pdf"),
    "pdf/header-footer":   ("pdf-header-footer",  "Add Header/Footer",   "pdf"),
    "pdf/crop":            ("pdf-crop",           "Crop PDF",            "pdf"),
    "pdf/flatten":         ("pdf-flatten",        "Flatten PDF",         "pdf"),
    "pdf/repair":          ("pdf-repair",         "Repair PDF",          "pdf"),
    "pdf/metadata":        ("pdf-metadata",       "PDF Metadata",        "pdf"),
    "pdf/redact":          ("pdf-redact",         "Redact PDF",          "pdf"),
    "pdf/compare":         ("pdf-compare",        "Compare PDFs",        "pdf"),
    "pdf/pdf-to-pdfa":     ("pdf-to-pdfa",        "PDF to PDF/A",        "pdf"),
    "pdf/bookmarks":       ("pdf-bookmarks",      "Add Bookmarks",       "pdf"),
    "pdf/overlay":         ("pdf-overlay",        "PDF Overlay",         "pdf"),
    "pdf/fill-form":       ("pdf-fill-form",      "Fill PDF Form",       "pdf"),
    "pdf/pdf-info":        ("pdf-info",           "PDF Info",            "pdf"),
    # Conversion tools
    "convert/pdf-to-word":  ("pdf-to-word",    "PDF to Word",        "convert"),
    "convert/word-to-pdf":  ("word-to-pdf",    "Word to PDF",        "convert"),
    "convert/pdf-to-excel": ("pdf-to-excel",   "PDF to Excel",       "convert"),
    "convert/excel-to-pdf": ("excel-to-pdf",   "Excel to PDF",       "convert"),
    "convert/pdf-to-pptx":  ("pdf-to-pptx",    "PDF to PowerPoint",  "convert"),
    "convert/pptx-to-pdf":  ("pptx-to-pdf",    "PowerPoint to PDF",  "convert"),
    "convert/pdf-to-image": ("pdf-to-image",   "PDF to Image",       "convert"),
    "convert/image-to-pdf": ("image-to-pdf",   "Image to PDF",       "convert"),
    "convert/html-to-pdf":  ("html-to-pdf",    "HTML to PDF",        "convert"),
    "convert/pdf-to-html":  ("pdf-to-html",    "PDF to HTML",        "convert"),
    "convert/md-to-pdf":    ("md-to-pdf",      "Markdown to PDF",    "convert"),
    "convert/csv-to-pdf":   ("csv-to-pdf",     "CSV to PDF",         "convert"),
    "convert/csv-to-excel": ("csv-to-excel",   "CSV to Excel",       "convert"),
    "convert/excel-to-csv": ("excel-to-csv",   "Excel to CSV",       "convert"),
    "convert/text-to-pdf":  ("text-to-pdf",    "Text to PDF",        "convert"),
    "convert/svg-convert":  ("svg-convert",    "SVG Convert",        "convert"),
    "convert/epub-to-pdf":  ("epub-to-pdf",    "EPUB to PDF",        "convert"),
    "convert/json-to-table":("json-to-table",  "JSON to Table",      "convert"),
    # Image tools
    "image/compress":     ("image-compress",     "Compress Image",     "image"),
    "image/resize":       ("image-resize",       "Resize Image",       "image"),
    "image/crop":         ("image-crop",         "Crop Image",         "image"),
    "image/rotate":       ("image-rotate",       "Rotate Image",       "image"),
    "image/convert":      ("image-convert",      "Convert Image",      "image"),
    "image/remove-bg":    ("image-remove-bg",    "Remove Background",  "image"),
    "image/watermark":    ("image-watermark",    "Image Watermark",    "image"),
    "image/to-base64":    ("image-to-base64",    "Image to Base64",    "image"),
    "image/from-base64":  ("image-from-base64",  "Base64 to Image",    "image"),
    "image/exif":         ("image-exif",         "EXIF Viewer",        "image"),
    "image/remove-exif":  ("image-remove-exif",  "Remove EXIF",        "image"),
    "image/bulk-resize":  ("image-bulk-resize",  "Bulk Resize",        "image"),
    "image/color-picker": ("image-color-picker", "Color Picker",       "image"),
    "image/filter":       ("image-filter",       "Image Filter",       "image"),
    # AI tools
    "ai/chat":        ("ai-chat",        "AI Chat",        "ai"),
    "ai/summarize":   ("ai-summarize",   "AI Summarize",   "ai"),
    "ai/extract":     ("ai-extract",     "AI Extract",     "ai"),
    "ai/ocr-cleanup": ("ai-ocr-cleanup", "AI OCR Cleanup", "ai"),
}


def _tool_info_from_path(path: str) -> tuple[str, str, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) >= 2:
        return _TOOL_MAP.get(f"{parts[-2]}/{parts[-1]}")
    return None


def _tier_for_user(user, db: Session) -> str:
    """Return the highest active API-key tier for a user, falling back to 'free'."""
    from app.repositories.api_key_repository import APIKeyRepository
    keys = APIKeyRepository(db).get_by_user(user.id)
    active = [k for k in keys if k.is_active]
    if not active:
        return "free"
    return max(active, key=lambda k: TIER_ORDER.index(k.tier) if k.tier in TIER_ORDER else 0).tier


def _maybe_reset_ops(user, db: Session) -> None:
    """Reset monthly_operations counter if a new calendar month has started."""
    now = datetime.now(timezone.utc)
    reset_at = user.ops_reset_at
    reset_aware = reset_at.replace(tzinfo=timezone.utc) if reset_at.tzinfo is None else reset_at

    if now.year != reset_aware.year or now.month != reset_aware.month:
        UserRepository(db).update(user, monthly_operations=0, ops_reset_at=now)
        user.monthly_operations = 0


def plan_guard(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """FastAPI dependency — enforces monthly quota for JWT-authenticated requests."""
    if not credentials:
        return  # anonymous — IP rate limiting handles abuse

    payload = decode_access_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        return  # malformed token — let the endpoint decide if auth is required

    user = UserRepository(db).get_by_id(int(payload["sub"]))
    if not user or not user.is_active:
        return

    _maybe_reset_ops(user, db)

    tier = _tier_for_user(user, db)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    monthly_limit: int | None = limits["monthly"]

    if monthly_limit is not None and user.monthly_operations >= monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Monthly operation quota exhausted ({monthly_limit} ops/{tier} tier). "
                "Upgrade your plan at /pricing."
            ),
        )

    UserRepository(db).update(user, monthly_operations=user.monthly_operations + 1)

    # Record a ProcessingJob so dashboard stats reflect actual usage
    try:
        from app.models.job import ProcessingJob
        tool_info = _tool_info_from_path(request.url.path)
        if tool_info:
            slug, name, category = tool_info
            db.add(ProcessingJob(
                user_id=user.id,
                tool_slug=slug,
                tool_name=name,
                category=category,
                filename="file",
                file_size_bytes=0,
                output_size_bytes=None,
                status="success",
            ))
            db.commit()
    except Exception:
        logger.exception("Failed to record processing job — continuing")
