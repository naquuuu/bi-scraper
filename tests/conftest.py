# OWNERSHIP: tooling
"""Shared pytest fixtures. All tests are offline (MockTransport only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bi_scraper.config import Settings
from bi_scraper.storage.sqlite_store import StudyStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixture_text():
    """Read a fixture file as UTF-8 text."""

    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    return Settings(
        project_root=tmp_path,
        data_dir=data,
        db_path=data / "bi_study.db",
        raw_dir=data / "raw",
        inbox_dir=data / "inbox",
        exports_dir=tmp_path / "exports",
        min_delay=0.0,
        jitter=0.0,
        timeout=3.0,
        max_retries=2,
        horizon_days=60,
        max_pages=3,
    )


@pytest.fixture()
def store(settings: Settings):
    study_store = StudyStore(settings.db_path)
    yield study_store
    study_store.close()
