# OWNERSHIP: tooling
"""SQLite storage: documents, chapters, indicators, fetch_log + FTS5 search."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..chapter_map import CHAPTERS

SCHEMA = """
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    syllabus_version TEXT NOT NULL,
    syllabus_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL REFERENCES chapters(id),
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    doc_date TEXT,
    date_source TEXT NOT NULL DEFAULT 'parsed'
        CHECK (date_source IN ('parsed', 'fetch_fallback')),
    fetched_at TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('public', 'my-notes')),
    doc_kind TEXT NOT NULL,
    raw_path TEXT,
    content TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    UNIQUE (chapter, url, content_hash)
);

CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL REFERENCES chapters(id),
    name TEXT NOT NULL,
    period TEXT NOT NULL,
    value REAL,
    unit TEXT,
    url TEXT,
    fetched_at TEXT,
    UNIQUE (name, period, value, url)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    chapter INTEGER PRIMARY KEY REFERENCES chapters(id),
    last_fetch_at TEXT NOT NULL,
    last_mode TEXT NOT NULL,
    note TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    content,
    content='documents',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO documents_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;
"""


def utcnow_iso() -> str:
    """UTC timestamp used across records (``YYYY-MM-DDTHH:MM:SSZ``)."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StudyStore:
    """Thin, explicit wrapper around the study database."""

    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._seed_chapters()
        self.conn.commit()

    def _migrate(self) -> None:
        """Idempotent upgrades for databases created by earlier versions."""

        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(documents)")}
        if "date_source" not in columns:
            self.conn.execute(
                "ALTER TABLE documents ADD COLUMN date_source TEXT NOT NULL DEFAULT 'parsed'"
            )
            # Old rows without a parsed date were displayed with the fetch date:
            # mark them as fallback so the freshness gate ignores them.
            self.conn.execute(
                "UPDATE documents SET date_source = 'fetch_fallback' "
                "WHERE doc_date IS NULL AND source_type = 'public'"
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "StudyStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _seed_chapters(self) -> None:
        for chapter in CHAPTERS:
            self.conn.execute(
                """
                INSERT INTO chapters (id, name, syllabus_version, syllabus_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    syllabus_version = excluded.syllabus_version,
                    syllabus_date = excluded.syllabus_date
                """,
                (chapter.id, chapter.name, chapter.syllabus_version, chapter.syllabus_date),
            )

    @staticmethod
    def content_hash(title: str, content: str) -> str:
        return hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()

    def add_document(
        self,
        *,
        chapter: int,
        url: str,
        title: str,
        content: str = "",
        source_type: str = "public",
        doc_kind: str = "web_page",
        doc_date: str | None = None,
        date_source: str | None = None,
        fetched_at: str | None = None,
        raw_path: str | None = None,
    ) -> bool:
        """Insert a document; returns ``True`` when a new row was stored.

        ``date_source`` is derived: ``parsed`` when a real publish date was
        extracted, ``fetch_fallback`` when only the fetch timestamp is shown.
        """

        fetched_at = fetched_at or utcnow_iso()
        if date_source is None:
            date_source = "parsed" if doc_date else "fetch_fallback"
        digest = self.content_hash(title, content)
        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO documents
                (chapter, url, title, doc_date, date_source, fetched_at,
                 source_type, doc_kind, raw_path, content, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter,
                url,
                title,
                doc_date,
                date_source,
                fetched_at,
                source_type,
                doc_kind,
                raw_path,
                content,
                digest,
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def add_indicator(
        self,
        *,
        chapter: int,
        name: str,
        period: str,
        value: float,
        unit: str | None = None,
        url: str | None = None,
        fetched_at: str | None = None,
    ) -> bool:
        """Insert an indicator point; returns ``True`` when a new row was stored."""

        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO indicators
                (chapter, name, period, value, unit, url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (chapter, name, period, value, unit, url, fetched_at or utcnow_iso()),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def set_fetch_log(self, chapter: int, mode: str, note: str | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO fetch_log (chapter, last_fetch_at, last_mode, note)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chapter) DO UPDATE SET
                last_fetch_at = excluded.last_fetch_at,
                last_mode = excluded.last_mode,
                note = excluded.note
            """,
            (chapter, utcnow_iso(), mode, note),
        )
        self.conn.commit()

    def last_fetch_at(self, chapter: int) -> str | None:
        row = self.conn.execute(
            "SELECT last_fetch_at FROM fetch_log WHERE chapter = ?", (chapter,)
        ).fetchone()
        return row["last_fetch_at"] if row else None

    def newest_public_date(self, chapter: int) -> date | None:
        """Newest dated public document (falls back to fetch date)."""

        row = self.conn.execute(
            """
            SELECT MAX(COALESCE(doc_date, substr(fetched_at, 1, 10)))
            FROM documents
            WHERE chapter = ? AND source_type = 'public'
            """,
            (chapter,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            return date.fromisoformat(str(row[0]))
        except ValueError:
            return None

    def newest_real_date(self, chapter: int) -> date | None:
        """Newest public document with a **parsed** publish date.

        Fetch-fallback rows are excluded: they carry no real date evidence and
        must not drive the freshness gate or the NEWER-THAN-SYLLABUS flag.
        """

        row = self.conn.execute(
            """
            SELECT MAX(doc_date)
            FROM documents
            WHERE chapter = ? AND source_type = 'public' AND date_source = 'parsed'
            """,
            (chapter,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            return date.fromisoformat(str(row[0]))
        except ValueError:
            return None

    def fallback_doc_count(self, chapter: int) -> int:
        """Public documents whose displayed date is only the fetch timestamp."""

        row = self.conn.execute(
            """
            SELECT COUNT(*) FROM documents
            WHERE chapter = ? AND source_type = 'public'
              AND date_source = 'fetch_fallback'
            """,
            (chapter,),
        ).fetchone()
        return int(row[0]) if row else 0

    def count_documents(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0]) if row else 0

    def doc_count(self, chapter: int, source_type: str | None = None) -> int:
        if source_type is None:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM documents WHERE chapter = ?", (chapter,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM documents WHERE chapter = ? AND source_type = ?",
                (chapter, source_type),
            ).fetchone()
        return int(row[0]) if row else 0

    def documents_for_chapter(
        self,
        chapter: int,
        *,
        source_type: str | None = None,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        """Documents newest-first (``doc_date`` DESC, then ``fetched_at`` DESC)."""

        sql = """
            SELECT * FROM documents
            WHERE chapter = ?
        """
        params: list[Any] = [chapter]
        if source_type is not None:
            sql += " AND source_type = ?"
            params.append(source_type)
        sql += " ORDER BY (doc_date IS NULL), doc_date DESC, fetched_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, params).fetchall())

    def coverage_rows(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    c.syllabus_version,
                    c.syllabus_date,
                    (SELECT COUNT(*) FROM documents d
                     WHERE d.chapter = c.id AND d.source_type = 'public') AS doc_count,
                    (SELECT MAX(d.doc_date) FROM documents d
                     WHERE d.chapter = c.id AND d.source_type = 'public'
                       AND d.date_source = 'parsed') AS newest_real_date,
                    (SELECT COUNT(*) FROM documents d
                     WHERE d.chapter = c.id AND d.source_type = 'public'
                       AND d.date_source = 'fetch_fallback') AS fallback_count,
                    (SELECT f.last_fetch_at FROM fetch_log f
                     WHERE f.chapter = c.id) AS last_fetch_at
                FROM chapters c
                ORDER BY c.id
                """
            ).fetchall()
        )

    def indicator_series(
        self, chapter: int, name: str | None = None
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM indicators WHERE chapter = ?"
        params: list[Any] = [chapter]
        if name is not None:
            sql += " AND name = ?"
            params.append(name)
        sql += " ORDER BY period ASC"
        return list(self.conn.execute(sql, params).fetchall())

    def search(self, query: str, limit: int = 25) -> list[sqlite3.Row]:
        """FTS5 search over titles/content; returns rows plus a snippet."""

        tokens = [token for token in query.split() if token.strip()]
        if not tokens:
            return []
        match_expr = " ".join(f'"{token}"' for token in tokens)
        try:
            return list(
                self.conn.execute(
                    """
                    SELECT d.*, snippet(documents_fts, 1, '[', ']', ' ... ', 12) AS snippet
                    FROM documents_fts
                    JOIN documents d ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ?
                    ORDER BY bm25(documents_fts)
                    LIMIT ?
                    """,
                    (match_expr, limit),
                ).fetchall()
            )
        except sqlite3.OperationalError:
            return []

    def rebuild_fts(self) -> None:
        self.conn.execute("INSERT INTO documents_fts(documents_fts) VALUES ('rebuild')")
        self.conn.commit()

    def iter_documents(self) -> Iterator[sqlite3.Row]:
        yield from self.conn.execute("SELECT * FROM documents ORDER BY id")
