# OWNERSHIP: public-derived
"""Public PDF text extraction (text only; never decrypts or bypasses protections)."""

from __future__ import annotations

from io import BytesIO


class PdfExtractionError(RuntimeError):
    """Raised when a PDF cannot be read without bypassing protections."""


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a public PDF.

    Encrypted/protected files raise ``PdfExtractionError`` and are skipped —
    this tool never decrypts or bypasses PDF protection.
    """

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - pypdf is a declared dependency
        raise PdfExtractionError("pypdf is not installed") from exc

    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise PdfExtractionError(f"unreadable PDF: {exc}") from exc

    if reader.is_encrypted:
        raise PdfExtractionError("encrypted/protected PDF skipped (never decrypted)")

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(part.strip() for part in pages if part.strip())
