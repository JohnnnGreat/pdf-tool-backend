"""Batch processing service — process multiple files at once."""
import os
from pathlib import Path

from app.services import pdf_service, image_service, convert_service


def batch_convert(input_paths: list[str], output_dir: str, target_format: str) -> list[str]:
    results = []
    for path in input_paths:
        ext = Path(path).suffix.lower()
        stem = Path(path).stem
        out = os.path.join(output_dir, f"{stem}.{target_format.lstrip('.')}")
        try:
            if target_format == "pdf":
                if ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
                    convert_service.images_to_pdf([path], out)
                elif ext in (".docx", ".doc"):
                    convert_service.word_to_pdf(path, output_dir)
                    out = os.path.join(output_dir, f"{stem}.pdf")
            elif target_format in ("png", "jpg", "jpeg") and ext == ".pdf":
                pages = convert_service.pdf_to_images(path, output_dir, fmt=target_format)
                results.extend(pages)
                continue
            results.append(out)
        except Exception as e:
            results.append(f"ERROR:{path}:{e}")
    return results


def batch_compress(input_paths: list[str], output_dir: str) -> list[str]:
    results = []
    for path in input_paths:
        ext = Path(path).suffix.lower()
        stem = Path(path).stem
        if ext == ".pdf":
            out = os.path.join(output_dir, f"{stem}_compressed.pdf")
            pdf_service.compress_pdf(path, out)
        elif ext in (".jpg", ".jpeg", ".png", ".webp"):
            out = os.path.join(output_dir, f"{stem}_compressed{ext}")
            image_service.compress_image(path, out)
        else:
            continue
        results.append(out)
    return results


def batch_watermark(input_paths: list[str], output_dir: str, text: str) -> list[str]:
    results = []
    for path in input_paths:
        ext = Path(path).suffix.lower()
        stem = Path(path).stem
        if ext == ".pdf":
            out = os.path.join(output_dir, f"{stem}_watermarked.pdf")
            pdf_service.add_text_watermark(path, out, text)
            results.append(out)
    return results


def batch_rename(input_paths: list[str], output_dir: str, pattern: str) -> list[str]:
    """
    pattern: use {name}, {index}, {ext} placeholders.
    Example: "document_{index}{ext}"
    """
    import shutil
    results = []
    for i, path in enumerate(input_paths):
        p = Path(path)
        new_name = pattern.format(name=p.stem, index=i + 1, ext=p.suffix)
        out = os.path.join(output_dir, new_name)
        shutil.copy2(path, out)
        results.append(out)
    return results
