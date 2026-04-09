"""Signature and stamp service — powered by PyMuPDF."""
import fitz
from fastapi import HTTPException


def add_signature(
    input_path: str,
    output_path: str,
    signature_image_path: str,
    page_number: int = 1,
    x: float = 50,
    y: float = 50,
    width: float = 150,
    height: float = 60,
) -> None:
    doc = fitz.open(input_path)
    page_idx = page_number - 1
    if page_idx < 0 or page_idx >= len(doc):
        raise HTTPException(status_code=422, detail=f"Page {page_number} does not exist")
    page = doc[page_idx]
    rect = fitz.Rect(x, y, x + width, y + height)
    page.insert_image(rect, filename=signature_image_path)
    doc.save(output_path)
    doc.close()


def add_text_stamp(
    input_path: str,
    output_path: str,
    text: str,
    page_number: int = 1,
    x: float = 100,
    y: float = 100,
    font_size: int = 36,
    color: tuple = (1, 0, 0),
    rotate: int = 0,
) -> None:
    doc = fitz.open(input_path)
    page_idx = page_number - 1
    if page_idx < 0 or page_idx >= len(doc):
        raise HTTPException(status_code=422, detail=f"Page {page_number} does not exist")
    page = doc[page_idx]
    page.insert_text(
        fitz.Point(x, y),
        text,
        fontsize=font_size,
        color=color,
        rotate=rotate,
    )
    doc.save(output_path)
    doc.close()


def add_date_stamp(
    input_path: str,
    output_path: str,
    date_str: str,
    page_number: int = 1,
    x: float = 400,
    y: float = 750,
    font_size: int = 14,
) -> None:
    add_text_stamp(
        input_path,
        output_path,
        text=date_str,
        page_number=page_number,
        x=x,
        y=y,
        font_size=font_size,
        color=(0, 0, 0.8),
    )


def digital_sign(input_path: str, output_path: str, cert_path: str, cert_password: str) -> None:
    """
    Cryptographic PDF signing requires a PKCS#12 (.p12/.pfx) certificate.
    Requires: pyhanko (pip install pyhanko pyhanko-certvalidator)
    """
    try:
        from pyhanko.sign import signers, fields
        from pyhanko.sign.fields import SigFieldSpec
        from pyhanko_certvalidator import CertificateValidator
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

        with open(input_path, "rb") as inf:
            writer = IncrementalPdfFileWriter(inf)
            fields.append_signature_field(writer, SigFieldSpec("Signature", on_page=0))
            signer = signers.SimpleSigner.load_pkcs12(cert_path, passphrase=cert_password.encode())
            signers.sign_pdf(writer, signers.PdfSignatureMetadata(field_name="Signature"), signer=signer)
            with open(output_path, "wb") as outf:
                writer.write(outf)
    except ImportError:
        raise HTTPException(status_code=501, detail="pyhanko not installed. Run: pip install pyhanko")
