"""PDF tools router — 22 endpoints."""
import json
from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.services import pdf_service
from app.utils.file_handler import (
    ALLOWED_PDF, cleanup, make_job_dirs, make_zip, read_file, save_bytes, validate_file_type, read_upload
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/pdf", tags=["PDF Tools"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


# ---------------------------------------------------------------------------
# Merge / Split
# ---------------------------------------------------------------------------

@router.post("/merge")
async def merge(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 PDF files to merge")
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, ALLOWED_PDF)
            content = await read_upload(f)
            paths.append(save_bytes(content, up, f"input_{i}.pdf"))
        output_path = f"{out}/merged.pdf"
        pdf_service.merge_pdfs(paths, output_path)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="merged.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/split")
async def split(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        pages = pdf_service.split_pdf(input_path, out)
        zip_path = f"{up}/pages.zip"
        make_zip(pages, zip_path)
        data = read_file(zip_path)
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="pages.zip"'})
    finally:
        cleanup(up, out)


@router.post("/split-range")
async def split_range(request: Request, file: UploadFile = File(...), ranges: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        pages = pdf_service.split_pdf_ranges(input_path, out, ranges)
        zip_path = f"{up}/ranges.zip"
        make_zip(pages, zip_path)
        data = read_file(zip_path)
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="ranges.zip"'})
    finally:
        cleanup(up, out)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

@router.post("/compress")
async def compress(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/compressed.pdf"
        pdf_service.compress_pdf(input_path, output_path)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="compressed.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/rotate")
async def rotate(request: Request, file: UploadFile = File(...), angle: int = Form(90), pages: Optional[str] = Form(None)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    if angle not in (90, 180, 270):
        raise HTTPException(status_code=422, detail="Angle must be 90, 180, or 270")
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/rotated.pdf"
        pdf_service.rotate_pdf(input_path, output_path, angle, pages)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="rotated.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/delete-pages")
async def delete_pages(request: Request, file: UploadFile = File(...), page_numbers: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/output.pdf"
        pdf_service.delete_pages(input_path, output_path, page_numbers)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="output.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/reorder")
async def reorder(request: Request, file: UploadFile = File(...), order: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/reordered.pdf"
        pdf_service.reorder_pages(input_path, output_path, order)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="reordered.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/extract-pages")
async def extract_pages(request: Request, file: UploadFile = File(...), page_numbers: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/extracted.pdf"
        pdf_service.extract_pages(input_path, output_path, page_numbers)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="extracted.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/page-numbers")
async def page_numbers(
    request: Request, file: UploadFile = File(...),
    position: str = Form("bottom-center"), font_size: int = Form(12), start_number: int = Form(1),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/numbered.pdf"
        pdf_service.add_page_numbers(input_path, output_path, position, font_size, start_number)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="numbered.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/watermark")
async def watermark(
    request: Request, file: UploadFile = File(...), text: str = Form(...),
    opacity: float = Form(0.3), font_size: int = Form(50),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/watermarked.pdf"
        pdf_service.add_text_watermark(input_path, output_path, text, opacity, font_size)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="watermarked.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/header-footer")
async def header_footer(
    request: Request, file: UploadFile = File(...),
    header: str = Form(""), footer: str = Form(""), font_size: int = Form(10),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/output.pdf"
        pdf_service.add_header_footer(input_path, output_path, header, footer, font_size)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="output.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/crop")
async def crop(
    request: Request, file: UploadFile = File(...),
    x: float = Form(0), y: float = Form(0), width: float = Form(400), height: float = Form(600),
):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/cropped.pdf"
        pdf_service.crop_pdf(input_path, output_path, x, y, width, height)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="cropped.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/flatten")
async def flatten(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/flattened.pdf"
        pdf_service.flatten_pdf(input_path, output_path)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="flattened.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/repair")
async def repair(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/repaired.pdf"
        pdf_service.repair_pdf(input_path, output_path)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="repaired.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/metadata")
async def metadata(request: Request, file: UploadFile = File(...), update: Optional[str] = Form(None)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        if update:
            meta_dict = json.loads(update)
            output_path = f"{out}/output.pdf"
            pdf_service.set_metadata(input_path, output_path, meta_dict)
            data = read_file(output_path)
            return Response(content=data, media_type="application/pdf",
                            headers={"Content-Disposition": 'attachment; filename="output.pdf"'})
        return pdf_service.get_pdf_info(input_path)
    finally:
        cleanup(up, out)


@router.post("/redact")
async def redact(request: Request, file: UploadFile = File(...), patterns: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    pattern_list = [p.strip() for p in patterns.split(",")]
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/redacted.pdf"
        pdf_service.redact_text(input_path, output_path, pattern_list)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="redacted.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/compare")
async def compare(request: Request, file_a: UploadFile = File(...), file_b: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file_a, ALLOWED_PDF)
    validate_file_type(file_b, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content_a = await read_upload(file_a)
        content_b = await read_upload(file_b)
        path_a = save_bytes(content_a, up, "a.pdf")
        path_b = save_bytes(content_b, up, "b.pdf")
        return pdf_service.compare_pdfs(path_a, path_b)
    finally:
        cleanup(up, out)


@router.post("/pdf-to-pdfa")
async def pdf_to_pdfa(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/pdfa.pdf"
        pdf_service.convert_to_pdfa(input_path, output_path)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="pdfa.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/bookmarks")
async def bookmarks(request: Request, file: UploadFile = File(...), bookmarks_json: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    bm_list = json.loads(bookmarks_json)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/bookmarked.pdf"
        pdf_service.add_bookmarks(input_path, output_path, bm_list)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="bookmarked.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/overlay")
async def overlay(request: Request, base: UploadFile = File(...), overlay_file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(base, ALLOWED_PDF)
    validate_file_type(overlay_file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        base_content = await read_upload(base)
        overlay_content = await read_upload(overlay_file)
        base_path = save_bytes(base_content, up, "base.pdf")
        overlay_path = save_bytes(overlay_content, up, "overlay.pdf")
        output_path = f"{out}/overlaid.pdf"
        pdf_service.overlay_pdfs(base_path, overlay_path, output_path)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="overlaid.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/fill-form")
async def fill_form(request: Request, file: UploadFile = File(...), fields_json: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    field_values = json.loads(fields_json)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/filled.pdf"
        pdf_service.fill_form(input_path, output_path, field_values)
        data = read_file(output_path)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="filled.pdf"'})
    finally:
        cleanup(up, out)


@router.post("/pdf-info")
async def pdf_info(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        return pdf_service.get_pdf_info(input_path)
    finally:
        cleanup(up, out)
