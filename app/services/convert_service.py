"""Format conversion service — PDF ↔ Word/Excel/PPT/Image/HTML/Markdown/CSV/Text."""
import os
import subprocess
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings


# ---------------------------------------------------------------------------
# PDF ↔ Office (LibreOffice headless)
# ---------------------------------------------------------------------------

def _libreoffice_convert(input_path: str, output_dir: str, target_format: str) -> str:
    lo = settings.LIBREOFFICE_PATH or "soffice"
    if lo.startswith('"') and lo.endswith('"'):
        lo = lo[1:-1]

    # Map target formats to LibreOffice filter names if needed
    convert_to = target_format
    if target_format == "pptx":
        # Sometimes 'impress_pptx_Export' is needed for PDF to PPTX conversion via Draw
        convert_to = "pptx"

    result = subprocess.run(
        [lo, "--headless", "--convert-to", convert_to, "--outdir", output_dir, input_path],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"DEBUG: LO stdout: {result.stdout}")
        print(f"DEBUG: LO stderr: {result.stderr}")
        raise HTTPException(status_code=500, detail=f"LibreOffice conversion failed: {result.stderr or result.stdout}")

    stem = Path(input_path).stem
    # Use glob to find the produced file as extension case/naming might vary
    possible_files = [f for f in os.listdir(output_dir) if f.lower().startswith(stem.lower()) and f.lower().endswith(f".{target_format.lower()}")]

    if not possible_files:
        print(f"DEBUG: LO STDOUT: {result.stdout}")
        print(f"DEBUG: Files in {output_dir}: {os.listdir(output_dir)}")
        raise HTTPException(status_code=500, detail=f"Conversion output not found for {stem}.{target_format}")

    return os.path.join(output_dir, possible_files[0])


