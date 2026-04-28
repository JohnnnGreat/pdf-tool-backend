"""PDF processing service — powered by PyMuPDF (fitz) and pypdf."""
import os
from typing import Optional

import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Merge / Split
# ---------------------------------------------------------------------------

def merge_pdfs(input_paths: list[str], output_path: str) -> None:
    doc = fitz.open()
    for path in input_paths:
        src = fitz.open(path)
        doc.insert_pdf(src)
        src.close()
    doc.save(output_path)
    doc.close()


def split_pdf(input_path: str, output_dir: str) -> list[str]:
    doc = fitz.open(input_path)
    paths = []
    for i in range(len(doc)):
        out = fitz.open()
        out.insert_pdf(doc, from_page=i, to_page=i)
        path = os.path.join(output_dir, f"page_{i + 1}.pdf")
        out.save(path)
        out.close()
        paths.append(path)
    doc.close()
    return paths


def split_pdf_ranges(input_path: str, output_dir: str, ranges: str) -> list[str]:
    """ranges: '1-3,5,7-10' (1-indexed)"""
    doc = fitz.open(input_path)
    total = len(doc)
    paths = []
    for segment in ranges.split(","):
        segment = segment.strip()
        if "-" in segment:
            start, end = segment.split("-", 1)
            from_page, to_page = int(start) - 1, int(end) - 1
        else:
            from_page = to_page = int(segment) - 1
        if from_page > to_page or from_page < 0 or to_page >= total:
            raise HTTPException(status_code=422, detail=f"Invalid page range: {segment}")
        out = fitz.open()
        out.insert_pdf(doc, from_page=from_page, to_page=to_page)
        label = segment.replace("-", "_")
        path = os.path.join(output_dir, f"range_{label}.pdf")
        out.save(path)
        out.close()
        paths.append(path)
    doc.close()
    return paths


# ---------------------------------------------------------------------------
# Compress / Rotate
# ---------------------------------------------------------------------------

def compress_pdf(input_path: str, output_path: str, quality: str = "medium") -> None:
    doc = fitz.open(input_path)
    # compression_effort: 0 = no effort (fast, larger), 100 = max effort (slow, smallest)
    if quality == "low":
        effort = 100
    elif quality == "high":
        effort = 20
    else:
        effort = 60
    doc.save(
        output_path,
        garbage=4,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        use_objstms=1,
        clean=True,
        compression_effort=effort,
    )
    doc.close()


def rotate_pdf(input_path: str, output_path: str, angle: int = 90, pages: Optional[str] = None) -> None:
    doc = fitz.open(input_path)
    targets = _parse_page_list(pages, len(doc)) if pages else list(range(len(doc)))
    for i in targets:
        doc[i].set_rotation((doc[i].rotation + angle) % 360)
    doc.save(output_path)
    doc.close()


# ---------------------------------------------------------------------------
# Page manipulation
# ---------------------------------------------------------------------------

def delete_pages(input_path: str, output_path: str, page_numbers: str) -> None:
    doc = fitz.open(input_path)
    to_delete = sorted([int(p) - 1 for p in page_numbers.split(",")], reverse=True)
    for i in to_delete:
        if 0 <= i < len(doc):
            doc.delete_page(i)
    doc.save(output_path)
    doc.close()


def reorder_pages(input_path: str, output_path: str, order: str) -> None:
    doc = fitz.open(input_path)
    new_order = [int(p) - 1 for p in order.split(",")]
    doc.select(new_order)
    doc.save(output_path)
    doc.close()


def extract_pages(input_path: str, output_path: str, page_numbers: str) -> None:
    doc = fitz.open(input_path)
    pages = sorted([int(p) - 1 for p in page_numbers.split(",")])
    out = fitz.open()
    for i in pages:
        if 0 <= i < len(doc):
            out.insert_pdf(doc, from_page=i, to_page=i)
    out.save(output_path)
    out.close()
    doc.close()


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------

def add_page_numbers(
    input_path: str,
    output_path: str,
    position: str = "bottom-center",
    font_size: int = 12,
    start_number: int = 1,
) -> None:
    doc = fitz.open(input_path)
    for i, page in enumerate(doc):
        rect = page.rect
        text = str(i + start_number)
        y = rect.height - 30 if "bottom" in position else 20
        if "left" in position:
            x = 30
        elif "right" in position:
            x = rect.width - 30
        else:
            x = rect.width / 2
        page.insert_text(fitz.Point(x, y), text, fontsize=font_size, color=(0, 0, 0))
    doc.save(output_path)
    doc.close()


def add_text_watermark(
    input_path: str,
    output_path: str,
    text: str,
    opacity: float = 0.3,
    font_size: int = 50,
) -> None:
    doc = fitz.open(input_path)
    for page in doc:
        rect = page.rect
        # PyMuPDF insert_text 'rotate' parameter only supports multiples of 90.
        # For arbitrary angles like 45, we use the 'morph' parameter (point, matrix).
        center = fitz.Point(rect.width / 2, rect.height / 2)
        # Matrix to rotate around the insertion point
        matrix = fitz.Matrix(45)
        page.insert_text(
            fitz.Point(rect.width * 0.1, rect.height * 0.6),
            text,
            fontsize=font_size,
            color=(0.5, 0.5, 0.5),
            fill_opacity=opacity,
            stroke_opacity=opacity,
            morph=(fitz.Point(rect.width * 0.3, rect.height * 0.5), matrix),
            overlay=True,
        )
    doc.save(output_path)
    doc.close()


