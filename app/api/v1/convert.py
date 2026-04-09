"""Conversion tools router — 18 endpoints."""
import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.services import convert_service
from app.utils.file_handler import (
    ALLOWED_DOCS, ALLOWED_IMAGES, ALLOWED_PDF, ALLOWED_SHEETS, ALLOWED_SLIDES,
    cleanup, make_job_dirs, make_zip, read_file, save_bytes, validate_file_type, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/convert", tags=["Conversion Tools"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _zip_response(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _file_response(data: bytes, filename: str, media_type: str) -> Response:
    return Response(content=data, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/pdf-to-word")
async def pdf_to_word(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/output.docx"
        convert_service.pdf_to_word(input_path, output_path)
        data = read_file(output_path)
        return _file_response(data, "output.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    finally:
        cleanup(up, out)


@router.post("/word-to-pdf")
async def word_to_pdf(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".doc", ".docx", ".odt", ".rtf"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, file.filename or "input.docx")
        out_path = convert_service.word_to_pdf(input_path, out)
        data = read_file(out_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/pdf-to-excel")
async def pdf_to_excel(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/output.xlsx"
        convert_service.pdf_to_excel(input_path, output_path)
        data = read_file(output_path)
        return _file_response(data, "output.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    finally:
        cleanup(up, out)


@router.post("/excel-to-pdf")
async def excel_to_pdf(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".xls", ".xlsx", ".ods"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, file.filename or "input.xlsx")
        out_path = convert_service.excel_to_pdf(input_path, out)
        data = read_file(out_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/pdf-to-pptx")
async def pdf_to_pptx(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        out_path = convert_service.pdf_to_pptx(input_path, out)
        data = read_file(out_path)
        return _file_response(data, "output.pptx",
                               "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    finally:
        cleanup(up, out)


@router.post("/pptx-to-pdf")
async def pptx_to_pdf(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".ppt", ".pptx", ".odp"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, file.filename or "input.pptx")
        out_path = convert_service.pptx_to_pdf(input_path, out)
        data = read_file(out_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/pdf-to-image")
async def pdf_to_image(request: Request, file: UploadFile = File(...),
                       fmt: str = Form("png"), dpi: int = Form(150)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    if fmt not in ("png", "jpg", "jpeg"):
        raise HTTPException(status_code=400, detail="fmt must be png, jpg, or jpeg")
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        pages = convert_service.pdf_to_images(input_path, out, fmt, dpi)
        zip_path = f"{up}/pages.zip"
        make_zip(pages, zip_path)
        data = read_file(zip_path)
        return _zip_response(data, "pages.zip")
    finally:
        cleanup(up, out)


@router.post("/image-to-pdf")
async def image_to_pdf(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, ALLOWED_IMAGES)
            content = await read_upload(f)
            paths.append(save_bytes(content, up, f"img_{i}{f.filename[-4:]}"))
        output_path = f"{out}/output.pdf"
        convert_service.images_to_pdf(paths, output_path)
        data = read_file(output_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/html-to-pdf")
async def html_to_pdf(request: Request, html: str = Form(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        output_path = f"{out}/output.pdf"
        convert_service.html_to_pdf(html, output_path)
        data = read_file(output_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/pdf-to-html")
async def pdf_to_html(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pdf")
        output_path = f"{out}/output.html"
        convert_service.pdf_to_html(input_path, output_path)
        data = read_file(output_path)
        return _file_response(data, "output.html", "text/html")
    finally:
        cleanup(up, out)


@router.post("/md-to-pdf")
async def md_to_pdf(request: Request, file: Optional[UploadFile] = File(None), text: str = Form("")):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        md_text = text
        if file:
            validate_file_type(file, [".md", ".txt"])
            content = await read_upload(file)
            md_text = content.decode("utf-8")
        output_path = f"{out}/output.pdf"
        convert_service.markdown_to_pdf(md_text, output_path)
        data = read_file(output_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/csv-to-pdf")
async def csv_to_pdf(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".csv"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.csv")
        output_path = f"{out}/output.pdf"
        convert_service.csv_to_pdf(input_path, output_path)
        data = read_file(output_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/csv-to-excel")
async def csv_to_excel(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".csv"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.csv")
        output_path = f"{out}/output.xlsx"
        convert_service.csv_to_excel(input_path, output_path)
        data = read_file(output_path)
        return _file_response(data, "output.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    finally:
        cleanup(up, out)


@router.post("/excel-to-csv")
async def excel_to_csv(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".xlsx", ".xls"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.xlsx")
        output_path = f"{out}/output.csv"
        convert_service.excel_to_csv(input_path, output_path)
        data = read_file(output_path)
        return _file_response(data, "output.csv", "text/csv")
    finally:
        cleanup(up, out)


@router.post("/text-to-pdf")
async def text_to_pdf(request: Request, file: Optional[UploadFile] = File(None),
                      text: str = Form(""), font_size: int = Form(12)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        content_text = text
        if file:
            validate_file_type(file, [".txt"])
            raw = await read_upload(file)
            content_text = raw.decode("utf-8")
        output_path = f"{out}/output.pdf"
        convert_service.text_to_pdf(content_text, output_path, font_size)
        data = read_file(output_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/svg-convert")
async def svg_convert(request: Request, file: UploadFile = File(...), target: str = Form("png")):
    _rl(request)
    validate_file_type(file, [".svg"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.svg")
        output_path = f"{out}/output.{target}"
        convert_service.svg_to_png(input_path, output_path)
        data = read_file(output_path)
        return _file_response(data, f"output.{target}", f"image/{target}")
    finally:
        cleanup(up, out)


@router.post("/epub-to-pdf")
async def epub_to_pdf(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".epub"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.epub")
        out_path = convert_service.epub_to_pdf(input_path, out)
        data = read_file(out_path)
        return _pdf_response(data, "output.pdf")
    finally:
        cleanup(up, out)


@router.post("/json-to-table")
async def json_to_table(request: Request, file: UploadFile = File(...), target: str = Form("csv")):
    _rl(request)
    validate_file_type(file, [".json"])
    if target not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="target must be 'csv' or 'xlsx'")
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.json")
        output_path = f"{out}/output.{target}"
        convert_service.json_to_table(input_path, output_path, target)
        data = read_file(output_path)
        mt = "text/csv" if target == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return _file_response(data, f"output.{target}", mt)
    finally:
        cleanup(up, out)
