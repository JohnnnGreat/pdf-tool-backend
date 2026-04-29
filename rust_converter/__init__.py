from __future__ import annotations

from typing import Final

__all__ = [
    "AVAILABLE",
    "RustConversionError",
    "InvalidPdfError",
    "UnsupportedScannedPdfError",
    "DocxGenerationError",
    "RustModuleNotBuiltError",
    "convert_pdf_to_docx",
    "is_available",
]


class RustConversionError(RuntimeError):
    """Base error raised by the Rust PDF-to-DOCX converter."""


class InvalidPdfError(RustConversionError):
    """Raised when the input file is not a valid PDF."""


class UnsupportedScannedPdfError(RustConversionError):
    """Raised when the converter detects a scanned PDF without extractable text."""


class DocxGenerationError(RustConversionError):
    """Raised when the converter cannot write the output DOCX."""


class RustModuleNotBuiltError(RustConversionError):
    """Raised when the compiled PyO3 extension is not available."""


_IMPORT_ERROR: Exception | None = None

try:
    from ._rust_converter import (  # type: ignore[attr-defined]
        DocxGenerationError,
        InvalidPdfError,
        RustConversionError,
        UnsupportedScannedPdfError,
        convert_pdf_to_docx as _native_convert_pdf_to_docx,
    )

    AVAILABLE: Final[bool] = True
except Exception as exc:  # pragma: no cover - exercised when native module is absent.
    _IMPORT_ERROR = exc
    AVAILABLE = False

    def _native_convert_pdf_to_docx(input_path: str, output_path: str) -> bool:
        raise RustModuleNotBuiltError(
            "The Rust converter extension is not available. "
            "Build and install it with `maturin develop --release` from the backend root."
        ) from _IMPORT_ERROR


def is_available() -> bool:
    return AVAILABLE


def convert_pdf_to_docx(input_path: str, output_path: str) -> bool:
    """Convert a PDF to DOCX using the compiled Rust engine."""
    return _native_convert_pdf_to_docx(input_path, output_path)
