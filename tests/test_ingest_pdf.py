# OWNERSHIP: tooling
"""Local PDF ingest: full text, raw copy, idempotency, low-yield flag."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from bi_scraper.chapter_map import get_chapter
from bi_scraper.cli import ingest_pdf_file
from bi_scraper.parsers.pdf import PdfExtractionError

FIXTURES = Path(__file__).parent / "fixtures"

CANONICAL = (
    "https://www.bi.go.id/id/publikasi/kajian/Documents/"
    "Blueprint-Sistem-Pembayaran-Indonesia-2030.pdf"
)


def test_ingest_pdf_stores_full_text_and_raw_copy(store, settings):
    result = ingest_pdf_file(
        store=store,
        settings=settings,
        chapter=get_chapter(5),
        path=FIXTURES / "sample.pdf",
        url=CANONICAL,
        title="BSPI 2030 (test)",
    )
    assert result.inserted is True
    assert result.pages == 1
    assert result.chars > 0
    assert result.raw_path.is_file()
    assert result.raw_path.read_bytes().startswith(b"%PDF")

    row = store.document_by_url(5, CANONICAL)
    assert row is not None
    assert row["title"] == "BSPI 2030 (test)"
    assert "Hello BI Scraper PDF" in row["content"]  # full extracted text


def test_ingest_pdf_is_idempotent(store, settings):
    last = None
    for _ in range(2):
        last = ingest_pdf_file(
            store=store,
            settings=settings,
            chapter=get_chapter(5),
            path=FIXTURES / "sample.pdf",
            url=CANONICAL,
            title="BSPI 2030 (test)",
        )
    assert last is not None and last.inserted is False
    assert store.doc_count(5, source_type="public") == 1


def test_ingest_pdf_flags_scanned_low_yield(store, settings, tmp_path):
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=100, height=100)
    buffer = BytesIO()
    writer.write(buffer)
    blank = tmp_path / "scan.pdf"
    blank.write_bytes(buffer.getvalue())

    url = "https://www.bi.go.id/id/rupiah/digital-rupiah/Documents/scan.pdf"
    result = ingest_pdf_file(
        store=store,
        settings=settings,
        chapter=get_chapter(6),
        path=blank,
        url=url,
        title="Scanned doc",
    )
    assert result.low_yield is True
    assert result.pages == 3
    row = store.document_by_url(6, url)
    assert row is not None
    assert row["visual_flag"] == 1
    assert "tanpa lapisan teks" in row["content"]


def test_ingest_pdf_refuses_encrypted(store, settings, tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    buffer = BytesIO()
    writer.write(buffer)
    secure = tmp_path / "secure.pdf"
    secure.write_bytes(buffer.getvalue())

    with pytest.raises(PdfExtractionError, match="encrypted"):
        ingest_pdf_file(
            store=store,
            settings=settings,
            chapter=get_chapter(5),
            path=secure,
        )


def test_ingest_pdf_missing_file_raises(store, settings, tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest_pdf_file(
            store=store,
            settings=settings,
            chapter=get_chapter(5),
            path=tmp_path / "nope.pdf",
        )
