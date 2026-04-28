"""Utility tools router — 6 endpoints."""
import difflib
import zipfile
import io

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.utils.file_handler import (
    ALLOWED_ALL, cleanup, make_job_dirs, make_zip, read_file, save_bytes, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

from app.core.plan_guard import plan_guard

router = APIRouter(prefix="/utility", tags=["Utility Tools"], dependencies=[Depends(plan_guard)])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


@router.post("/create-zip")
async def create_zip(request: Request, files: list[UploadFile] = File(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            content = await read_upload(f)
            ext = (f.filename or "file").rsplit(".", 1)[-1].lower()
            paths.append(save_bytes(content, up, f.filename or f"file_{i}.{ext}"))
        zip_path = f"{out}/archive.zip"
        make_zip(paths, zip_path)
        return Response(content=read_file(zip_path), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="archive.zip"'})
    finally:
        cleanup(up, out)


@router.post("/extract-zip")
async def extract_zip(request: Request, file: UploadFile = File(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "archive.zip")
        with zipfile.ZipFile(input_path, "r") as zf:
            zf.extractall(out)
        import os
        extracted = [os.path.join(out, f) for f in os.listdir(out)]
        zip_path = f"{up}/extracted.zip"
        make_zip(extracted, zip_path)
        return Response(content=read_file(zip_path), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="extracted.zip"'})
    finally:
        cleanup(up, out)


@router.post("/file-size")
async def file_size(request: Request, file: UploadFile = File(...)):
    _rl(request)
    content = await read_upload(file)
    size_bytes = len(content)
    return {
        "filename": file.filename,
        "bytes": size_bytes,
        "kb": round(size_bytes / 1024, 2),
        "mb": round(size_bytes / 1024 / 1024, 4),
    }


@router.post("/text-diff")
async def text_diff(request: Request, text_a: str = Form(...), text_b: str = Form(...)):
    _rl(request)
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    diff = list(difflib.unified_diff(lines_a, lines_b, fromfile="text_a", tofile="text_b"))
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return {
        "diff": "".join(diff),
        "lines_added": added,
        "lines_removed": removed,
        "is_identical": text_a == text_b,
    }


@router.post("/word-counter")
async def word_counter(request: Request, file: UploadFile = File(None), text: str = Form("")):
    _rl(request)
    if file:
        content = await read_upload(file)
        try:
            raw = content.decode("utf-8")
        except UnicodeDecodeError:
            raw = content.decode("latin-1")
    else:
        raw = text
    words = raw.split()
    sentences = [s.strip() for s in raw.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    return {
        "characters": len(raw),
        "characters_no_spaces": len(raw.replace(" ", "")),
        "words": len(words),
        "sentences": len(sentences),
        "paragraphs": len([p for p in raw.split("\n\n") if p.strip()]),
    }


@router.post("/case-convert")
async def case_convert(request: Request, text: str = Form(...), target_case: str = Form(...)):
    _rl(request)
    cases = {
        "upper": text.upper,
        "lower": text.lower,
        "title": text.title,
        "sentence": lambda: text[0].upper() + text[1:].lower() if text else "",
        "camel": lambda: "".join(w.capitalize() for w in text.split()),
        "snake": lambda: "_".join(text.lower().split()),
        "kebab": lambda: "-".join(text.lower().split()),
    }
    if target_case not in cases:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown case: {target_case}. Options: {list(cases.keys())}")
    converted = cases[target_case]()
    return {"original": text, "converted": converted, "case": target_case}
