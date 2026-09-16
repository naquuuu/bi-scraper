# OWNERSHIP: tooling
"""Freshness rules: 60-day coverage horizon and NEWER-THAN-SYLLABUS flags."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .chapter_map import Chapter, CHAPTERS
from .storage.sqlite_store import StudyStore

STATUS_OK = "OK"
STATUS_STALE = "STALE"
STATUS_REPORT = "REPORT"


@dataclass(frozen=True)
class CoverageStatus:
    chapter: Chapter
    doc_count: int
    newest_date: date | None
    last_fetch_at: str | None
    stale: bool
    newer_than_syllabus: bool
    status: str


def evaluate_chapter(
    chapter: Chapter,
    *,
    doc_count: int,
    newest_date: date | None,
    last_fetch_at: str | None,
    today: date,
    horizon_days: int,
) -> CoverageStatus:
    """Apply the binding freshness rule for a single chapter.

    Chapter 7 (``report_only``) is reported honestly and never fails.
    """

    stale = newest_date is None or (today - newest_date).days > horizon_days
    newer_than_syllabus = (
        newest_date is not None
        and newest_date > date.fromisoformat(chapter.syllabus_date)
    )
    if chapter.report_only:
        status = STATUS_REPORT
    elif stale:
        status = STATUS_STALE
    else:
        status = STATUS_OK
    return CoverageStatus(
        chapter=chapter,
        doc_count=doc_count,
        newest_date=newest_date,
        last_fetch_at=last_fetch_at,
        stale=stale,
        newer_than_syllabus=newer_than_syllabus,
        status=status,
    )


def coverage_statuses(
    store: StudyStore, *, today: date, horizon_days: int
) -> list[CoverageStatus]:
    """Evaluate freshness for all eight chapters, newest-date first per row."""

    statuses: list[CoverageStatus] = []
    rows = {int(row["id"]): row for row in store.coverage_rows()}
    for chapter in CHAPTERS:
        row = rows.get(chapter.id)
        newest: date | None = None
        if row is not None and row["newest_date"]:
            try:
                newest = date.fromisoformat(str(row["newest_date"]))
            except ValueError:
                newest = None
        statuses.append(
            evaluate_chapter(
                chapter,
                doc_count=int(row["doc_count"]) if row is not None else 0,
                newest_date=newest,
                last_fetch_at=str(row["last_fetch_at"]) if row and row["last_fetch_at"] else None,
                today=today,
                horizon_days=horizon_days,
            )
        )
    return statuses


def coverage_failures(statuses: list[CoverageStatus]) -> list[CoverageStatus]:
    """Chapters that violate the freshness rule (report-only chapters exempt)."""

    return [
        status
        for status in statuses
        if status.stale and not status.chapter.report_only
    ]
