"""Generator tools router — 10 endpoints."""
import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.services import generator_service
from app.utils.file_handler import ALLOWED_IMAGES, cleanup, make_job_dirs, make_zip, read_file, save_bytes, read_upload, validate_file_type
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/generate", tags=["Generator Tools"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


@router.post("/qr")
async def generate_qr(
    request: Request,
    data: str = Form(...),
    size: int = Form(300),
    fill_color: str = Form("black"),
    back_color: str = Form("white"),
):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        output_path = f"{out}/qrcode.png"
        generator_service.generate_qr_code(data, output_path, size, fill_color, back_color)
        img_data = read_file(output_path)
        return Response(content=img_data, media_type="image/png",
                        headers={"Content-Disposition": 'attachment; filename="qrcode.png"'})
    finally:
        cleanup(up, out)


@router.post("/barcode")
async def generate_barcode(
    request: Request,
    data: str = Form(...),
    barcode_type: str = Form("code128"),
):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        output_path = f"{out}/barcode.png"
        generator_service.generate_barcode(data, output_path, barcode_type)
        img_data = read_file(output_path)
        return Response(content=img_data, media_type="image/png",
                        headers={"Content-Disposition": 'attachment; filename="barcode.png"'})
    finally:
        cleanup(up, out)


@router.post("/invoice")
async def generate_invoice(request: Request, data_json: str = Form(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        data = json.loads(data_json)
        output_path = f"{out}/invoice.pdf"
        generator_service.generate_invoice(data, output_path)
        pdf_data = read_file(output_path)
        return Response(content=pdf_data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="invoice.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/resume")
async def generate_resume(request: Request, data_json: str = Form(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        data = json.loads(data_json)
        output_path = f"{out}/resume.pdf"
        generator_service.generate_resume(data, output_path)
        pdf_data = read_file(output_path)
        return Response(content=pdf_data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="resume.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/certificate")
async def generate_certificate(request: Request, data_json: str = Form(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        data = json.loads(data_json)
        output_path = f"{out}/certificate.pdf"
        generator_service.generate_certificate(data, output_path)
        pdf_data = read_file(output_path)
        return Response(content=pdf_data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="certificate.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/color-convert")
async def color_convert(request: Request, value: str = Form(...), source_format: str = Form("hex")):
    _rl(request)
    return generator_service.convert_color(value, source_format)


@router.post("/lorem-ipsum")
async def lorem_ipsum(
    request: Request,
    count: int = Form(5),
    unit: str = Form("sentences"),
):
    _rl(request)
    text = generator_service.generate_lorem_ipsum(count, unit)
    return {"text": text, "count": count, "unit": unit}


@router.post("/file-hash")
async def file_hash(request: Request, file: UploadFile = File(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, file.filename or "file")
        return generator_service.compute_file_hash(input_path)
    finally:
        cleanup(up, out)


# ---------------------------------------------------------------------------
# Favicon generator
# ---------------------------------------------------------------------------

@router.post("/favicon/from-text")
async def favicon_from_text(
    request: Request,
    text: str = Form(..., max_length=4, description="1–4 characters or an emoji"),
    bg_color: str = Form("#4F46E5", description="Background hex color e.g. #4F46E5"),
    text_color: str = Form("#FFFFFF", description="Text/icon hex color e.g. #FFFFFF"),
    shape: str = Form("square", description="square | circle | rounded"),
):
    """Generate a full favicon pack from text or emoji.

    Returns a ZIP containing:
    - `favicon.ico` (16×16, 32×32, 48×48 embedded)
    - `favicon-16x16.png` … `favicon-512x512.png`
    - `site.webmanifest`
    """
    _rl(request)
    if shape not in ("square", "circle", "rounded"):
        raise HTTPException(status_code=422, detail="shape must be square, circle, or rounded")
    _, up, out = make_job_dirs()
    try:
        paths = generator_service.generate_favicon_from_text(
            text=text,
            bg_color=bg_color,
            text_color=text_color,
            shape=shape,
            output_dir=out,
        )
        zip_path = f"{up}/favicon.zip"
        make_zip(paths, zip_path)
        data = read_file(zip_path)
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="favicon.zip"'},
        )
    finally:
        cleanup(up, out)


@router.post("/favicon/from-image")
async def favicon_from_image(
    request: Request,
    file: UploadFile = File(..., description="Source image (PNG, JPG, WebP, etc.)"),
):
    """Generate a full favicon pack from an uploaded image.

    The image is center-cropped to a square, then exported at every standard
    favicon size.  Returns a ZIP containing the same files as `/favicon/from-text`.
    """
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, file.filename or "source.png")
        paths = generator_service.generate_favicon_from_image(
            input_path=input_path,
            output_dir=out,
        )
        zip_path = f"{up}/favicon.zip"
        make_zip(paths, zip_path)
        data = read_file(zip_path)
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="favicon.zip"'},
        )
    finally:
        cleanup(up, out)
