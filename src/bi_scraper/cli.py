# OWNERSHIP: tooling
"""Typer CLI: fetch / ingest-inbox / index / export-notebook /
export-portfolio / coverage / search."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import typer

from . import config
from .chapter_map import Chapter, resolve_chapter_selector
from .config import FULL_START_DEFAULT, Settings, get_settings, load_hub_env_by_reference
from .export import export_notebook as _export_notebook
from .export import export_portfolio as _export_portfolio
from .freshness import coverage_failures, coverage_statuses
from .http_client import PoliteClient
from .inbox import ingest_inbox as _ingest_inbox
from .parsers.bi_rate import (
    build_page_payload,
    build_search_payload,
    extract_form_state,
    find_next_page_target,
    parse_rate_rows,
)
from .parsers.generic import parse_indicator_rows, parse_page
from .parsers.press_release import parse_press_release_listing
from .sources import (
    KIND_BI_RATE_FORM,
    KIND_PRESS_RELEASE,
    KIND_TABLE_PAGE,
    Source,
    sources_for_chapter,
)
from .storage.raw import save_raw
from .storage.sqlite_store import StudyStore

MAX_CONTENT_CHARS = 200_000

app = typer.Typer(
    add_completion=False,
    help="PCPM/TPD study corpus builder (public bi.go.id sources only).",
)


@dataclass
class FetchSummary:
    chapter: int
    name: str
    mode: str
    start: Optional[str]
    end: str
    fetched: int = 0
    failures: list[str] = field(default_factory=list)
    newest: Optional[str] = None
    note: str = ""


def run_fetch(
    *,
    store: StudyStore,
    settings: Settings,
    chapters: list[Chapter],
    start: date | None,
    end: date | None,
    full: bool,
    client: object,
    now: datetime | None = None,
) -> list[FetchSummary]:
    """Fetch configured sources per chapter (incremental unless ``full``)."""

    today = (now or datetime.now()).date()
    effective_end = end or today
    summaries: list[FetchSummary] = []
    for chapter in chapters:
        stored_newest = store.newest_public_date(chapter.id)
        if start is not None:
            chapter_start = start
        elif not full and stored_newest is not None:
            chapter_start = stored_newest + timedelta(days=1)
        else:
            chapter_start = date.fromisoformat(FULL_START_DEFAULT)
        mode = "full" if full else "incremental"
        summary = FetchSummary(
            chapter=chapter.id,
            name=chapter.name,
            mode=mode,
            start=chapter_start.isoformat(),
            end=effective_end.isoformat(),
        )
        if chapter_start > effective_end:
            summary.note = "up to date (nothing newer to fetch)"
            summaries.append(summary)
            continue
        for source in sources_for_chapter(chapter.id):
            try:
                _fetch_source(
                    store=store,
                    settings=settings,
                    client=client,
                    source=source,
                    chapter=chapter,
                    start=chapter_start,
                    end=effective_end,
                    full=full,
                    summary=summary,
                )
            except Exception as exc:  # keep going: one bad source never kills a run
                summary.failures.append(f"{source.name}: {exc}")
        store.set_fetch_log(chapter.id, mode, note=summary.note or None)
        newest = store.newest_public_date(chapter.id)
        summary.newest = newest.isoformat() if newest else None
        summaries.append(summary)
    return summaries


def _fetch_source(
    *,
    store: StudyStore,
    settings: Settings,
    client: object,
    source: Source,
    chapter: Chapter,
    start: date,
    end: date,
    full: bool,
    summary: FetchSummary,
) -> None:
    if source.kind == KIND_BI_RATE_FORM:
        _fetch_bi_rate_form(
            store=store,
            settings=settings,
            client=client,
            source=source,
            chapter=chapter,
            start=start,
            end=end,
            summary=summary,
        )
        return

    response = client.get(source.url)  # type: ignore[attr-defined]
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    raw_path = save_raw(settings.raw_dir, chapter.id, source.url, response.content)

    if source.kind == KIND_PRESS_RELEASE:
        metas = parse_press_release_listing(response.text, base_url=source.url)
        for meta in metas:
            if meta.date is not None:
                if not (start <= meta.date <= end):
                    continue
            elif not full:
                # undated listing entries are only re-collected on explicit --full
                continue
            store.add_document(
                chapter=chapter.id,
                url=meta.url,
                title=meta.title,
                content=meta.title,
                doc_kind="press_release_pdf" if meta.doc_type == "pdf" else "press_release_page",
                doc_date=meta.date.isoformat() if meta.date else None,
                raw_path=str(raw_path),
            )
            summary.fetched += 1
        return

    content = parse_page(response.text, source.url)
    store.add_document(
        chapter=chapter.id,
        url=source.url,
        title=content.title or source.name,
        content=content.text[:MAX_CONTENT_CHARS],
        doc_kind="web_page",
        raw_path=str(raw_path),
    )
    summary.fetched += 1
    if source.kind == KIND_TABLE_PAGE:
        rows = parse_indicator_rows(content)
        for _, period, value in rows:
            if period is None:
                continue
            store.add_indicator(
                chapter=chapter.id,
                name=source.name,
                period=period.isoformat(),
                value=value,
                unit=None,
                url=source.url,
            )
            summary.fetched += 1


def _fetch_bi_rate_form(
    *,
    store: StudyStore,
    settings: Settings,
    client: object,
    source: Source,
    chapter: Chapter,
    start: date,
    end: date,
    summary: FetchSummary,
) -> None:
    response = client.get(source.url)  # type: ignore[attr-defined]
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    save_raw(settings.raw_dir, chapter.id, source.url, response.content)
    state = extract_form_state(response.text)
    payload = build_search_payload(state, start, end)

    html = response.text
    page_number = 0
    while page_number < settings.max_pages:
        if page_number == 0:
            page_response = client.post(source.url, data=payload)  # type: ignore[attr-defined]
        else:
            target = find_next_page_target(html)
            if not target:
                break
            page_response = client.post(  # type: ignore[attr-defined]
                source.url, data=build_page_payload(state, target)
            )
        if page_response.status_code != 200:
            raise RuntimeError(f"HTTP {page_response.status_code} on page {page_number + 1}")
        html = page_response.text
        rows = parse_rate_rows(html, base_url=source.url)
        if not rows:
            break
        for row in rows:
            if row.rate_percent is None or row.period is None:
                continue
            if not (start <= row.period <= end):
                continue
            store.add_indicator(
                chapter=chapter.id,
                name="BI-Rate",
                period=row.period.isoformat(),
                value=row.rate_percent,
                unit="%",
                url=row.press_url or source.url,
            )
            if row.press_url:
                store.add_document(
                    chapter=chapter.id,
                    url=row.press_url,
                    title=f"BI-Rate {row.period.isoformat()}: {row.rate_percent}%",
                    content="",
                    doc_kind="press_release_link",
                    doc_date=row.period.isoformat(),
                )
            summary.fetched += 1
        page_number += 1


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


@app.callback()
def _main_callback() -> None:
    _configure_stdout()


def _parse_date_option(value: Optional[str], name: str) -> Optional[date]:
    if value is None:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise typer.BadParameter(f"{name} must be YYYY-MM-DD") from exc


def _chapters_or_bad_parameter(selector: str) -> list[Chapter]:
    try:
        return resolve_chapter_selector(selector)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _open_store(settings: Settings) -> StudyStore:
    return StudyStore(settings.db_path)


@app.command()
def fetch(
    chapter: str = typer.Option("all", "--chapter", help="1-8, comma list, or 'all'"),
    start_date: Optional[str] = typer.Option(
        None, "--start-date", help="YYYY-MM-DD (default: full start or stored newest + 1)"
    ),
    end_date: Optional[str] = typer.Option(
        None, "--end-date", help="YYYY-MM-DD (default: today)"
    ),
    full: bool = typer.Option(
        False, "--full", help="Explicit full refetch (ignores stored newest date)"
    ),
) -> None:
    """Fetch public bi.go.id sources for one or more chapters."""

    settings = get_settings()
    load_hub_env_by_reference()
    chapters = _chapters_or_bad_parameter(chapter)
    start = _parse_date_option(start_date, "--start-date")
    end = _parse_date_option(end_date, "--end-date")
    store = _open_store(settings)
    try:
        with PoliteClient(settings=settings) as client:
            summaries = run_fetch(
                store=store,
                settings=settings,
                chapters=chapters,
                start=start,
                end=end,
                full=full,
                client=client,
            )
    finally:
        store.close()
    for summary in summaries:
        typer.echo(
            f"ch{summary.chapter} {summary.name}: mode={summary.mode} "
            f"range={summary.start}..{summary.end} fetched={summary.fetched} "
            f"newest={summary.newest or 'none'}"
        )
        if summary.note:
            typer.echo(f"  note: {summary.note}")
        for failure in summary.failures:
            typer.echo(f"  [warn] {failure}")


@app.command("ingest-inbox")
def ingest_inbox_command() -> None:
    """Tag and index my own chapter summaries from data/inbox (no scraping)."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        results = _ingest_inbox(store, settings)
    finally:
        store.close()
    if not results:
        typer.echo("inbox is empty or missing (data/inbox/)")
        return
    for result in results:
        status = "indexed" if result.inserted else f"skipped ({result.reason or 'unchanged'})"
        chapter = f"ch{result.chapter}" if result.chapter else "untagged"
        typer.echo(f"{result.path.name}: {chapter} -> {status}")


