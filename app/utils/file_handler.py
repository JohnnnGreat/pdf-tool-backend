import os
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException

from app.core.config import settings

ALLOWED_PDF = [".pdf"]
ALLOWED_IMAGES = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".ico"]
ALLOWED_DOCS = [".doc", ".docx", ".odt", ".rtf", ".txt"]
ALLOWED_SHEETS = [".xls", ".xlsx", ".csv", ".tsv", ".ods"]
ALLOWED_SLIDES = [".ppt", ".pptx", ".odp"]
ALLOWED_ARCHIVES = [".zip", ".rar", ".7z", ".tar", ".gz"]
ALLOWED_ALL = ALLOWED_PDF + ALLOWED_IMAGES + ALLOWED_DOCS + ALLOWED_SHEETS + ALLOWED_SLIDES + ALLOWED_ARCHIVES


def validate_file_type(file: UploadFile, allowed: list[str]) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(allowed)}",
        )


def validate_file_size(content: bytes) -> None:
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.MAX_FILE_SIZE_MB}MB limit",
        )


async def read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    validate_file_size(content)
    return content


def make_job_dirs() -> tuple[str, str, str]:
    job_id = str(uuid.uuid4())
    upload_dir = os.path.join(settings.UPLOAD_DIR, job_id)
    output_dir = os.path.join(settings.OUTPUT_DIR, job_id)
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    return job_id, upload_dir, output_dir


def save_bytes(content: bytes, directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


def read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def cleanup(*dirs: str) -> None:
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)


def make_zip(file_paths: list[str], zip_path: str) -> None:
    import zipfile
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            zf.write(fp, os.path.basename(fp))
