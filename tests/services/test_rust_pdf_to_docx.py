from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from app.services import convert_service
from rust_converter import is_available


def test_rust_pdf_to_docx_converts_sample_pdf(tmp_path: Path) -> None:
    if not is_available():
        pytest.skip("rust_converter native module is not built; run `maturin develop --release` first.")

    sample_pdf = Path(__file__).resolve().parents[2] / "test.pdf"
    output_docx = tmp_path / "sample.docx"

    convert_service.pdf_to_word(str(sample_pdf), str(output_docx))

    assert output_docx.exists()
    assert output_docx.stat().st_size > 0

    with ZipFile(output_docx) as archive:
        assert "word/document.xml" in archive.namelist()
