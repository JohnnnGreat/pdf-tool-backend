"""OCR tools router — 6 endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.services import ocr_service
from app.utils.file_handler import (
    ALLOWED_IMAGES, ALLOWED_PDF, cleanup, make_job_dirs, read_file,
    save_bytes, validate_file_type, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

from app.core.plan_guard import plan_guard

router = APIRouter(prefix="/ocr", tags=["OCR Tools"], dependencies=[Depends(plan_guard)])

ALLOWED_OCR = ALLOWED_PDF + ALLOWED_IMAGES


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


@router.post("/image")
async def ocr_image(request: Request, file: UploadFile = File(...), lang: Optional[str] = Form(None)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        return ocr_service.ocr_image(input_path, lang)
    finally:
        cleanup(up, out)


@router.post("/pdf")
async def ocr_pdf(request: Request, file: UploadFile = File(...), lang: Optional[str] = Form(None)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/searchable.pdf"
        ocr_service.ocr_pdf_to_searchable(input_path, output_path, lang)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="searchable.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/multilang")
async def ocr_multilang(request: Request, file: UploadFile = File(...), lang: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        return ocr_service.ocr_multilang(input_path, lang)
    finally:
        cleanup(up, out)


@router.post("/table")
async def ocr_table(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_OCR)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/table.csv"
        ocr_service.ocr_table(input_path, output_path)
        data = read_file(output_path)
        return Response(content=data, media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="table.csv"'})
    finally:
        cleanup(up, out)


@router.post("/handwriting")
async def ocr_handwriting(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        return ocr_service.ocr_handwriting(input_path)
    finally:
        cleanup(up, out)


@router.post("/receipt")
async def ocr_receipt(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".jpg").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        return ocr_service.ocr_receipt(input_path)
    finally:
        cleanup(up, out)
