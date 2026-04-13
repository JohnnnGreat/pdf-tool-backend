"""OCR service — powered by pytesseract and PyMuPDF."""
import os
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from app.core.config import settings


def _get_tesseract():
    import pytesseract
    if settings.TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH
    # Validate tesseract is actually available
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        raise HTTPException(
            status_code=501,
            detail="Tesseract OCR is not installed or not found. Set TESSERACT_PATH in your .env file."
        )
    return pytesseract


def ocr_image(input_path: str, lang: Optional[str] = None) -> dict:
    pytesseract = _get_tesseract()
    from PIL import Image
    img = Image.open(input_path)
    language = lang or settings.TESSERACT_LANG
    text = pytesseract.image_to_string(img, lang=language)
    data = pytesseract.image_to_data(img, lang=language, output_type=pytesseract.Output.DICT)
    confidence = [c for c in data["conf"] if c != -1]
    avg_conf = round(sum(confidence) / len(confidence), 2) if confidence else 0.0
    return {"text": text.strip(), "confidence": avg_conf, "language": language}


def ocr_pdf_to_searchable(input_path: str, output_path: str, lang: Optional[str] = None) -> None:
    """Adds invisible text layer over scanned PDF pages."""
    import fitz
    pytesseract = _get_tesseract()
    from PIL import Image
    import io

    doc = fitz.open(input_path)
    language = lang or settings.TESSERACT_LANG
    new_doc = fitz.open()

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        ocr_pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, lang=language, extension="pdf")
        src = fitz.open("pdf", ocr_pdf_bytes)
        new_doc.insert_pdf(src)
        src.close()

    doc.close()
    new_doc.save(output_path)
    new_doc.close()


def ocr_multilang(input_path: str, lang: str) -> dict:
    return ocr_image(input_path, lang=lang)


def ocr_table(input_path: str, output_path: str) -> None:
    """Extract tables from scanned image/PDF into CSV."""
    import csv
    pytesseract = _get_tesseract()
    from PIL import Image

    ext = Path(input_path).suffix.lower()
    if ext == ".pdf":
        import fitz, io
        doc = fitz.open(input_path)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()
    else:
        img = Image.open(input_path)

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    rows: dict[int, list] = {}
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        line = data["line_num"][i]
        rows.setdefault(line, []).append(text)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for line_num in sorted(rows):
            writer.writerow(rows[line_num])


def ocr_handwriting(input_path: str) -> dict:
    pytesseract = _get_tesseract()
    from PIL import Image
    img = Image.open(input_path)
    text = pytesseract.image_to_string(img, config="--psm 6")
    return {"text": text.strip()}


def ocr_receipt(input_path: str) -> dict:
    result = ocr_image(input_path)
    text = result["text"]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    total = None
    date = None
    for line in lines:
        lower = line.lower()
        if "total" in lower:
            parts = line.split()
            for p in parts:
                try:
                    total = float(p.replace(",", "").replace("$", "").replace("£", ""))
                except ValueError:
                    pass
        if any(sep in line for sep in ["/", "-"]) and len(line) <= 12:
            date = line
    return {
        "raw_text": text,
        "lines": lines,
        "detected_total": total,
        "detected_date": date,
    }
