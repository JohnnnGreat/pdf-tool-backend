"""PDF live-editor service — powered by PyMuPDF (fitz).

Load:   parse PDF into pages (dimensions + text blocks + thumbnail)
Apply:  receive a list of edit operations and produce a modified PDF
"""
from __future__ import annotations

import base64
from typing import Any

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Load — return page structure + thumbnails
# ---------------------------------------------------------------------------

def load_pdf(input_path: str, thumbnail_scale: float = 1.5) -> dict:
    """Open a PDF and return its full structure as a dict.

    Args:
        input_path: path to the source PDF
        thumbnail_scale: zoom factor for page thumbnails (1.5 ≈ 96 dpi)

    Returns:
        {
            page_count: int,
            pages: [
                {
                    page_number: int,
                    width: float,
                    height: float,
                    thumbnail: str,          # base64-encoded PNG
                    text_blocks: [
                        {text, x0, y0, x1, y1, font_size, font, color}
                    ]
                }
            ]
        }
    """
    doc = fitz.open(input_path)
    pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        rect = page.rect

        # Render thumbnail
        mat = fitz.Matrix(thumbnail_scale, thumbnail_scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        thumbnail_b64 = base64.b64encode(pix.tobytes("png")).decode()

        # Extract text spans
        text_blocks: list[dict] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:  # 0 = text
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    raw_color = span.get("color", 0)
                    text_blocks.append({
                        "text": span["text"],
                        "x0": round(span["bbox"][0], 2),
                        "y0": round(span["bbox"][1], 2),
                        "x1": round(span["bbox"][2], 2),
                        "y1": round(span["bbox"][3], 2),
                        "font_size": round(span["size"], 2),
                        "font": span.get("font", ""),
                        # color is a packed int 0xRRGGBB in PyMuPDF
                        "color": _unpack_color(raw_color),
                    })

        pages.append({
            "page_number": page_num,
            "width": round(rect.width, 2),
            "height": round(rect.height, 2),
            "thumbnail": thumbnail_b64,
            "text_blocks": text_blocks,
        })

    doc.close()
    return {"page_count": len(pages), "pages": pages}


def render_page(input_path: str, page_number: int, scale: float = 2.0) -> bytes:
    """Render a single PDF page to PNG bytes."""
    doc = fitz.open(input_path)
    if page_number < 0 or page_number >= len(doc):
        doc.close()
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Page {page_number} does not exist")
    mat = fitz.Matrix(scale, scale)
    pix = doc[page_number].get_pixmap(matrix=mat, alpha=False)
    data = pix.tobytes("png")
    doc.close()
    return data


# ---------------------------------------------------------------------------
# Apply — execute edit operations and return modified PDF bytes
# ---------------------------------------------------------------------------

_OP_TYPES = {
    "replace_text", "add_text", "add_image",
    "add_highlight", "add_rectangle", "add_line",
    "whiteout", "delete_page", "add_blank_page",
}


def apply_edits(input_path: str, output_path: str, operations: list[dict[str, Any]]) -> None:
    """Apply a sequence of edit operations to a PDF and save the result.

    Supported operation types
    -------------------------
    replace_text     page, original_text, text, font_size?, color?
    add_text         page, x, y, text, font_size?, color?
    add_image        page, x, y, width, height, image_b64
    add_highlight    page, x, y, width, height, color?   (yellow by default)
    add_rectangle    page, x, y, width, height, color?, stroke_width?
    add_line         page, x1, y1, x2, y2, color?, stroke_width?
    whiteout         page, x, y, width, height
    delete_page      page
    add_blank_page   after_page?
    """
    doc = fitz.open(input_path)
    pages_to_delete: list[int] = []

    for op in operations:
        op_type = op.get("type", "")
        if op_type not in _OP_TYPES:
            continue

        page_num: int = op.get("page", 0)

        # --- Structural operations ---
        if op_type == "delete_page":
            pages_to_delete.append(page_num)
            continue

        if op_type == "add_blank_page":
            after = op.get("after_page", len(doc) - 1)
            doc.insert_page(after + 1)
            continue

        # --- Per-page operations ---
        if page_num < 0 or page_num >= len(doc):
            continue
        page = doc[page_num]

        if op_type == "replace_text":
            _op_replace_text(page, op)

        elif op_type == "add_text":
            _op_add_text(page, op)

        elif op_type == "add_image":
            _op_add_image(page, op)

        elif op_type == "add_highlight":
            x, y = op.get("x", 0), op.get("y", 0)
            w, h = op.get("width", 100), op.get("height", 20)
            color = _norm_color(op.get("color", [1, 1, 0]))
            page.draw_rect(fitz.Rect(x, y, x + w, y + h),
                           color=None, fill=color, fill_opacity=0.4)

        elif op_type == "add_rectangle":
            x, y = op.get("x", 0), op.get("y", 0)
            w, h = op.get("width", 100), op.get("height", 50)
            color = _norm_color(op.get("color", [1, 0, 0]))
            page.draw_rect(fitz.Rect(x, y, x + w, y + h),
                           color=color, width=float(op.get("stroke_width", 1.5)))

        elif op_type == "add_line":
            p1 = fitz.Point(op.get("x1", 0), op.get("y1", 0))
            p2 = fitz.Point(op.get("x2", 100), op.get("y2", 100))
            color = _norm_color(op.get("color", [0, 0, 0]))
            page.draw_line(p1, p2, color=color, width=float(op.get("stroke_width", 1.5)))

        elif op_type == "whiteout":
            x, y = op.get("x", 0), op.get("y", 0)
            w, h = op.get("width", 100), op.get("height", 50)
            page.add_redact_annot(fitz.Rect(x, y, x + w, y + h), fill=(1, 1, 1))
            page.apply_redactions()

    # Delete pages in reverse so indices stay valid
    for p in sorted(set(pages_to_delete), reverse=True):
        if 0 <= p < len(doc):
            doc.delete_page(p)

    doc.save(output_path)
    doc.close()


# ---------------------------------------------------------------------------
# Operation helpers
# ---------------------------------------------------------------------------

def _op_replace_text(page: fitz.Page, op: dict) -> None:
    original = op.get("original_text", "")
    if not original:
        return
    areas = page.search_for(original)
    if not areas:
        return
    # Whiteout all occurrences
    for area in areas:
        page.add_redact_annot(area, fill=(1, 1, 1))
    page.apply_redactions()
    # Insert replacement at the first occurrence's baseline
    replacement = op.get("text", "")
    if replacement:
        first = areas[0]
        page.insert_text(
            fitz.Point(first.x0, first.y1),
            replacement,
            fontsize=float(op.get("font_size", 11)),
            color=_norm_color(op.get("color", [0, 0, 0])),
        )


def _op_add_text(page: fitz.Page, op: dict) -> None:
    text = op.get("text", "")
    if not text:
        return
    page.insert_text(
        fitz.Point(op.get("x", 0), op.get("y", 0)),
        text,
        fontsize=float(op.get("font_size", 12)),
        color=_norm_color(op.get("color", [0, 0, 0])),
    )


def _op_add_image(page: fitz.Page, op: dict) -> None:
    image_b64 = op.get("image_b64", "")
    if not image_b64:
        return
    try:
        img_bytes = base64.b64decode(image_b64)
    except Exception:
        return
    x, y = op.get("x", 0), op.get("y", 0)
    w, h = op.get("width", 100), op.get("height", 100)
    page.insert_image(fitz.Rect(x, y, x + w, y + h), stream=img_bytes)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _unpack_color(packed: int) -> list[int]:
    """Convert PyMuPDF packed int color (0xRRGGBB) to [R, G, B] 0-255."""
    return [(packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF]


def _norm_color(color: list) -> tuple:
    """Normalise a color list to a tuple of floats 0.0-1.0 for PyMuPDF."""
    result = []
    for c in color[:3]:
        result.append(c / 255.0 if c > 1.0 else float(c))
    return tuple(result)
