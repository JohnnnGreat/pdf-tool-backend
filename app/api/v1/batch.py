"""Batch processing router — 4 endpoints."""
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.services import batch_service
from app.utils.file_handler import (
    ALLOWED_ALL, cleanup, make_job_dirs, make_zip, read_file, save_bytes, validate_file_type, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/batch", tags=["Batch Tools"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


def _zip_response(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/convert")
async def batch_convert(request: Request, files: list[UploadFile] = File(...),
                        target_format: str = Form(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, ALLOWED_ALL)
            content = await read_upload(f)
            ext = (f.filename or ".pdf").rsplit(".", 1)[-1].lower()
            paths.append(save_bytes(content, up, f"file_{i}.{ext}"))
        results = batch_service.batch_convert(paths, out, target_format)
        valid = [p for p in results if not p.startswith("ERROR:")]
        zip_path = f"{up}/converted.zip"
        make_zip(valid, zip_path)
        return _zip_response(read_file(zip_path), "converted.zip")
    finally:
        cleanup(up, out)


@router.post("/compress")
async def batch_compress(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, ALLOWED_ALL)
            content = await read_upload(f)
            ext = (f.filename or ".pdf").rsplit(".", 1)[-1].lower()
            paths.append(save_bytes(content, up, f"file_{i}.{ext}"))
        results = batch_service.batch_compress(paths, out)
        zip_path = f"{up}/compressed.zip"
        make_zip(results, zip_path)
        return _zip_response(read_file(zip_path), "compressed.zip")
    finally:
        cleanup(up, out)


@router.post("/rename")
async def batch_rename(request: Request, files: list[UploadFile] = File(...),
                       pattern: str = Form("{name}_{index}{ext}")):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            content = await read_upload(f)
            ext = (f.filename or ".pdf").rsplit(".", 1)[-1].lower()
            paths.append(save_bytes(content, up, f"file_{i}.{ext}"))
        results = batch_service.batch_rename(paths, out, pattern)
        zip_path = f"{up}/renamed.zip"
        make_zip(results, zip_path)
        return _zip_response(read_file(zip_path), "renamed.zip")
    finally:
        cleanup(up, out)


@router.post("/watermark")
async def batch_watermark(request: Request, files: list[UploadFile] = File(...),
                          text: str = Form(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            content = await read_upload(f)
            paths.append(save_bytes(content, up, f"file_{i}.pdf"))
        results = batch_service.batch_watermark(paths, out, text)
        zip_path = f"{up}/watermarked.zip"
        make_zip(results, zip_path)
        return _zip_response(read_file(zip_path), "watermarked.zip")
    finally:
        cleanup(up, out)
