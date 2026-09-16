# OWNERSHIP: tooling
"""Freshness rules: 60-day horizon, chapter 7 exemption, syllabus flags."""

from __future__ import annotations

from datetime import date, timedelta

from bi_scraper.chapter_map import get_chapter
from bi_scraper.freshness import coverage_failures, coverage_statuses, evaluate_chapter

TODAY = date(2026, 9, 17)


def _evaluate(chapter_id: int, newest: date | None, doc_count: int = 5):
    return evaluate_chapter(
        get_chapter(chapter_id),
        doc_count=doc_count,
        newest_date=newest,
        last_fetch_at="2026-09-17T00:00:00Z",
        today=TODAY,
        horizon_days=60,
    )


def test_ok_within_horizon():
    status = _evaluate(1, TODAY - timedelta(days=59))
    assert status.status == "OK"
    assert status.stale is False


def test_stale_beyond_horizon():
    status = _evaluate(1, TODAY - timedelta(days=61))
    assert status.status == "STALE"
    assert status.stale is True


def test_no_documents_is_stale():
    status = _evaluate(1, None, doc_count=0)
    assert status.status == "STALE"


def test_chapter7_is_report_only_and_never_fails():
    status = _evaluate(7, None, doc_count=0)
    assert status.status == "REPORT"
    assert status.stale is True
    assert coverage_failures([status]) == []


def test_newer_than_syllabus_flag():
    flagged = _evaluate(1, date(2026, 9, 16))  # ch1 syllabus pin: 2026-09-09
    assert flagged.newer_than_syllabus is True
    clean = _evaluate(1, date(2026, 9, 1))
    assert clean.newer_than_syllabus is False


def test_coverage_statuses_from_store(store):
    today = date.today()
    for chapter_id in (1, 2):
        store.add_document(
            chapter=chapter_id,
            url=f"https://www.bi.go.id/{chapter_id}",
            title=f"doc {chapter_id}",
            doc_date=today.isoformat(),
        )
    statuses = coverage_statuses(store, today=today, horizon_days=60)
    by_id = {status.chapter.id: status for status in statuses}
    assert by_id[1].status == "OK"
    assert by_id[2].status == "OK"
    assert by_id[3].status == "STALE"
    failures = coverage_failures(statuses)
    assert {status.chapter.id for status in failures} == {3, 4, 5, 6, 8}
