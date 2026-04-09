"""PDF security service — powered by pypdf."""
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from fastapi import HTTPException


def encrypt_pdf(
    input_path: str,
    output_path: str,
    user_password: str,
    owner_password: str = "",
) -> None:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=user_password, owner_password=owner_password or user_password)
    with open(output_path, "wb") as f:
        writer.write(f)


def decrypt_pdf(input_path: str, output_path: str, password: str) -> None:
    reader = PdfReader(input_path)
    if reader.is_encrypted:
        result = reader.decrypt(password)
        if result == 0:
            raise HTTPException(status_code=400, detail="Incorrect password")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)


def set_permissions(
    input_path: str,
    output_path: str,
    owner_password: str,
    allow_printing: bool = True,
    allow_copying: bool = False,
    allow_modifying: bool = False,
) -> None:
    from pypdf.constants import UserAccessPermissions
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    permissions = UserAccessPermissions(0)
    if allow_printing:
        permissions |= UserAccessPermissions.PRINT
    if allow_copying:
        permissions |= UserAccessPermissions.EXTRACT
    if allow_modifying:
        permissions |= UserAccessPermissions.MODIFY
    writer.encrypt(owner_password=owner_password, user_password="", permissions_flag=permissions)
    with open(output_path, "wb") as f:
        writer.write(f)


def auto_redact_pii(input_path: str, output_path: str, patterns: list[str]) -> None:
    import fitz
    PRESETS = {
        "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "phone": r"\+?[\d\s\-\(\)]{7,15}",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    }
    compiled = []
    for p in patterns:
        pattern = PRESETS.get(p, p)
        compiled.append(re.compile(pattern))

    doc = fitz.open(input_path)
    for page in doc:
        text = page.get_text()
        for regex in compiled:
            for match in regex.finditer(text):
                areas = page.search_for(match.group())
                for area in areas:
                    page.add_redact_annot(area, fill=(0, 0, 0))
        page.apply_redactions()
    doc.save(output_path)
    doc.close()


def sanitize_pdf(input_path: str, output_path: str) -> None:
    """Remove JavaScript, embedded files, and hidden metadata."""
    import fitz
    doc = fitz.open(input_path)
    doc.set_metadata({})
    doc.save(output_path, garbage=4, clean=True, deflate=True)
    doc.close()
