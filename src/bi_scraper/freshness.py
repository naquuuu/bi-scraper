# OWNERSHIP: tooling
"""Freshness rules: 60-day gate on parsed publish dates + NEWER-THAN-SYLLABUS.

Fetch-fallback dates (the fetch timestamp shown when no publish date could be
parsed) are **excluded** from the 60-day gate and from the NEWER-THAN-SYLLABUS
flag. A chapter whose only evidence is fallback reports ``HONEST-UNKNOWN``
instead of a misleading "fresh" date; a never-fetched chapter still fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .chapter_map import CHAPTERS, Chapter
from .storage.sqlite_store import StudyStore

STATUS_OK = "OK"
STATUS_STALE = "STALE"
STATUS_REPORT = "REPORT"
STATUS_UNKNOWN = "HONEST-UNKNOWN"


@dataclass(frozen=True)
class CoverageStatus:
    chapter: Chapter
    doc_count: int
    fallback_docs: int
    newest_date: date | None  # parsed publish dates only
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
    fallback_docs: int = 0,
) -> CoverageStatus:
    """Apply the binding freshness rule for a single chapter."""

    if chapter.report_only:
        status = STATUS_REPORT
    elif newest_date is None:
        status = STATUS_STALE if doc_count == 0 else STATUS_UNKNOWN
    elif (today - newest_date).days > horizon_days:
        status = STATUS_STALE
    else:
        status = STATUS_OK
    newer_than_syllabus = (
        newest_date is not None
        and newest_date > date.fromisoformat(chapter.syllabus_date)
    )
    return CoverageStatus(
        chapter=chapter,
        doc_count=doc_count,
        fallback_docs=fallback_docs,
        newest_date=newest_date,
        last_fetch_at=last_fetch_at,
        stale=status == STATUS_STALE,
        newer_than_syllabus=newer_than_syllabus,
        status=status,
    )


def coverage_statuses(
    store: StudyStore, *, today: date, horizon_days: int
) -> list[CoverageStatus]:
    """Evaluate freshness for all eight chapters."""

    statuses: list[CoverageStatus] = []
    rows = {int(row["id"]): row for row in store.coverage_rows()}
    for chapter in CHAPTERS:
        row = rows.get(chapter.id)
        newest: date | None = None
        if row is not None and row["newest_real_date"]:
            try:
                newest = date.fromisoformat(str(row["newest_real_date"]))
            except ValueError:
                newest = None
        statuses.append(
            evaluate_chapter(
                chapter,
                doc_count=int(row["doc_count"]) if row is not None else 0,
                fallback_docs=int(row["fallback_count"]) if row is not None else 0,
                newest_date=newest,
                last_fetch_at=(
                    str(row["last_fetch_at"]) if row is not None and row["last_fetch_at"] else None
                ),
                today=today,
                horizon_days=horizon_days,
            )
        )
    return statuses


def coverage_failures(statuses: list[CoverageStatus]) -> list[CoverageStatus]:
    """Chapters that violate the gate (report-only chapters are never STALE)."""

    return [status for status in statuses if status.status == STATUS_STALE]
