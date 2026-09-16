# OWNERSHIP: tooling
"""CLI contract tests (offline: no command here performs network I/O)."""

from __future__ import annotations

from datetime import date

from typer.testing import CliRunner

from bi_scraper.cli import app
from bi_scraper.config import Settings, get_settings
from bi_scraper.storage.sqlite_store import StudyStore

runner = CliRunner()


def _settings_with_env(tmp_path, monkeypatch) -> Settings:
    data = tmp_path / "data"
    monkeypatch.setenv("BI_SCRAPER_DATA_DIR", str(data))
    monkeypatch.setenv("BI_SCRAPER_DB", str(data / "bi_study.db"))
    monkeypatch.setenv("BI_SCRAPER_EXPORTS_DIR", str(tmp_path / "exports"))
    return get_settings()


def test_coverage_fails_when_empty(tmp_path, monkeypatch):
    _settings_with_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["coverage"])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_coverage_passes_with_fresh_docs(tmp_path, monkeypatch):
    settings = _settings_with_env(tmp_path, monkeypatch)
    store = StudyStore(settings.db_path)
    today = date.today().isoformat()
    for chapter_id in (1, 2, 3, 4, 5, 6, 8):
        store.add_document(
            chapter=chapter_id,
            url=f"https://www.bi.go.id/{chapter_id}",
            title=f"doc {chapter_id}",
            doc_date=today,
        )
    store.close()
    result = runner.invoke(app, ["coverage"])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_ingest_inbox_index_and_search(tmp_path, monkeypatch):
    settings = _settings_with_env(tmp_path, monkeypatch)
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    (settings.inbox_dir / "ch3_kebijakan.md").write_text(
        "---\nchapter: 3\ntitle: Catatan moneter\n---\n# Catatan\n\nKebijakan moneter longgar.",
        encoding="utf-8",
    )
    ingested = runner.invoke(app, ["ingest-inbox"])
    assert ingested.exit_code == 0
    assert "indexed" in ingested.output

    rebuilt = runner.invoke(app, ["index", "--rebuild"])
    assert rebuilt.exit_code == 0
    assert "rebuilt" in rebuilt.output

    found = runner.invoke(app, ["search", "moneter"])
    assert found.exit_code == 0
    assert "[ch3]" in found.output


def test_export_notebook_command(tmp_path, monkeypatch):
    _settings_with_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["export-notebook", "--chapter", "1"])
    assert result.exit_code == 0
    assert "wrote" in result.output


def test_fetch_rejects_invalid_chapter(tmp_path, monkeypatch):
    _settings_with_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["fetch", "--chapter", "9"])
    assert result.exit_code != 0
