from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
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


def _load_native_module():
    package_dir = Path(__file__).resolve().parent

    for search_root in [package_dir, *(Path(path) / "rust_converter" for path in sys.path if path)]:
        if not search_root.is_dir():
            continue

        for suffix in EXTENSION_SUFFIXES:
            candidate = search_root / f"_rust_converter{suffix}"
            if not candidate.is_file():
                continue

            spec = importlib.util.spec_from_file_location("rust_converter._rust_converter", candidate)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    raise ModuleNotFoundError("No module named 'rust_converter._rust_converter'")

try:
    _native_module = _load_native_module()
    DocxGenerationError = _native_module.DocxGenerationError
    InvalidPdfError = _native_module.InvalidPdfError
    RustConversionError = _native_module.RustConversionError
    UnsupportedScannedPdfError = _native_module.UnsupportedScannedPdfError
    _native_convert_pdf_to_docx = _native_module.convert_pdf_to_docx

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
