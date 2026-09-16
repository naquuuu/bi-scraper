# OWNERSHIP: public-derived
"""PDF text extraction: public PDFs only, encrypted files refused."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from bi_scraper.parsers.pdf import PdfExtractionError, extract_pdf_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_text_from_public_pdf():
    data = (FIXTURES / "sample.pdf").read_bytes()
    text = extract_pdf_text(data)
    assert "Hello BI Scraper PDF" in text


def test_encrypted_pdf_is_refused_never_decrypted():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(PdfExtractionError, match="encrypted"):
        extract_pdf_text(buffer.getvalue())


def test_garbage_bytes_are_refused():
    with pytest.raises(PdfExtractionError):
        extract_pdf_text(b"this is not a pdf")
