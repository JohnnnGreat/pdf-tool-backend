from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

from app.core.plan_guard import plan_guard

router  = APIRouter(prefix="/ai", tags=["AI"], dependencies=[Depends(plan_guard)])
_svc    = AIService()

_ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg", "image/png", "image/webp", "image/tiff",
}


def _check_file(file: UploadFile) -> None:
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Upload a PDF or image.",
        )


# ── Chat (streaming SSE) ───────────────────────────────────────────────────

@router.post("/chat")
async def ai_chat(
    file: UploadFile     = File(...),
    message: str         = Form(...),
    history: str         = Form(default="[]"),
    _user: User          = Depends(get_current_user),
):
    _check_file(file)
    file_bytes = await file.read()

    try:
        parsed_history = json.loads(history)
    except Exception as exc:
        logger.warning("Invalid chat history JSON — using empty history: %s", exc)
        parsed_history = []

    return StreamingResponse(
        _svc.chat_stream(file_bytes, file.content_type, message, parsed_history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Summarize ──────────────────────────────────────────────────────────────

class SummarizeResponse(BaseModel):
    summary: str
    format:  str
    length:  str


@router.post("/summarize", response_model=SummarizeResponse)
async def ai_summarize(
    file:        UploadFile = File(...),
    format_type: str        = Form(default="bullets"),
    length:      str        = Form(default="standard"),
    _user: User             = Depends(get_current_user),
):
    _check_file(file)
    file_bytes = await file.read()
    summary    = await _svc.summarize(file_bytes, file.content_type, format_type, length)
    return SummarizeResponse(summary=summary, format=format_type, length=length)


# ── Extract ────────────────────────────────────────────────────────────────

class ExtractResponse(BaseModel):
    data:     dict | None
    raw:      str
    doc_type: str


@router.post("/extract", response_model=ExtractResponse)
async def ai_extract(
    file:     UploadFile = File(...),
    doc_type: str        = Form(default="custom"),
    _user: User          = Depends(get_current_user),
):
    _check_file(file)
    file_bytes = await file.read()
    result     = await _svc.extract(file_bytes, file.content_type, doc_type)
    return ExtractResponse(doc_type=doc_type, **result)


# ── OCR Cleanup (streaming SSE) ────────────────────────────────────────────

@router.post("/ocr-cleanup")
async def ai_ocr_cleanup(
    text:  str   = Form(...),
    _user: User  = Depends(get_current_user),
):
    if not text.strip():
        raise HTTPException(status_code=422, detail="text field is required.")

    return StreamingResponse(
        _svc.cleanup_ocr_stream(text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
