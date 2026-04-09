"""Format conversion service — PDF ↔ Word/Excel/PPT/Image/HTML/Markdown/CSV/Text."""
import io
import os
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from app.core.config import settings


# ---------------------------------------------------------------------------
# PDF ↔ Office (LibreOffice headless)
# ---------------------------------------------------------------------------

def _libreoffice_convert(input_path: str, output_dir: str, target_format: str) -> str:
    lo = settings.LIBREOFFICE_PATH or "libreoffice"
    result = subprocess.run(
        [lo, "--headless", "--convert-to", target_format, "--outdir", output_dir, input_path],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"LibreOffice conversion failed: {result.stderr}")
    stem = Path(input_path).stem
    out_path = os.path.join(output_dir, f"{stem}.{target_format}")
    if not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="Conversion output not found")
    return out_path


def word_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def excel_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def pptx_to_pdf(input_path: str, output_dir: str) -> str:
    return _libreoffice_convert(input_path, output_dir, "pdf")


def pdf_to_word(input_path: str, output_path: str) -> None:
    """Extract PDF text into a .docx."""
    import fitz
    from docx import Document

    doc = fitz.open(input_path)
    word = Document()
    for page in doc:
        word.add_paragraph(page.get_text())
        word.add_page_break()
    doc.close()
    word.save(output_path)


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
    return _libreoffice_convert(input_path, output_dir, "pptx")


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
    from PIL import Image
    images = []
    for p in input_paths:
        img = Image.open(p).convert("RGB")
        images.append(img)
    if not images:
        raise HTTPException(status_code=400, detail="No images provided")
    images[0].save(output_path, save_all=True, append_images=images[1:])


# ---------------------------------------------------------------------------
# HTML / Markdown / Text / CSV / SVG
# ---------------------------------------------------------------------------

def html_to_pdf(html_content: str, output_path: str) -> None:
    try:
        import weasyprint
        weasyprint.HTML(string=html_content).write_pdf(output_path)
    except ImportError:
        raise HTTPException(status_code=501, detail="weasyprint not installed. Run: pip install weasyprint")


def pdf_to_html(input_path: str, output_path: str) -> None:
    import fitz
    doc = fitz.open(input_path)
    html_parts = ["<html><body>"]
    for page in doc:
        html_parts.append(f"<div class='page'><pre>{page.get_text()}</pre></div>")
    html_parts.append("</body></html>")
    doc.close()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))


def markdown_to_pdf(md_text: str, output_path: str) -> None:
    try:
        import markdown as md_lib
        html = md_lib.markdown(md_text)
        html_to_pdf(html, output_path)
    except ImportError:
        raise HTTPException(status_code=501, detail="markdown not installed. Run: pip install markdown weasyprint")


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


def svg_to_png(input_path: str, output_path: str) -> None:
    try:
        import cairosvg
        cairosvg.svg2png(url=input_path, write_to=output_path)
    except ImportError:
        raise HTTPException(status_code=501, detail="cairosvg not installed. Run: pip install cairosvg")


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