def word_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def excel_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def pptx_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def pdf_to_word(input_path: str, output_path: str) -> None:
    """Convert PDF to Word via LibreOffice Draw PDF import for pixel-perfect layout."""
    lo = settings.LIBREOFFICE_PATH or "soffice"
    if lo.startswith('"') and lo.endswith('"'):
        lo = lo[1:-1]

    output_dir = str(Path(output_path).parent)

    # draw_pdf_import preserves exact element positions (text boxes, images, shapes)
    # as anchored Draw objects — far more accurate than writer_pdf_import which
    # tries to reflow content as paragraphs and scrambles the layout.
    result = subprocess.run(
        [
            lo, "--headless",
            "--infilter=draw_pdf_import",
            "--convert-to", "docx",
            "--outdir", output_dir,
            input_path,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"LibreOffice conversion failed: {result.stderr or result.stdout}",
        )

    stem = Path(input_path).stem
    possible = [
        f for f in os.listdir(output_dir)
        if f.lower().startswith(stem.lower()) and f.lower().endswith(".docx")
    ]
    if not possible:
        raise HTTPException(
            status_code=500,
            detail=f"Conversion output not found for {stem}.docx",
        )

    lo_out = os.path.join(output_dir, possible[0])
    if lo_out != output_path:
        os.replace(lo_out, output_path)


def pdf_to_excel(input_path: str, output_path: str) -> None:
    """Extract tables from PDF into .xlsx using PyMuPDF."""
    import fitz
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    doc = fitz.open(input_path)
    for page in doc:
        tabs = page.find_tables()
        for table in tabs.tables:
            for row in table.extract():
                ws.append([cell or "" for cell in row])
    doc.close()
    wb.save(output_path)


def pdf_to_pptx(input_path: str, output_dir: str) -> str:
    # Converting PDF to PPTX directly via LibreOffice CLI is unreliable.
    # We use a visual-fidelity approach: PDF -> Images -> PPTX slides.
    from pptx import Presentation
    from pptx.util import Inches
    import fitz

    # 1. Convert PDF to images
    doc = fitz.open(input_path)
    prs = Presentation()

    # Use first page size as slide size
    if len(doc) > 0:
        p = doc[0]
        prs.slide_width = Inches(p.rect.width / 72)
        prs.slide_height = Inches(p.rect.height / 72)

    for i, page in enumerate(doc):
        # Render page to image
        pix = page.get_pixmap(dpi=150)
        img_path = os.path.join(output_dir, f"temp_page_{i}.png")
        pix.save(img_path)

        # Create slide and add image
        slide = prs.slides.add_slide(prs.slide_layouts[6]) # blank layout
        slide.shapes.add_picture(img_path, 0, 0, width=prs.slide_width, height=prs.slide_height)

        # Cleanup temp image
        if os.path.exists(img_path):
            os.remove(img_path)

    doc.close()
    stem = Path(input_path).stem
    out_path = os.path.join(output_dir, f"{stem}.pptx")
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
        path = os.path.join(output_dir, f"page_{i + 1}.{fmt}")
        pix.save(path)
        paths.append(path)
    doc.close()
    return paths


def images_to_pdf(input_paths: list[str], output_path: str) -> None:
    import fitz
    if not input_paths:
        raise HTTPException(status_code=400, detail="No images provided")
    doc = fitz.open()
    for img_path in input_paths:
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        # Open image to get its dimensions
        img_doc = fitz.open(stream=img_bytes, filetype="png" if img_path.endswith(".png") else "jpg")
        if len(img_doc) > 0:
            r = img_doc[0].rect
            img_doc.close()
        else:
            img_doc.close()
            from PIL import Image as PILImage
            pil_img = PILImage.open(img_path)
            r = fitz.Rect(0, 0, pil_img.width, pil_img.height)
        page = doc.new_page(width=r.width, height=r.height)
        page.insert_image(r, stream=img_bytes)
    doc.save(output_path)
    doc.close()


# ---------------------------------------------------------------------------
# HTML / Markdown / Text / CSV / SVG
# ---------------------------------------------------------------------------

def html_to_pdf(html_content: str, output_path: str) -> None:
    # Use a unique stem for the temp file to avoid confusion in _libreoffice_convert
    temp_stem = "source_html"
    temp_html = os.path.join(os.path.dirname(output_path), f"{temp_stem}.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    try:
        lo_out = _libreoffice_convert(temp_html, os.path.dirname(output_path), "pdf")
        if os.path.exists(lo_out):
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(lo_out, output_path)
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)


def pdf_to_html(input_path: str, output_path: str) -> None:
    # Use LibreOffice for better PDF-to-HTML conversion
    lo_out = _libreoffice_convert(input_path, os.path.dirname(output_path), "html")
    if lo_out != output_path and os.path.exists(lo_out):
        os.replace(lo_out, output_path)


def markdown_to_pdf(md_text: str, output_path: str) -> None:
    import markdown as md_lib
    html = md_lib.markdown(md_text)
    html_to_pdf(html, output_path)


def svg_to_png(input_path: str, output_path: str) -> None:
    lo_out = _libreoffice_convert(input_path, os.path.dirname(output_path), "png")
    if lo_out != output_path and os.path.exists(lo_out):
        os.replace(lo_out, output_path)


def text_to_pdf(text: str, output_path: str, font_size: int = 12) -> None:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    y = height - 50
    for line in text.split("\n"):
        if y < 50:
            c.showPage()
            y = height - 50
        c.setFontSize(font_size)
        c.drawString(50, y, line)
        y -= font_size + 4
    c.save()


def csv_to_pdf(input_path: str, output_path: str) -> None:
    import csv
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from reportlab.lib import colors
    with open(input_path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    doc = SimpleDocTemplate(output_path)
    table = Table(rows)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    doc.build([table])


def csv_to_excel(input_path: str, output_path: str) -> None:
    import csv
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    with open(input_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            ws.append(row)
    wb.save(output_path)


def excel_to_csv(input_path: str, output_path: str) -> None:
    import csv
    from openpyxl import load_workbook
    wb = load_workbook(input_path, read_only=True)
    ws = wb.active
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            writer.writerow([cell or "" for cell in row])




def json_to_table(input_path: str, output_path: str, target: str = "csv") -> None:
    import json
    import csv
    from openpyxl import Workbook
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]
    keys = list(data[0].keys()) if data else []
    if target == "csv":
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(data)
    else:
        wb = Workbook()
        ws = wb.active
        ws.append(keys)
        for row in data:
            ws.append([row.get(k, "") for k in keys])
        wb.save(output_path)


def epub_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")
