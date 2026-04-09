"""Security tools router — 5 endpoints."""
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.services import security_service
from app.utils.file_handler import (
    ALLOWED_PDF, cleanup, make_job_dirs, read_file,
    save_bytes, validate_file_type, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/security", tags=["Security Tools"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/encrypt")
async def encrypt_pdf(
    request: Request,
    file: UploadFile = File(...),
    user_password: str = Form(...),
    owner_password: str = Form(""),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/encrypted.pdf"
        security_service.encrypt_pdf(input_path, output_path, user_password, owner_password)
        data = read_file(output_path)
        return _pdf_response(data, "encrypted.pdf")
    finally:
        cleanup(up, out)


@router.post("/decrypt")
async def decrypt_pdf(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/decrypted.pdf"
        security_service.decrypt_pdf(input_path, output_path, password)
        data = read_file(output_path)
        return _pdf_response(data, "decrypted.pdf")
    finally:
        cleanup(up, out)


@router.post("/permissions")
async def pdf_permissions(
    request: Request,
    file: UploadFile = File(...),
    owner_password: str = Form(...),
    allow_printing: bool = Form(True),
    allow_copying: bool = Form(False),
    allow_modifying: bool = Form(False),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/protected.pdf"
        security_service.set_permissions(input_path, output_path, owner_password,
                                         allow_printing, allow_copying, allow_modifying)
        data = read_file(output_path)
        return _pdf_response(data, "protected.pdf")
    finally:
        cleanup(up, out)


@router.post("/auto-redact")
async def auto_redact(
    request: Request,
    file: UploadFile = File(...),
    patterns: str = Form("email,phone"),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    pattern_list = [p.strip() for p in patterns.split(",")]
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/redacted.pdf"
        security_service.auto_redact_pii(input_path, output_path, pattern_list)
        data = read_file(output_path)
        return _pdf_response(data, "redacted.pdf")
    finally:
        cleanup(up, out)


@router.post("/sanitize")
async def sanitize_pdf(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/sanitized.pdf"
        security_service.sanitize_pdf(input_path, output_path)
        data = read_file(output_path)
        return _pdf_response(data, "sanitized.pdf")
    finally:
        cleanup(up, out)
