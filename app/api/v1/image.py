"""Image tools router — 14 endpoints."""
import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.services import image_service
from app.utils.file_handler import (
    ALLOWED_IMAGES, cleanup, make_job_dirs, make_zip, read_file, save_bytes,
    validate_file_type, read_upload,
)
from app.utils.rate_limiter import get_client_ip, rate_limiter

router = APIRouter(prefix="/image", tags=["Image Tools"])


def _rl(request: Request):
    rate_limiter.check(get_client_ip(request))


def _img_response(data: bytes, filename: str, ext: str = "png") -> Response:
    mt = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    return Response(content=data, media_type=mt,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/compress")
async def compress_image(request: Request, file: UploadFile = File(...), quality: int = Form(75)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/compressed.{ext}"
        image_service.compress_image(input_path, output_path, quality)
        data = read_file(output_path)
        return _img_response(data, f"compressed.{ext}", ext)
    finally:
        cleanup(up, out)


@router.post("/resize")
async def resize_image(request: Request, file: UploadFile = File(...),
                       width: Optional[int] = Form(None), height: Optional[int] = Form(None),
                       maintain_ratio: bool = Form(True)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/resized.{ext}"
        image_service.resize_image(input_path, output_path, width, height, maintain_ratio)
        data = read_file(output_path)
        return _img_response(data, f"resized.{ext}", ext)
    finally:
        cleanup(up, out)


@router.post("/crop")
async def crop_image(request: Request, file: UploadFile = File(...),
                     x: int = Form(...), y: int = Form(...),
                     width: int = Form(...), height: int = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/cropped.{ext}"
        image_service.crop_image(input_path, output_path, x, y, width, height)
        data = read_file(output_path)
        return _img_response(data, f"cropped.{ext}", ext)
    finally:
        cleanup(up, out)


@router.post("/rotate")
async def rotate_image(request: Request, file: UploadFile = File(...),
                       angle: int = Form(90), flip: Optional[str] = Form(None)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/rotated.{ext}"
        image_service.rotate_image(input_path, output_path, angle, flip)
        data = read_file(output_path)
        return _img_response(data, f"rotated.{ext}", ext)
    finally:
        cleanup(up, out)


@router.post("/convert")
async def convert_image(request: Request, file: UploadFile = File(...), target_format: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        out_ext = target_format.lower().lstrip(".")
        output_path = f"{out}/output.{out_ext}"
        image_service.convert_image_format(input_path, output_path, target_format)
        data = read_file(output_path)
        return _img_response(data, f"output.{out_ext}", out_ext)
    finally:
        cleanup(up, out)


@router.post("/remove-bg")
async def remove_bg(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        input_path = save_bytes(content, up, "input.png")
        output_path = f"{out}/no_bg.png"
        image_service.remove_background(input_path, output_path)
        data = read_file(output_path)
        return _img_response(data, "no_bg.png", "png")
    finally:
        cleanup(up, out)


@router.post("/watermark")
async def image_watermark(request: Request, file: UploadFile = File(...),
                          text: str = Form(...), opacity: int = Form(128)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/watermarked.{ext}"
        image_service.add_image_watermark_text(input_path, output_path, text, opacity)
        data = read_file(output_path)
        return _img_response(data, f"watermarked.{ext}", ext)
    finally:
        cleanup(up, out)


@router.post("/to-base64")
async def image_to_base64(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        return image_service.image_to_base64(input_path)
    finally:
        cleanup(up, out)


@router.post("/from-base64")
async def base64_to_image(request: Request, base64_string: str = Form(...),
                          format: str = Form("png")):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        output_path = f"{out}/output.{format}"
        image_service.base64_to_image(base64_string, output_path)
        data = read_file(output_path)
        return _img_response(data, f"output.{format}", format)
    finally:
        cleanup(up, out)


@router.post("/exif")
async def exif_viewer(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".jpg").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        return image_service.get_exif_data(input_path)
    finally:
        cleanup(up, out)


@router.post("/remove-exif")
async def exif_remover(request: Request, file: UploadFile = File(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".jpg").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/clean.{ext}"
        image_service.remove_exif(input_path, output_path)
        data = read_file(output_path)
        return _img_response(data, f"clean.{ext}", ext)
    finally:
        cleanup(up, out)


@router.post("/bulk-resize")
async def bulk_resize(request: Request, files: list[UploadFile] = File(...),
                      width: int = Form(...), height: int = Form(...)):
    _rl(request)
    _, up, out = make_job_dirs()
    try:
        paths = []
        for i, f in enumerate(files):
            validate_file_type(f, ALLOWED_IMAGES)
            content = await read_upload(f)
            ext = (f.filename or ".png").rsplit(".", 1)[-1].lower()
            paths.append(save_bytes(content, up, f"img_{i}.{ext}"))
        result_paths = image_service.bulk_resize(paths, out, width, height)
        zip_path = f"{up}/resized.zip"
        make_zip(result_paths, zip_path)
        data = read_file(zip_path)
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="resized.zip"'})
    finally:
        cleanup(up, out)


@router.post("/color-picker")
async def color_picker(request: Request, file: UploadFile = File(...), count: int = Form(5)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        return {"colors": image_service.extract_colors(input_path, count)}
    finally:
        cleanup(up, out)


@router.post("/filter")
async def image_filter(request: Request, file: UploadFile = File(...), filter_name: str = Form(...)):
    _rl(request)
    validate_file_type(file, ALLOWED_IMAGES)
    _, up, out = make_job_dirs()
    try:
        content = await read_upload(file)
        ext = (file.filename or ".png").rsplit(".", 1)[-1].lower()
        input_path = save_bytes(content, up, f"input.{ext}")
        output_path = f"{out}/filtered.{ext}"
        image_service.apply_filter(input_path, output_path, filter_name)
        data = read_file(output_path)
        return _img_response(data, f"filtered.{ext}", ext)
    finally:
        cleanup(up, out)
