"""Signature & stamp tools router — 4 endpoints."""
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.services import signature_service
from app.utils.file_handler import (
    ALLOWED_IMAGES, ALLOWED_PDF, cleanup, make_job_dirs, read_file,
    save_bytes, validate_file_type, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/signature", tags=["Signature & Stamp Tools"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/add-signature")
async def add_signature(
    request: Request,
    file: UploadFile = File(...),
    signature: UploadFile = File(...),
    page_number: int = Form(1),
    x: float = Form(50), y: float = Form(50),
    width: float = Form(150), height: float = Form(60),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    validate_file_type(signature, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        pdf_content = await read_upload(file)
        sig_content = await read_upload(signature)
        input_path = save_bytes(pdf_content, up, "input.pdf")
        sig_ext = (signature.filename or ".png").rsplit(".", 1)[-1].lower()
        sig_path = save_bytes(sig_content, up, f"signature.{sig_ext}")
        output_path = f"{out}/signed.pdf"
        signature_service.add_signature(input_path, output_path, sig_path, page_number, x, y, width, height)
        data = read_file(output_path)
        return _pdf_response(data, "signed.pdf")
    finally:
        cleanup(up, out)


@router.post("/add-stamp")
async def add_stamp(
    request: Request,
    file: UploadFile = File(...),
    text: str = Form(...),
    page_number: int = Form(1),
    x: float = Form(100), y: float = Form(100),
    font_size: int = Form(36),
    rotate: int = Form(0),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/stamped.pdf"
        signature_service.add_text_stamp(input_path, output_path, text, page_number, x, y, font_size, rotate=rotate)
        data = read_file(output_path)
        return _pdf_response(data, "stamped.pdf")
    finally:
        cleanup(up, out)


@router.post("/date-stamp")
async def date_stamp(
    request: Request,
    file: UploadFile = File(...),
    date: str = Form(...),
    page_number: int = Form(1),
    x: float = Form(400), y: float = Form(750),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/date_stamped.pdf"
        signature_service.add_date_stamp(input_path, output_path, date, page_number, x, y)
        data = read_file(output_path)
        return _pdf_response(data, "date_stamped.pdf")
    finally:
        cleanup(up, out)


@router.post("/digital-sign")
async def digital_sign(
    request: Request,
    file: UploadFile = File(...),
    certificate: UploadFile = File(...),
    cert_password: str = Form(...),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    validate_file_type(certificate, [".p12", ".pfx"])
    _, up, out = make_job_dirs()
    try:
        pdf_content = await read_upload(file)
        cert_content = await read_upload(certificate)
        input_path = save_bytes(pdf_content, up, "input.pdf")
        cert_path = save_bytes(cert_content, up, "cert.p12")
        output_path = f"{out}/digitally_signed.pdf"
        signature_service.digital_sign(input_path, output_path, cert_path, cert_password)
        data = read_file(output_path)
        return _pdf_response(data, "digitally_signed.pdf")
    finally:
        cleanup(up, out)