def add_image_watermark(input_path: str, output_path: str, watermark_image_path: str, opacity: float = 0.3) -> None:
    doc = fitz.open(input_path)
    wm = fitz.open(watermark_image_path)
    for page in doc:
        page.show_pdf_page(page.rect, wm, 0, overlay=True, keep_proportion=True)
    doc.save(output_path)
    doc.close()


def add_header_footer(
    input_path: str,
    output_path: str,
    header: str = "",
    footer: str = "",
    font_size: int = 10,
) -> None:
    doc = fitz.open(input_path)
    for page in doc:
        rect = page.rect
        if header:
            page.insert_text(fitz.Point(30, 20), header, fontsize=font_size, color=(0, 0, 0))
        if footer:
            page.insert_text(fitz.Point(30, rect.height - 15), footer, fontsize=font_size, color=(0, 0, 0))
    doc.save(output_path)
    doc.close()


# ---------------------------------------------------------------------------
# Edit / Repair
# ---------------------------------------------------------------------------

def crop_pdf(input_path: str, output_path: str, x: float, y: float, width: float, height: float) -> None:
    doc = fitz.open(input_path)
    crop_rect = fitz.Rect(x, y, x + width, y + height)
    for page in doc:
        page.set_cropbox(crop_rect)
    doc.save(output_path)
    doc.close()


def flatten_pdf(input_path: str, output_path: str) -> None:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    writer.append(reader)
    writer.flatten_fields()
    with open(output_path, "wb") as f:
        writer.write(f)


def repair_pdf(input_path: str, output_path: str) -> None:
    doc = fitz.open(input_path)
    doc.save(output_path, clean=True, garbage=4)
    doc.close()


def redact_text(input_path: str, output_path: str, patterns: list[str]) -> None:
    doc = fitz.open(input_path)
    for page in doc:
        for pattern in patterns:
            areas = page.search_for(pattern)
            for area in areas:
                page.add_redact_annot(area, fill=(0, 0, 0))
        page.apply_redactions()
    doc.save(output_path)
    doc.close()


def overlay_pdfs(input_path: str, overlay_path: str, output_path: str) -> None:
    doc = fitz.open(input_path)
    overlay = fitz.open(overlay_path)
    for i, page in enumerate(doc):
        if i < len(overlay):
            page.show_pdf_page(page.rect, overlay, i, overlay=True)
    doc.save(output_path)
    doc.close()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def get_pdf_info(input_path: str) -> dict:
    doc = fitz.open(input_path)
    meta = doc.metadata
    info = {
        "page_count": len(doc),
        "file_size_bytes": os.path.getsize(input_path),
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "creator": meta.get("creator", ""),
        "producer": meta.get("producer", ""),
        "creation_date": meta.get("creationDate", ""),
        "modification_date": meta.get("modDate", ""),
    }
    doc.close()
    return info


def set_metadata(input_path: str, output_path: str, metadata: dict) -> None:
    doc = fitz.open(input_path)
    doc.set_metadata(metadata)
    doc.save(output_path)
    doc.close()


def convert_to_pdfa(input_path: str, output_path: str) -> None:
    doc = fitz.open(input_path)
    doc.save(output_path, pdfa=3, garbage=4, deflate=True)
    doc.close()


def add_bookmarks(input_path: str, output_path: str, bookmarks: list[dict]) -> None:
    """bookmarks: [{"title": "...", "page": 1, "level": 1}]"""
    doc = fitz.open(input_path)
    toc = [[b["level"], b["title"], b["page"]] for b in bookmarks]
    doc.set_toc(toc)
    doc.save(output_path)
    doc.close()


def fill_form(input_path: str, output_path: str, field_values: dict) -> None:
    doc = fitz.open(input_path)
    for page in doc:
        for field in page.widgets():
            if field.field_name in field_values:
                field.field_value = field_values[field.field_name]
                field.update()
    doc.save(output_path)
    doc.close()


def compare_pdfs(path_a: str, path_b: str) -> dict:
    doc_a = fitz.open(path_a)
    doc_b = fitz.open(path_b)
    result = {
        "pages_a": len(doc_a),
        "pages_b": len(doc_b),
        "page_count_match": len(doc_a) == len(doc_b),
        "differences": [],
    }
    for i in range(min(len(doc_a), len(doc_b))):
        text_a = doc_a[i].get_text()
        text_b = doc_b[i].get_text()
        if text_a != text_b:
            result["differences"].append({"page": i + 1, "changed": True})
    doc_a.close()
    doc_b.close()
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_page_list(pages_str: str, total: int) -> list[int]:
    result = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            result.extend(range(int(a) - 1, int(b)))
        else:
            result.append(int(part) - 1)
    return [p for p in result if 0 <= p < total]
