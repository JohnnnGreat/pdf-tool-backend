"""Document tools router — 16 endpoints (Word, Excel, PowerPoint)."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.services import document_service
from app.utils.file_handler import (
    ALLOWED_DOCS, ALLOWED_IMAGES, ALLOWED_PDF, ALLOWED_SHEETS, ALLOWED_SLIDES,
    cleanup, make_job_dirs, make_zip, read_file, save_bytes, validate_file_type, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

from app.core.plan_guard import plan_guard

router = APIRouter(prefix="/document", tags=["Document Tools"], dependencies=[Depends(plan_guard)])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


def _file_response(data: bytes, filename: str, media_type: str) -> Response:
    return Response(content=data, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


DOCX_MT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

@router.post("/create-docx")
async def create_docx(request: Request):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        data = await request.json()
        output_path = f"{out}/document.docx"
        document_service.create_docx(data, output_path)
        return _file_response(read_file(output_path), "document.docx", DOCX_MT)
    finally:
        cleanup(up, out)


@router.post("/find-replace-docx")
async def find_replace_docx(request: Request, file: UploadFile = File(...),
                             find: str = Form(...), replace: str = Form(...)):
    _rl(request)
    validate_file_type(file, [".docx"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.docx")
        output_path = f"{out}/output.docx"
        count = document_service.find_replace_docx(input_path, output_path, find, replace)
        return _file_response(read_file(output_path), "output.docx", DOCX_MT)
    finally:
        cleanup(up, out)


@router.post("/docx-to-md")
async def docx_to_md(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".docx"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.docx")
        output_path = f"{out}/output.md"
        document_service.docx_to_markdown(input_path, output_path)
        return _file_response(read_file(output_path), "output.md", "text/markdown")
    finally:
        cleanup(up, out)


@router.post("/merge-docx")
async def merge_docx(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 .docx files")
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, [".docx"])
            content = await read_upload(f)
            paths.append(save_bytes(content, up, f"doc_{i}.docx"))
        output_path = f"{out}/merged.docx"
        document_service.merge_docx_files(paths, output_path)
        return _file_response(read_file(output_path), "merged.docx", DOCX_MT)
    finally:
        cleanup(up, out)


@router.post("/compare-docx")
async def compare_docx(request: Request, file_a: UploadFile = File(...), file_b: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file_a, [".docx"])
    validate_file_type(file_b, [".docx"])
    _, up, out = make_job_dirs()
    try:
        ca = await read_upload(file_a)
        cb = await read_upload(file_b)
        path_a = save_bytes(ca, up, "a.docx")
        path_b = save_bytes(cb, up, "b.docx")
        return document_service.compare_docx_files(path_a, path_b)
    finally:
        cleanup(up, out)


@router.post("/extract-text")
async def extract_text(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_PDF + ALLOWED_DOCS + ALLOWED_SLIDES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".pdf").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        text = document_service.extract_text_from_file(input_path)
        return {"text": text}
    finally:
        cleanup(up, out)


@router.post("/mail-merge")
async def mail_merge(request: Request, template: UploadFile = File(...), data_csv: UploadFile = File(...)):
    _rl(request)
    validate_file_type(template, [".docx"])
    validate_file_type(data_csv, [".csv"])
    _, up, out = make_job_dirs()
    try:
        t_content = await read_upload(template)
        c_content = await read_upload(data_csv)
        template_path = save_bytes(t_content, up, "template.docx")
        csv_path = save_bytes(c_content, up, "data.csv")
        paths = document_service.mail_merge(template_path, csv_path, out)
        zip_path = f"{up}/mail_merge.zip"
        make_zip(paths, zip_path)
        return Response(content=read_file(zip_path), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="mail_merge.zip"'})
    finally:
        cleanup(up, out)


# ---------------------------------------------------------------------------
# PowerPoint
# ---------------------------------------------------------------------------

@router.post("/merge-pptx")
async def merge_pptx(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 .pptx files")
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, [".pptx"])
            content = await read_upload(f)
            paths.append(save_bytes(content, up, f"pptx_{i}.pptx"))
        output_path = f"{out}/merged.pptx"
        document_service.merge_pptx_files(paths, output_path)
        return _file_response(read_file(output_path), "merged.pptx", PPTX_MT)
    finally:
        cleanup(up, out)


@router.post("/pptx-to-images")
async def pptx_to_images(request: Request, file: UploadFile = File(...),
                          fmt: str = Form("png"), dpi: int = Form(150)):
    _rl(request)
    validate_file_type(file, [".pptx"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pptx")
        paths = document_service.pptx_to_images(input_path, out, fmt, dpi)
        zip_path = f"{up}/slides.zip"
        make_zip(paths, zip_path)
        return Response(content=read_file(zip_path), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="slides.zip"'})
    finally:
        cleanup(up, out)


@router.post("/extract-notes")
async def extract_notes(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".pptx"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.pptx")
        return {"notes": document_service.extract_slide_notes(input_path)}
    finally:
        cleanup(up, out)


@router.post("/images-to-pptx")
async def images_to_pptx(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, ALLOWED_IMAGES)
            content = await read_upload(f)
            ext = (f.filename or ".png").rsplit(".", 1)[-1].lower()
            paths.append(save_bytes(content, up, f"img_{i}.{ext}"))
        output_path = f"{out}/presentation.pptx"
        document_service.images_to_pptx(paths, output_path)
        return _file_response(read_file(output_path), "presentation.pptx", PPTX_MT)
    finally:
        cleanup(up, out)


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

@router.post("/merge-excel")
async def merge_excel(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 Excel files")
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, [".xlsx", ".xls"])
            content = await read_upload(f)
            paths.append(save_bytes(content, up, f"excel_{i}.xlsx"))
        output_path = f"{out}/merged.xlsx"
        document_service.merge_excel_files(paths, output_path)
        return _file_response(read_file(output_path), "merged.xlsx", XLSX_MT)
    finally:
        cleanup(up, out)


@router.post("/split-excel")
async def split_excel(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".xlsx"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.xlsx")
        paths = document_service.split_excel_sheets(input_path, out)
        zip_path = f"{up}/sheets.zip"
        make_zip(paths, zip_path)
        return Response(content=read_file(zip_path), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="sheets.zip"'})
    finally:
        cleanup(up, out)


@router.post("/clean-excel")
async def clean_excel(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".xlsx"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.xlsx")
        output_path = f"{out}/cleaned.xlsx"
        result = document_service.clean_excel(input_path, output_path)
        return _file_response(read_file(output_path), "cleaned.xlsx", XLSX_MT)
    finally:
        cleanup(up, out)


@router.post("/json-to-excel")
async def json_to_excel(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".json"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.json")
        output_path = f"{out}/output.xlsx"
        document_service.json_to_excel(input_path, output_path)
        return _file_response(read_file(output_path), "output.xlsx", XLSX_MT)
    finally:
        cleanup(up, out)


@router.post("/excel-to-json")
async def excel_to_json(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, [".xlsx", ".xls"])
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.xlsx")
        output_path = f"{out}/output.json"
        document_service.excel_to_json(input_path, output_path)
        return _file_response(read_file(output_path), "output.json", "application/json")
    finally:
        cleanup(up, out)
