"""Image processing service — powered by Pillow and rembg."""
import base64
import io
import json
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter, ImageEnhance, ExifTags
from fastapi import HTTPException


def compress_image(input_path: str, output_path: str, quality: int = 75) -> None:
    img = Image.open(input_path)
    ext = Path(output_path).suffix.lower()
    fmt = "JPEG" if ext in (".jpg", ".jpeg") else ext.lstrip(".").upper()
    if img.mode in ("RGBA", "P") and fmt == "JPEG":
        img = img.convert("RGB")
    img.save(output_path, format=fmt, quality=quality, optimize=True)


def resize_image(
    input_path: str,
    output_path: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    maintain_ratio: bool = True,
) -> None:
    img = Image.open(input_path)
    orig_w, orig_h = img.size
    if maintain_ratio:
        if width and not height:
            height = int(orig_h * width / orig_w)
        elif height and not width:
            width = int(orig_w * height / orig_h)
    if not width or not height:
        raise HTTPException(status_code=400, detail="Provide at least width or height")
    img = img.resize((width, height), Image.LANCZOS)
    img.save(output_path)


def crop_image(input_path: str, output_path: str, x: int, y: int, width: int, height: int) -> None:
    img = Image.open(input_path)
    img = img.crop((x, y, x + width, y + height))
    img.save(output_path)


def rotate_image(input_path: str, output_path: str, angle: int = 90, flip: Optional[str] = None) -> None:
    img = Image.open(input_path)
    if flip == "horizontal":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif flip == "vertical":
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    img = img.rotate(-angle, expand=True)
    img.save(output_path)


def convert_image_format(input_path: str, output_path: str, target_format: str) -> None:
    img = Image.open(input_path)
    fmt = target_format.upper().replace("JPG", "JPEG")
    if img.mode in ("RGBA", "P") and fmt == "JPEG":
        img = img.convert("RGB")
    img.save(output_path, format=fmt)


def remove_background(input_path: str, output_path: str) -> None:
    from rembg import remove
    with open(input_path, "rb") as f:
        data = f.read()
    result = remove(data)
    with open(output_path, "wb") as f:
        f.write(result)


def add_image_watermark_text(
    input_path: str,
    output_path: str,
    text: str,
    opacity: int = 128,
    position: str = "center",
) -> None:
    from PIL import ImageDraw, ImageFont
    img = Image.open(input_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("arial.ttf", size=40)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (img.width - tw) // 2
    y = (img.height - th) // 2
    draw.text((x, y), text, fill=(255, 255, 255, opacity), font=font)
    combined = Image.alpha_composite(img, overlay)
    combined.convert("RGB").save(output_path)


def image_to_base64(input_path: str) -> dict:
    with open(input_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    ext = Path(input_path).suffix.lstrip(".").lower()
    return {"base64": b64, "mime_type": f"image/{ext}"}


def base64_to_image(b64_string: str, output_path: str) -> None:
    data = base64.b64decode(b64_string)
    with open(output_path, "wb") as f:
        f.write(data)


def get_exif_data(input_path: str) -> dict:
    img = Image.open(input_path)
    exif_raw = img._getexif()
    if not exif_raw:
        return {}
    return {ExifTags.TAGS.get(k, k): str(v) for k, v in exif_raw.items()}


def remove_exif(input_path: str, output_path: str) -> None:
    img = Image.open(input_path)
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))
    clean.save(output_path)


def bulk_resize(input_paths: list[str], output_dir: str, width: int, height: int) -> list[str]:
    import os
    paths = []
    for p in input_paths:
        name = Path(p).name
        out = os.path.join(output_dir, name)
        resize_image(p, out, width, height)
        paths.append(out)
    return paths


def extract_colors(input_path: str, count: int = 5) -> list[dict]:
    img = Image.open(input_path).convert("RGB").resize((150, 150))
    pixels = list(img.getdata())
    from collections import Counter
    most_common = Counter(pixels).most_common(count)
    results = []
    for (r, g, b), freq in most_common:
        results.append({
            "hex": f"#{r:02x}{g:02x}{b:02x}",
            "rgb": {"r": r, "g": g, "b": b},
            "hsl": _rgb_to_hsl(r, g, b),
        })
    return results


def apply_filter(input_path: str, output_path: str, filter_name: str) -> None:
    img = Image.open(input_path)
    filters = {
        "blur": ImageFilter.BLUR,
        "sharpen": ImageFilter.SHARPEN,
        "contour": ImageFilter.CONTOUR,
        "detail": ImageFilter.DETAIL,
        "edge_enhance": ImageFilter.EDGE_ENHANCE,
        "emboss": ImageFilter.EMBOSS,
        "grayscale": None,
    }
    if filter_name not in filters:
        raise HTTPException(status_code=400, detail=f"Unknown filter: {filter_name}")
    if filter_name == "grayscale":
        img = img.convert("L")
    else:
        img = img.filter(filters[filter_name])
    img.save(output_path)


def _rgb_to_hsl(r: int, g: int, b: int) -> dict:
    r_, g_, b_ = r / 255, g / 255, b / 255
    cmax, cmin = max(r_, g_, b_), min(r_, g_, b_)
    delta = cmax - cmin
    l = (cmax + cmin) / 2
    s = 0 if delta == 0 else delta / (1 - abs(2 * l - 1))
    if delta == 0:
        h = 0
    elif cmax == r_:
        h = 60 * (((g_ - b_) / delta) % 6)
    elif cmax == g_:
        h = 60 * ((b_ - r_) / delta + 2)
    else:
        h = 60 * ((r_ - g_) / delta + 4)
    return {"h": round(h), "s": round(s * 100), "l": round(l * 100)}
