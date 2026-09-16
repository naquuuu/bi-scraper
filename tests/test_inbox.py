# OWNERSHIP: my-notes
"""Inbox ingestion: chapter tagging, idempotency, honest skips."""

from __future__ import annotations

import shutil
from pathlib import Path

from bi_scraper.inbox import ingest_inbox

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_frontmatter_note(store, settings):
    settings.inbox_dir.mkdir(parents=True)
    shutil.copyfile(
        FIXTURES / "inbox" / "ch2_inflasi_note.md",
        settings.inbox_dir / "ch2_inflasi_note.md",
    )
    results = ingest_inbox(store, settings)
    assert len(results) == 1
    assert results[0].chapter == 2
    assert results[0].inserted is True

    notes = store.documents_for_chapter(2, source_type="my-notes")
    assert len(notes) == 1
    assert notes[0]["title"] == "Ringkasan bab 2 - Inflasi dan Nilai Tukar"
    assert notes[0]["doc_date"] == "2026-09-12"
    assert notes[0]["url"] == "inbox://ch2_inflasi_note.md"
    assert "Inflasi" in notes[0]["content"]
    assert "[OWNERSHIP]" not in notes[0]["content"]


def test_ingest_is_idempotent(store, settings):
    settings.inbox_dir.mkdir(parents=True)
    shutil.copyfile(
        FIXTURES / "inbox" / "ch2_inflasi_note.md",
        settings.inbox_dir / "ch2_inflasi_note.md",
    )
    ingest_inbox(store, settings)
    second = ingest_inbox(store, settings)
    assert second[0].inserted is False
    assert "already indexed" in second[0].reason


def test_filename_chapter_tag(store, settings):
    settings.inbox_dir.mkdir(parents=True)
    (settings.inbox_dir / "bab7_catatan.md").write_text(
        "# Catatan\n\nWawasan kebangsaan catatan saya.", encoding="utf-8"
    )
    results = ingest_inbox(store, settings)
    assert results[0].chapter == 7
    assert results[0].inserted is True


def test_untagged_note_is_skipped_with_reason(store, settings):
    settings.inbox_dir.mkdir(parents=True)
    (settings.inbox_dir / "notes.md").write_text("# Notes\n\nno tags", encoding="utf-8")
    results = ingest_inbox(store, settings)
    assert results[0].chapter is None
    assert results[0].inserted is False
    assert results[0].reason == "no chapter 1-8 tag found"


def test_missing_inbox_returns_empty(store, settings):
    assert ingest_inbox(store, settings) == []
