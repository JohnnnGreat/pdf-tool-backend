"""Format conversion service — PDF ↔ Word/Excel/PPT/Image/HTML/Markdown/CSV/Text."""
import logging
import os
import subprocess
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LibreOffice helper (Word/Excel/PPTX → PDF, EPUB → PDF, SVG → PNG)
# ---------------------------------------------------------------------------

def _resolve_libreoffice_path() -> str:
    raw = settings.LIBREOFFICE_PATH or "soffice"
    raw = raw.strip().strip('"')
    if raw == "soffice":
        return raw
    resolved = Path(raw).resolve()
    if not resolved.exists():
        raise HTTPException(status_code=500, detail=f"LibreOffice binary not found at '{resolved}'")
    return str(resolved)


def _libreoffice_convert(input_path: str, output_dir: str, target_format: str) -> str:
    lo = _resolve_libreoffice_path()
    result = subprocess.run(
        [lo, "--headless", "--convert-to", target_format, "--outdir", output_dir, input_path],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        logger.debug("LO stdout: %s", result.stdout)
        logger.debug("LO stderr: %s", result.stderr)
        raise HTTPException(status_code=500,
                            detail=f"LibreOffice conversion failed: {result.stderr or result.stdout}")
    stem = Path(input_path).stem
    matches = [
        f for f in os.listdir(output_dir)
        if f.lower().startswith(stem.lower()) and f.lower().endswith(f".{target_format.lower()}")
    ]
    if not matches:
        raise HTTPException(status_code=500,
                            detail=f"Conversion output not found for {stem}.{target_format}")
    return os.path.join(output_dir, matches[0])


# ---------------------------------------------------------------------------
# Office → PDF  (LibreOffice is gold standard for these)
# ---------------------------------------------------------------------------

def word_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def excel_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def pptx_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


# ---------------------------------------------------------------------------
# PDF → Word  (pdf2docx for digital, Tesseract+pdf2docx for scanned)
# ---------------------------------------------------------------------------

def pdf_to_word(input_path: str, output_path: str) -> None:
    """
    Digital PDFs  → pdf2docx (best-in-class layout fidelity)
    Scanned PDFs  → Tesseract OCR → searchable PDF → pdf2docx
    """
    import fitz
    pdf = fitz.open(input_path)
    sample_chars = sum(len(pdf[i].get_text().strip()) for i in range(min(3, len(pdf))))
    pdf.close()
    if sample_chars < 80:
        _pdf_to_word_scanned(input_path, output_path)
    else:
        _pdf_to_word_digital(input_path, output_path)


def _pdf_to_word_digital(input_path: str, output_path: str) -> None:
    from pdf2docx import Converter
    cv = Converter(input_path)
    cv.convert(output_path, start=0, end=None)
    cv.close()


def _pdf_to_word_scanned(input_path: str, output_path: str) -> None:
    """Render → Tesseract OCR PDF (text layer) → pdf2docx for full layout analysis."""
    import fitz
    import io
    import tempfile

    try:
        import pytesseract
        from PIL import Image
        if settings.TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH
        HAS_OCR = True
    except ImportError:
        HAS_OCR = False

    if not HAS_OCR:
        _pdf_to_word_digital(input_path, output_path)
        return

    pdf = fitz.open(input_path)
    page_pdfs: list[bytes] = []
    for page in pdf:
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        ocr_pdf = pytesseract.image_to_pdf_or_hocr(
            img, extension="pdf", config="--psm 1 --oem 3",
        )
        page_pdfs.append(ocr_pdf)
    pdf.close()

    merged = fitz.open()
    for page_bytes in page_pdfs:
        pg = fitz.open("pdf", page_bytes)
        merged.insert_pdf(pg)
        pg.close()

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)
    try:
        merged.save(tmp_path)
        merged.close()
        _pdf_to_word_digital(tmp_path, output_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# PDF → Excel  (pdfplumber — best table extraction accuracy)
# ---------------------------------------------------------------------------

def pdf_to_excel(input_path: str, output_path: str) -> None:
    """
    Extract tables from PDF into .xlsx.
    Uses pdfplumber with multiple strategies (lines → text fallback).
    Each detected table gets its own worksheet.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    BLUE   = "2563EB"
    STRIPE = "F1F5F9"
    BORDER_COLOR = "E2E8F0"

    def _border():
        s = Side(style="thin", color=BORDER_COLOR)
        return Border(left=s, right=s, top=s, bottom=s)

    try:
        import pdfplumber
        _extractor = "pdfplumber"
    except ImportError:
        _extractor = "pymupdf"

    wb = Workbook()
    wb.remove(wb.active)
    table_count = 0

    def _write_table(rows: list[list], sheet_title: str) -> None:
        nonlocal table_count
        table_count += 1
        ws = wb.create_sheet(title=sheet_title[:31])
        for r_idx, row in enumerate(rows, 1):
            for c_idx, val in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val or "")
                cell.border = _border()
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if r_idx == 1:
                    cell.fill = PatternFill("solid", fgColor=BLUE)
                    cell.font = Font(bold=True, color="FFFFFF", size=10)
                elif r_idx % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor=STRIPE)
        # Auto column widths
        for col in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 60)
        ws.freeze_panes = "A2"

    if _extractor == "pdfplumber":
        import pdfplumber
        with pdfplumber.open(input_path) as pdf:
            for p_num, page in enumerate(pdf.pages, 1):
                # Try line-based strategy first, fall back to text-based
                for strategy in (
                    {"vertical_strategy": "lines",    "horizontal_strategy": "lines",
                     "intersection_tolerance": 5},
                    {"vertical_strategy": "text",     "horizontal_strategy": "text",
                     "snap_tolerance": 3},
                ):
                    tables = page.extract_tables(strategy)
                    if tables:
                        break
                for t_idx, tbl in enumerate(tables or [], 1):
                    if tbl:
                        _write_table(tbl, f"P{p_num}-T{t_idx}")
    else:
        import fitz
        doc = fitz.open(input_path)
        for p_num, page in enumerate(doc, 1):
            for t_idx, tbl in enumerate(page.find_tables().tables, 1):
                rows = tbl.extract()
                if rows:
                    _write_table(rows, f"P{p_num}-T{t_idx}")
        doc.close()

    if not wb.worksheets:
        ws = wb.create_sheet("No Tables Found")
        ws.cell(1, 1, "No tables were detected in this PDF.")
        ws.column_dimensions["A"].width = 40

    wb.save(output_path)


# ---------------------------------------------------------------------------
# PDF → PPTX  (visual fidelity: each page → full-bleed slide image)
# ---------------------------------------------------------------------------

def pdf_to_pptx(input_path: str, output_dir: str) -> str:
    import fitz
    from pptx import Presentation
    from pptx.util import Emu

    doc = fitz.open(input_path)
    prs = Presentation()

    if doc:
        p0 = doc[0]
        # Convert PDF points (72 pt/inch) → EMU (914400 EMU/inch)
        prs.slide_width  = Emu(int(p0.rect.width  / 72 * 914400))
        prs.slide_height = Emu(int(p0.rect.height / 72 * 914400))

    blank_layout = prs.slide_layouts[6]

    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=200)   # 200 DPI — sharp on screen and print
        import io
        img_bytes = io.BytesIO(pix.tobytes("png"))
        slide = prs.slides.add_slide(blank_layout)
        slide.shapes.add_picture(img_bytes, 0, 0,
                                 width=prs.slide_width, height=prs.slide_height)

    doc.close()
    out_path = os.path.join(output_dir, f"{Path(input_path).stem}.pptx")
    prs.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# PDF ↔ Images
# ---------------------------------------------------------------------------

def pdf_to_images(input_path: str, output_dir: str, fmt: str = "png", dpi: int = 150) -> list[str]:
    import fitz
    doc = fitz.open(input_path)
    paths = []
    for i, page in enumerate(doc):
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        out = os.path.join(output_dir, f"page_{i + 1}.{fmt.lower()}")
        if fmt.lower() in ("jpg", "jpeg"):
            from PIL import Image as PILImage
            import io
            img = PILImage.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            img.save(out, "JPEG", quality=95, optimize=True)
        else:
            pix.save(out)
        paths.append(out)
    doc.close()
    return paths


def images_to_pdf(input_paths: list[str], output_path: str) -> None:
    """Convert images → PDF. Handles any format Pillow can open (PNG/JPEG/WebP/BMP/TIFF…)."""
    import fitz
    import io
    from PIL import Image as PILImage

    if not input_paths:
        raise HTTPException(status_code=400, detail="No images provided")

    doc = fitz.open()
    for img_path in input_paths:
        with PILImage.open(img_path) as pil_img:
            # Normalise: RGBA/P → RGB, keep L (greyscale)
            if pil_img.mode not in ("RGB", "L"):
                pil_img = pil_img.convert("RGB")
            w, h = pil_img.size
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
        page = doc.new_page(width=w, height=h)
        page.insert_image(fitz.Rect(0, 0, w, h), stream=img_bytes)

    doc.save(output_path, deflate=True)
    doc.close()


# ---------------------------------------------------------------------------
# HTML ↔ PDF  (xhtml2pdf — pure Python, better CSS than LibreOffice)
# ---------------------------------------------------------------------------

def html_to_pdf(html_content: str, output_path: str) -> None:
    """
    Convert HTML → PDF.
    Primary:  xhtml2pdf (pure Python, good CSS2 support, no system deps)
    Fallback: LibreOffice
    """
    try:
        from xhtml2pdf import pisa
        with open(output_path, "wb") as f:
            result = pisa.CreatePDF(html_content.encode("utf-8"), dest=f)
        if result.err:
            raise RuntimeError(f"xhtml2pdf error: {result.err}")
    except Exception as e:
        logger.warning("xhtml2pdf failed (%s), falling back to LibreOffice", e)
        _html_to_pdf_libreoffice(html_content, output_path)


def _html_to_pdf_libreoffice(html_content: str, output_path: str) -> None:
    temp_html = os.path.join(os.path.dirname(output_path), "_source.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    try:
        lo_out = _libreoffice_convert(temp_html, os.path.dirname(output_path), "pdf")
        if os.path.exists(lo_out) and lo_out != output_path:
            os.replace(lo_out, output_path)
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)


def pdf_to_html(input_path: str, output_path: str) -> None:
    """
    Convert PDF → HTML using PyMuPDF's structured HTML extraction.
    Preserves fonts, sizes, bold/italic, colours, and page layout far better
    than LibreOffice's export.
    """
    import fitz

    doc = fitz.open(input_path)
    pages_html: list[str] = []
    for i, page in enumerate(doc):
        # get_text("html") gives span-level HTML with font/size/colour attributes
        pages_html.append(
            f'<div class="page" id="page-{i + 1}" '
            f'style="position:relative;width:{page.rect.width:.0f}pt;'
            f'min-height:{page.rect.height:.0f}pt;">'
            f'{page.get_text("html")}</div>'
        )
    doc.close()

    html = (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        '<meta charset="utf-8">\n'
        "<style>\n"
        "  body{font-family:Arial,sans-serif;margin:0;padding:20px;background:#e5e7eb;}\n"
        "  .page{background:#fff;margin:0 auto 24px;padding:40px;max-width:860px;"
        "border-radius:4px;box-shadow:0 2px 10px rgba(0,0,0,.15);overflow:hidden;}\n"
        "</style>\n</head>\n<body>\n"
        + "\n".join(pages_html)
        + "\n</body>\n</html>"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Markdown → PDF  (proper styled HTML → xhtml2pdf)
# ---------------------------------------------------------------------------

def markdown_to_pdf(md_text: str, output_path: str) -> None:
    import markdown as md_lib

    body = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "nl2br", "sane_lists"],
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ margin: 2cm; }}
  body {{ font-family: Georgia, serif; font-size: 12pt; line-height: 1.7;
          color: #1e293b; }}
  h1 {{ font-size: 22pt; font-family: Arial, sans-serif; color: #0f172a;
        border-bottom: 2px solid #2563EB; padding-bottom: 6px; margin-top: 1.4em; }}
  h2 {{ font-size: 16pt; font-family: Arial, sans-serif; color: #0f172a;
        border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin-top: 1.2em; }}
  h3 {{ font-size: 13pt; font-family: Arial, sans-serif; color: #334155; }}
  code {{ background: #f1f5f9; padding: 2px 5px; border-radius: 3px;
          font-family: Courier, monospace; font-size: 10pt; }}
  pre  {{ background: #f1f5f9; padding: 14px; border-radius: 6px; }}
  pre code {{ background: none; padding: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 10pt; }}
  th {{ background: #2563EB; color: white; padding: 8px 12px; text-align: left; }}
  td {{ border: 1px solid #e2e8f0; padding: 7px 12px; }}
  tr:nth-child(even) td {{ background: #f8fafc; }}
  blockquote {{ border-left: 4px solid #2563EB; margin: 1em 0;
                padding: 8px 16px; background: #eff6ff; color: #1e40af; }}
  ul, ol {{ padding-left: 1.5em; }}
  a {{ color: #2563EB; }}
</style>
</head>
<body>{body}</body>
</html>"""

    html_to_pdf(html, output_path)


# ---------------------------------------------------------------------------
# SVG → PNG
# ---------------------------------------------------------------------------

def svg_to_png(input_path: str, output_path: str) -> None:
    lo_out = _libreoffice_convert(input_path, os.path.dirname(output_path), "png")
    if lo_out != output_path and os.path.exists(lo_out):
        os.replace(lo_out, output_path)


# ---------------------------------------------------------------------------
# Text → PDF  (ReportLab Platypus — proper word-wrap, Unicode, page breaks)
# ---------------------------------------------------------------------------

def text_to_pdf(text: str, output_path: str, font_size: int = 12) -> None:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors

    body_style = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=font_size,
        leading=font_size * 1.45,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=3,
    )

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=50, rightMargin=50,
        topMargin=50, bottomMargin=50,
    )

    story = []
    for line in text.split("\n"):
        if line.strip():
            # Escape special HTML chars so ReportLab doesn't misparse them
            safe = (line.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;"))
            story.append(Paragraph(safe, body_style))
        else:
            story.append(Spacer(1, font_size))

    if not story:
        story.append(Paragraph("(empty)", body_style))

    doc.build(story)


# ---------------------------------------------------------------------------
# CSV ↔ PDF / Excel
# ---------------------------------------------------------------------------

def csv_to_pdf(input_path: str, output_path: str) -> None:
    """
    CSV → PDF table via ReportLab.
    Auto-sizes columns, uses landscape for wide data, repeats header row on each page.
    """
    import csv
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm

    with open(input_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    if not rows:
        text_to_pdf("(Empty CSV file.)", output_path)
        return

    col_count = max(len(r) for r in rows)
    # Pad short rows
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    page_size = landscape(A4) if col_count > 6 else A4
    usable_w  = page_size[0] - 30 * mm

    # Column width proportional to longest value (capped)
    raw_widths = [
        max(len(str(rows[r][c])) for r in range(min(30, len(rows)))) or 4
        for c in range(col_count)
    ]
    total = sum(raw_widths)
    col_widths = [usable_w * w / total for w in raw_widths]

    style = TableStyle([
        ("BACKGROUND",     (0, 0), (-1,  0),  colors.HexColor("#2563EB")),
        ("TEXTCOLOR",      (0, 0), (-1,  0),  colors.white),
        ("FONTNAME",       (0, 0), (-1,  0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1,  0),  10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),  [colors.white, colors.HexColor("#f1f5f9")]),
        ("FONTSIZE",       (0, 1), (-1, -1),  9),
        ("GRID",           (0, 0), (-1, -1),  0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",     (0, 0), (-1, -1),  6),
        ("BOTTOMPADDING",  (0, 0), (-1, -1),  6),
        ("LEFTPADDING",    (0, 0), (-1, -1),  8),
        ("RIGHTPADDING",   (0, 0), (-1, -1),  8),
        ("VALIGN",         (0, 0), (-1, -1),  "MIDDLE"),
    ])

    doc = SimpleDocTemplate(
        output_path, pagesize=page_size,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(style)
    doc.build([table])


def csv_to_excel(input_path: str, output_path: str) -> None:
    """
    CSV → XLSX with:
    - Blue styled header row + freeze pane
    - Auto type coercion (int / float / string)
    - Auto column widths
    - Alternating row shading
    """
    import csv
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    BLUE   = "2563EB"
    STRIPE = "F1F5F9"
    BD     = "E2E8F0"

    def _border():
        s = Side(style="thin", color=BD)
        return Border(left=s, right=s, top=s, bottom=s)

    def _coerce(v: str):
        if v == "":
            return ""
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
        return v

    wb = Workbook()
    ws = wb.active
    ws.title = "Data"

    with open(input_path, newline="", encoding="utf-8-sig") as f:
        for r_idx, row in enumerate(csv.reader(f), 1):
            for c_idx, val in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.value = val if r_idx == 1 else _coerce(val)
                cell.border = _border()
                cell.alignment = Alignment(vertical="center")
                if r_idx == 1:
                    cell.fill = PatternFill("solid", fgColor=BLUE)
                    cell.font = Font(bold=True, color="FFFFFF", size=11)
                elif r_idx % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor=STRIPE)

    # Auto-fit columns
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 60)

    ws.freeze_panes = "A2"
    wb.save(output_path)


def excel_to_csv(input_path: str, output_path: str) -> None:
    import csv
    from openpyxl import load_workbook
    wb = load_workbook(input_path, read_only=True, data_only=True)
    ws = wb.active
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            writer.writerow([("" if cell is None else cell) for cell in row])


# ---------------------------------------------------------------------------
# JSON → CSV / Excel
# ---------------------------------------------------------------------------

def json_to_table(input_path: str, output_path: str, target: str = "csv") -> None:
    import json
    import csv
    from openpyxl import Workbook

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    # Normalise: wrap scalar/dict in a list
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        data = [{"value": data}]

    # Flatten one level of nesting
    flat: list[dict] = []
    for item in data:
        if isinstance(item, dict):
            flat.append({k: (str(v) if isinstance(v, (dict, list)) else v)
                         for k, v in item.items()})
        else:
            flat.append({"value": item})

    keys = list(flat[0].keys()) if flat else []

    if target == "csv":
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(flat)
    else:
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.append(keys)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2563EB")
        for row in flat:
            ws.append([row.get(k, "") for k in keys])
        for col in ws.columns:
            from openpyxl.utils import get_column_letter
            max_len = max((len(str(c.value or "")) for c in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 60)
        wb.save(output_path)


# ---------------------------------------------------------------------------
# EPUB → PDF
# ---------------------------------------------------------------------------

def epub_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")