@app.command()
def index(
    rebuild: bool = typer.Option(False, "--rebuild", help="Rebuild the FTS5 index"),
) -> None:
    """Maintain the FTS5 search index."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        if not rebuild:
            typer.echo("nothing to do (pass --rebuild to rebuild the FTS index)")
            return
        store.rebuild_fts()
        typer.echo(f"FTS index rebuilt ({store.count_documents()} documents)")
    finally:
        store.close()


@app.command("export-notebook")
def export_notebook_command(
    chapter: str = typer.Option("all", "--chapter", help="1-8, comma list, or 'all'"),
) -> None:
    """Write NotebookLM-ready Markdown study packs (one per chapter)."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        for selected in _chapters_or_bad_parameter(chapter):
            path = _export_notebook(store, selected, settings)
            typer.echo(f"ch{selected.id}: wrote {path}")
    finally:
        store.close()


@app.command("export-portfolio")
def export_portfolio_command(
    chapter: str = typer.Option("all", "--chapter", help="1-8, comma list, or 'all'"),
) -> None:
    """Write public-data-only portfolio charts + my analysis."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        for selected in _chapters_or_bad_parameter(chapter):
            path = _export_portfolio(store, selected, settings)
            typer.echo(f"ch{selected.id}: wrote {path}")
    finally:
        store.close()


@app.command()
def coverage() -> None:
    """Report chapter vs doc count vs newest date (exit 1 when stale)."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        statuses = coverage_statuses(
            store, today=config.today(), horizon_days=settings.horizon_days
        )
    finally:
        store.close()
    typer.echo(f"Freshness horizon: {settings.horizon_days} days (chapter 7 is report-only)")
    typer.echo("chapter                     | docs | newest     | fetched-at           | status")
    for status in statuses:
        newest = status.newest_date.isoformat() if status.newest_date else "-"
        fetched = status.last_fetch_at or "-"
        flag = " [NEWER-THAN-SYLLABUS]" if status.newer_than_syllabus else ""
        label = f"ch{status.chapter.id} {status.chapter.name}"
        typer.echo(
            f"{label:<27} | {status.doc_count:>4} | {newest:<10} | "
            f"{fetched:<20} | {status.status}{flag}"
        )
    failures = coverage_failures(statuses)
    if failures:
        chapters = ", ".join(f"ch{status.chapter.id}" for status in failures)
        typer.echo(
            f"FAIL: {len(failures)} chapter(s) older than {settings.horizon_days} days: {chapters}"
        )
        raise typer.Exit(code=1)
    typer.echo("PASS: all chapters within the freshness horizon (chapter 7 report-only)")


@app.command()
def search(
    query: str = typer.Argument(..., help="FTS5 query terms"),
    limit: int = typer.Option(25, "--limit", help="Maximum results"),
) -> None:
    """Full-text search across public documents and my notes."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        rows = store.search(query, limit=limit)
    finally:
        store.close()
    if not rows:
        typer.echo("no matches")
        return
    for row in rows:
        dated = row["doc_date"] or str(row["fetched_at"])[:10]
        typer.echo(f"[ch{row['chapter']}] {dated} -- {row['title']}")
        typer.echo(f"    {row['snippet']}")
        typer.echo(f"    {row['url']}")


if __name__ == "__main__":
    app()
