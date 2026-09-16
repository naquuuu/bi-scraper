# OWNERSHIP: tooling
"""The eight PCPM/TPD study chapters and pinned syllabus versions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
    """One study chapter with its pinned syllabus version."""

    id: int
    name: str
    syllabus_version: str
    syllabus_date: str  # ISO date
    report_only: bool = False  # thin coverage expected; never FAIL in coverage


CHAPTERS: tuple[Chapter, ...] = (
    Chapter(1, "Pengenalan BI", "v1.9", "2026-09-09"),
    Chapter(2, "Inflasi + Nilai Tukar", "v1.2", "2026-07-18"),
    Chapter(3, "Kebijakan Moneter", "v1.2", "2026-07-06"),
    Chapter(4, "SSK + Makroprudensial", "v1.5", "2026-08-29"),
    Chapter(5, "Sistem Pembayaran", "v1.3", "2026-08-24"),
    Chapter(6, "Uang Rupiah", "v1.1", "2026-08-20"),
    Chapter(7, "Wawasan Kebangsaan", "v1.2", "2026-08-31", report_only=True),
    Chapter(8, "Ekonomi-Multilateral", "v1.2", "2026-09-14"),
)

_BY_ID = {chapter.id: chapter for chapter in CHAPTERS}


def chapter_ids() -> tuple[int, ...]:
    """All valid chapter ids, in order."""

    return tuple(chapter.id for chapter in CHAPTERS)


def get_chapter(chapter_id: int) -> Chapter:
    """Return a chapter by id, raising ``KeyError`` for invalid ids."""

    return _BY_ID[chapter_id]


def resolve_chapter_selector(selector: str) -> list[Chapter]:
    """Resolve ``--chapter`` values: ``all`` or a comma list like ``1,3``."""

    value = selector.strip().lower()
    if value in {"all", "*"}:
        return list(CHAPTERS)
    result: list[Chapter] = []
    for part in value.split(","):
        part = part.strip()
        if not part.isdigit() or int(part) not in _BY_ID:
            raise ValueError(f"invalid chapter: {part!r} (expected 1-8 or 'all')")
        chapter = _BY_ID[int(part)]
        if chapter not in result:
            result.append(chapter)
    if not result:
        raise ValueError("no chapters selected")
    return result
