# OWNERSHIP: tooling
"""Freshness rules: real-date gate, fetch-fallback exclusion, syllabus flags."""

from __future__ import annotations

from datetime import date, timedelta

from bi_scraper.chapter_map import get_chapter
from bi_scraper.freshness import (
    STATUS_UNKNOWN,
    coverage_failures,
    coverage_statuses,
    evaluate_chapter,
)

TODAY = date(2026, 9, 17)


def _evaluate(
    chapter_id: int,
    newest: date | None,
    doc_count: int = 5,
    fallback_docs: int = 0,
):
    return evaluate_chapter(
        get_chapter(chapter_id),
        doc_count=doc_count,
        fallback_docs=fallback_docs,
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


def test_fallback_only_chapter_is_honest_unknown():
    status = _evaluate(1, None, doc_count=4, fallback_docs=4)
    assert status.status == STATUS_UNKNOWN
    assert status.stale is False
    assert status.newer_than_syllabus is False
    assert coverage_failures([status]) == []


def test_gate_uses_real_dates_only():
    # Real dates are old -> STALE, even though fallback docs "look" recent.
    status = _evaluate(1, TODAY - timedelta(days=100), doc_count=7, fallback_docs=3)
    assert status.status == "STALE"


def test_fresh_real_date_with_fallbacks_is_ok():
    status = _evaluate(1, TODAY - timedelta(days=5), doc_count=9, fallback_docs=8)
    assert status.status == "OK"


def test_chapter7_is_report_only_and_never_fails():
    status = _evaluate(7, None, doc_count=0)
    assert status.status == "REPORT"
    assert status.stale is False
    assert coverage_failures([status]) == []


def test_newer_than_syllabus_flag_uses_real_dates_only():
    flagged = _evaluate(1, date(2026, 9, 16))  # ch1 syllabus pin: 2026-09-09
    assert flagged.newer_than_syllabus is True
    clean = _evaluate(1, date(2026, 9, 1))
    assert clean.newer_than_syllabus is False
    fallback_only = _evaluate(1, None, doc_count=2, fallback_docs=2)
    assert fallback_only.newer_than_syllabus is False


def test_coverage_statuses_from_store(store):
    today = date.today()
    for chapter_id in (1, 2):
        store.add_document(
            chapter=chapter_id,
            url=f"https://www.bi.go.id/{chapter_id}",
            title=f"doc {chapter_id}",
            doc_date=today.isoformat(),
        )
    store.add_document(
        chapter=5,
        url="https://www.bi.go.id/id/rupiah/page",
        title="undated page doc",
    )
    statuses = coverage_statuses(store, today=today, horizon_days=60)
    by_id = {status.chapter.id: status for status in statuses}
    assert by_id[1].status == "OK"
    assert by_id[2].status == "OK"
    assert by_id[5].status == STATUS_UNKNOWN
    assert by_id[3].status == "STALE"
    failures = coverage_failures(statuses)
    assert {status.chapter.id for status in failures} == {3, 4, 6, 8}
