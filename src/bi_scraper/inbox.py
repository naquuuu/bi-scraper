# OWNERSHIP: my-notes
"""Ingest my own chapter summaries from ``data/inbox/`` (never scraped).

Notes are tagged to chapters 1-8 via simple frontmatter (``chapter: 2``) or a
``ch2_`` filename prefix, extracted to text, and indexed alongside the public
corpus with ``source_type='my-notes'``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .storage.sqlite_store import StudyStore

FRONTMATTER_RE = re.compile(
    r"\A(?:\s*<!--.*?-->\s*)?---\s*\n(.*?)\n---\s*\n?", re.DOTALL
)
CHAPTER_RE = re.compile(r"(?:chapter|ch|bab)[\s_-]*([1-8])(?!\d)", re.IGNORECASE)
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class NoteMeta:
    path: Path
    chapter: int
    title: str
    body: str
    doc_date: str | None


@dataclass(frozen=True)
class IngestResult:
    path: Path
    chapter: int | None
    title: str
    inserted: bool
    reason: str = ""


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip().strip("'\"")
    return fields, text[match.end():]


def _normalise_date(value: str) -> str | None:
    match = DATE_RE.search(value or "")
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def parse_note(path: Path) -> NoteMeta | None:
    """Parse one inbox note; ``None`` when no chapter tag can be found."""

    text = path.read_text(encoding="utf-8", errors="replace")
    fields, body = _parse_frontmatter(text)

    chapter: int | None = None
    raw_chapter = fields.get("chapter", "").strip()
    if raw_chapter.isdigit() and 1 <= int(raw_chapter) <= 8:
        chapter = int(raw_chapter)
    if chapter is None:
        match = CHAPTER_RE.search(path.stem)
        if match:
            chapter = int(match.group(1))
    if chapter is None:
        match = CHAPTER_RE.search(body[:200])
        if match:
            chapter = int(match.group(1))
    if chapter is None:
        return None

    title = fields.get("title", "").strip()
    if not title:
        heading = HEADING_RE.search(body)
        title = heading.group(1).strip() if heading else path.stem

    doc_date = _normalise_date(fields.get("date", ""))
    if doc_date is None:
        doc_date = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).date().isoformat()
    return NoteMeta(
        path=path, chapter=chapter, title=title, body=body.strip(), doc_date=doc_date
    )


def ingest_inbox(store: StudyStore, settings: Settings) -> list[IngestResult]:
    """Ingest every supported note in the inbox; idempotent per content hash."""

    inbox = settings.inbox_dir
    results: list[IngestResult] = []
    if not inbox.is_dir():
        return results
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        meta = parse_note(path)
        if meta is None:
            results.append(
                IngestResult(
                    path=path,
                    chapter=None,
                    title=path.stem,
                    inserted=False,
                    reason="no chapter 1-8 tag found",
                )
            )
            continue
        inserted = store.add_document(
            chapter=meta.chapter,
            url=f"inbox://{path.name}",
            title=meta.title,
            content=meta.body,
            source_type="my-notes",
            doc_kind="note",
            doc_date=meta.doc_date,
        )
        results.append(
            IngestResult(
                path=path,
                chapter=meta.chapter,
                title=meta.title,
                inserted=inserted,
                reason="" if inserted else "already indexed (unchanged)",
            )
        )
    return results
