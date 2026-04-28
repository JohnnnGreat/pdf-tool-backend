import os
import re
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


async def stream_upload_to_disk(file: UploadFile, directory: str, filename: str) -> str:
    """Stream upload directly to disk in 64 KB chunks to avoid loading the entire file into RAM.

    Raises HTTP 413 if the file exceeds MAX_FILE_SIZE_MB without reading it all first.
    """
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    path = os.path.join(directory, filename)
    total = 0
    try:
        with open(path, "wb") as f:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds {settings.MAX_FILE_SIZE_MB}MB limit",
                    )
                f.write(chunk)
    except HTTPException:
        if os.path.exists(path):
            os.unlink(path)
        raise
    return path


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


def output_name(original: str | None, suffix: str, ext: str | None = None) -> str:
    """Build a descriptive download filename: <original-stem>-<suffix>.<ext>"""
    basename = os.path.basename(original or "")
    stem = os.path.splitext(basename)[0].strip()
    orig_ext = os.path.splitext(basename)[1] if basename else ""
    final_ext = f".{ext.lstrip('.')}" if ext else (orig_ext or ".bin")
    clean_stem = re.sub(r"[^\w\-]", "-", stem).strip("-") or suffix
    return f"{clean_stem}-{suffix}{final_ext}"
