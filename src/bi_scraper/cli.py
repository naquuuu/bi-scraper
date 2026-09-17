# OWNERSHIP: tooling
"""Typer CLI: fetch / ingest-inbox / index / export-notebook /
export-portfolio / coverage / search."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

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
    RateFormError,
    build_page_payload,
    build_search_payload,
    extract_form_state,
    find_next_page_target,
    parse_rate_rows,
)
from .parsers.generic import parse_indicator_rows, parse_page
from .parsers.links import extract_internal_links
from .parsers.pdf import extract_pdf_text
from .parsers.press_release import parse_press_release_listing
from .parsers.visual import (
    content_image_srcs,
    count_content_images,
    is_visual_heavy,
    is_visual_heavy_unique,
)
from .sources import (
    KIND_BI_RATE_FORM,
    KIND_HUB,
    KIND_PDF,
    KIND_PRESS_RELEASE,
    KIND_TABLE_PAGE,
    Source,
    sources_for_chapter,
)
from .storage.raw import save_raw
from .storage.sqlite_store import StudyStore

MAX_CONTENT_CHARS = 200_000
# Per-request override for PDF downloads only (large binary files); never global.
PDF_REQUEST_TIMEOUT = 30.0

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


@dataclass
class EnrichSummary:
    chapter: int
    name: str
    pending: int = 0
    updated: int = 0
    failures: list[str] = field(default_factory=list)


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
    if source.kind == KIND_PDF:
        _fetch_pdf_source(
            store=store,
            settings=settings,
            client=client,
            source=source,
            chapter=chapter,
            summary=summary,
        )
        return

    if source.kind == KIND_HUB:
        _fetch_hub(
            store=store,
            settings=settings,
            client=client,
            source=source,
            chapter=chapter,
            summary=summary,
        )
        return

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
            timeout=source.timeout,
        )
        return

    response = client.get(source.url, timeout=source.timeout)  # type: ignore[attr-defined]
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    raw_path = save_raw(settings.raw_dir, chapter.id, source.url, response.content)

    if source.kind == KIND_PRESS_RELEASE:
        metas = parse_press_release_listing(response.text, base_url=source.url)
        for meta in metas:
            if meta.date is not None and not (start <= meta.date <= end):
                continue
            # Undated listing entries are always collected: INSERT OR IGNORE on
            # the content hash keeps repeated runs idempotent.
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
    image_count = count_content_images(response.text)
    store.add_document(
        chapter=chapter.id,
        url=source.url,
        title=content.title or source.name,
        content=content.text[:MAX_CONTENT_CHARS],
        doc_kind="web_page",
        raw_path=str(raw_path),
        visual_flag=1 if is_visual_heavy(image_count, len(content.text)) else 0,
        image_count=image_count,
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
    timeout: float | None = None,
) -> None:
    response = client.get(source.url, timeout=timeout)  # type: ignore[attr-defined]
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    save_raw(settings.raw_dir, chapter.id, source.url, response.content)
    state = extract_form_state(response.text)
    payload = build_search_payload(state, start, end)

    html = response.text
    page_number = 0
    while page_number < settings.max_pages:
        if page_number == 0:
            page_response = client.post(source.url, data=payload, timeout=timeout)  # type: ignore[attr-defined]
        else:
            target = find_next_page_target(html)
            if not target:
                break
            page_response = client.post(  # type: ignore[attr-defined]
                source.url, data=build_page_payload(state, target), timeout=timeout
            )
        if page_response.status_code != 200:
            raise RuntimeError(f"HTTP {page_response.status_code} on page {page_number + 1}")
        html = page_response.text
        try:
            # Refresh hidden fields (ViewState/EventValidation) from the current
            # page, mirroring what a browser submits for the next DataPager click.
            state = extract_form_state(html)
        except RateFormError:
            pass
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


def _hub_prefix(source: Source) -> str:
    """Path prefix that limits which links a hub crawl may follow."""

    if source.hub_prefix:
        return source.hub_prefix
    parts = [part for part in urlparse(source.url).path.split("/") if part]
    return "/" + "/".join(parts[:2]) + "/" if parts else "/"


def _fetch_pdf_source(
    *,
    store: StudyStore,
    settings: Settings,
    client: object,
    source: Source,
    chapter: Chapter,
    summary: FetchSummary,
) -> None:
    """Fetch one public PDF and store its extracted text (never decrypted)."""

    response = client.get(source.url, timeout=PDF_REQUEST_TIMEOUT)  # type: ignore[attr-defined]
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    raw_path = save_raw(
        settings.raw_dir,
        chapter.id,
        source.url,
        response.content,
        default_suffix=".pdf",
    )
    text = extract_pdf_text(response.content)
    if not text.strip():
        raise RuntimeError("no extractable text")
    store.add_document(
        chapter=chapter.id,
        url=source.url,
        title=source.name,
        content=text,
        doc_kind="web_pdf",
        raw_path=str(raw_path),
    )
    summary.fetched += 1


def _fetch_hub(
    *,
    store: StudyStore,
    settings: Settings,
    client: object,
    source: Source,
    chapter: Chapter,
    summary: FetchSummary,
) -> None:
    """BFS crawl of a bi.go.id section (root + subpages up to max_depth).

    Only links under the hub path prefix are followed; assets are skipped and
    every page is stored with its visual-dependence flags. Already-stored URLs
    are refreshed (flags/content untouched) instead of duplicated.
    """

    prefix = _hub_prefix(source)
    queue: list[tuple[str, int]] = [(source.url, 0)]
    visited: set[str] = set()
    known_urls = store.all_public_urls(chapter.id)
    pages = 0
    while queue and pages < settings.hub_max_pages:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        pages += 1
        try:
            if url.lower().endswith(".pdf"):
                response = client.get(url, timeout=PDF_REQUEST_TIMEOUT)  # type: ignore[attr-defined]
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}")
                raw_path = save_raw(
                    settings.raw_dir,
                    chapter.id,
                    url,
                    response.content,
                    default_suffix=".pdf",
                )
                text = extract_pdf_text(response.content)
                if url not in known_urls:
                    store.add_document(
                        chapter=chapter.id,
                        url=url,
                        title=url.rsplit("/", 1)[-1],
                        content=text,
                        doc_kind="web_pdf",
                        raw_path=str(raw_path),
                    )
                    known_urls.add(url)
                    summary.fetched += 1
                continue
            response = client.get(url)  # type: ignore[attr-defined]
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            raw_path = save_raw(settings.raw_dir, chapter.id, url, response.content)
            page = parse_page(response.text, url)
            image_count = count_content_images(response.text)
            visual_heavy = is_visual_heavy(image_count, len(page.text))
            if url in known_urls:
                existing = store.document_by_url(chapter.id, url)
                if existing is not None:
                    store.set_visual_flags(
                        int(existing["id"]),
                        image_count=image_count,
                        flagged=visual_heavy,
                    )
            else:
                store.add_document(
                    chapter=chapter.id,
                    url=url,
                    title=page.title or url,
                    content=page.text,
                    doc_kind="web_page",
                    raw_path=str(raw_path),
                    visual_flag=1 if visual_heavy else 0,
                    image_count=image_count,
                )
                known_urls.add(url)
                summary.fetched += 1
            if depth < source.max_depth:
                for link in extract_internal_links(response.text, url, prefix):
                    if link not in visited:
                        queue.append((link, depth + 1))
        except Exception as exc:  # one bad page never kills the crawl
            summary.failures.append(f"{url}: {exc}")


@dataclass
class VisualAuditSummary:
    chapter: int
    name: str
    scanned: int = 0
    flagged: int = 0


# Images repeated across at least this many pages are site chrome (sidebar
# thumbnails, carousels), not page content, and never trigger the flag alone.
CHROME_IMAGE_MIN_PAGES = 10


def run_audit_visuals(
    *, store: StudyStore, chapters: list[Chapter]
) -> list[VisualAuditSummary]:
    """Re-scan saved raw snapshots for image-heavy pages (no network access).

    Two passes: build a cross-page frequency table of image srcs (shared
    chrome detection), then flag pages whose *unique* images dominate.
    """

    per_doc: list[tuple[int, str, list[str], int]] = []
    for chapter in chapters:
        for row in store.public_documents_with_raw(chapter.id):
            raw_path = Path(str(row["raw_path"] or ""))
            if not raw_path.is_file():
                continue
            try:
                html = raw_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            per_doc.append(
                (
                    int(row["id"]),
                    str(row["chapter"]),
                    content_image_srcs(html),
                    len(str(row["content"] or "")),
                )
            )

    frequency: dict[str, int] = {}
    for _, _, srcs, _ in per_doc:
        for src in set(srcs):
            frequency[src] = frequency.get(src, 0) + 1

    summaries: list[VisualAuditSummary] = []
    for chapter in chapters:
        chapter_docs = [item for item in per_doc if item[1] == str(chapter.id)]
        summary = VisualAuditSummary(
            chapter=chapter.id, name=chapter.name, scanned=len(chapter_docs)
        )
        for document_id, _, srcs, text_length in chapter_docs:
            unique = sum(
                1 for src in set(srcs) if frequency.get(src, 0) < CHROME_IMAGE_MIN_PAGES
            )
            visual_heavy = is_visual_heavy_unique(unique, len(srcs), text_length)
            store.set_visual_flags(
                document_id, image_count=unique, flagged=visual_heavy
            )
            if visual_heavy:
                summary.flagged += 1
        summaries.append(summary)
    return summaries


def run_enrich(
    *,
    store: StudyStore,
    settings: Settings,
    chapters: list[Chapter],
    client: object,
    limit: int | None = None,
) -> list[EnrichSummary]:
    """Scrape the full text behind stored links (public HTML + public PDFs).

    Encrypted/protected PDFs are skipped and reported; nothing is ever
    decrypted or bypassed.
    """

    summaries: list[EnrichSummary] = []
    for chapter in chapters:
        targets = store.documents_needing_content(chapter.id, limit=limit)
        summary = EnrichSummary(
            chapter=chapter.id, name=chapter.name, pending=len(targets)
        )
        for row in targets:
            url = str(row["url"])
            try:
                is_pdf = (
                    str(row["doc_kind"]) == "press_release_pdf"
                    or url.lower().endswith(".pdf")
                )
                if is_pdf:
                    response = client.get(url, timeout=PDF_REQUEST_TIMEOUT)  # type: ignore[attr-defined]
                    if response.status_code != 200:
                        raise RuntimeError(f"HTTP {response.status_code}")
                    raw_path = save_raw(
                        settings.raw_dir,
                        chapter.id,
                        url,
                        response.content,
                        default_suffix=".pdf",
                    )
                    text = extract_pdf_text(response.content)
                else:
                    response = client.get(url)  # type: ignore[attr-defined]
                    if response.status_code != 200:
                        raise RuntimeError(f"HTTP {response.status_code}")
                    raw_path = save_raw(
                        settings.raw_dir, chapter.id, url, response.content
                    )
                    text = parse_page(response.text, url).text
                    image_count = count_content_images(response.text)
                    visual_heavy = is_visual_heavy(image_count, len(text))
                if not text.strip():
                    raise RuntimeError("no extractable text")
                store.update_document_content(int(row["id"]), text, str(raw_path))
                if not is_pdf:
                    store.set_visual_flags(
                        int(row["id"]), image_count=image_count, flagged=visual_heavy
                    )
                summary.updated += 1
            except Exception as exc:  # one bad URL never kills the run
                summary.failures.append(f"{url}: {exc}")
        summaries.append(summary)
    return summaries


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


@app.command()
def enrich(
    chapter: str = typer.Option("all", "--chapter", help="1-8, comma list, or 'all'"),
    limit: int = typer.Option(0, "--limit", help="Max documents per chapter (0 = all)"),
) -> None:
    """Scrape the full text behind stored links (public HTML + public PDFs)."""

    settings = get_settings()
    load_hub_env_by_reference()
    chapters = _chapters_or_bad_parameter(chapter)
    store = _open_store(settings)
    try:
        with PoliteClient(settings=settings) as client:
            summaries = run_enrich(
                store=store,
                settings=settings,
                chapters=chapters,
                client=client,
                limit=limit or None,
            )
    finally:
        store.close()
    updated_total = 0
    for summary in summaries:
        updated_total += summary.updated
        typer.echo(
            f"ch{summary.chapter} {summary.name}: enriched={summary.updated} "
            f"pending={summary.pending - summary.updated}"
        )
        for failure in summary.failures:
            typer.echo(f"  [warn] {failure}")
    typer.echo(f"enrich complete: {updated_total} document(s) with full text")


@app.command("audit-visuals")
def audit_visuals_command(
    chapter: str = typer.Option("all", "--chapter", help="1-8, comma list, or 'all'"),
) -> None:
    """Flag image-heavy pages using saved raw snapshots (no network access)."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        summaries = run_audit_visuals(
            store=store, chapters=_chapters_or_bad_parameter(chapter)
        )
    finally:
        store.close()
    total_flagged = 0
    for summary in summaries:
        total_flagged += summary.flagged
        typer.echo(
            f"ch{summary.chapter} {summary.name}: scanned={summary.scanned} "
            f"visual_heavy={summary.flagged}"
        )
    typer.echo(
        f"audit-visuals complete: {total_flagged} page(s) flagged for manual reading"
    )


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
    txt: bool = typer.Option(
        False, "--txt", help="Also write plain-text (.txt) packs for upload"
    ),
) -> None:
    """Write NotebookLM-ready Markdown study packs (one per chapter)."""

    settings = get_settings()
    store = _open_store(settings)
    try:
        for selected in _chapters_or_bad_parameter(chapter):
            path = _export_notebook(store, selected, settings, write_txt=txt)
            typer.echo(f"ch{selected.id}: wrote {path}")
            if txt:
                typer.echo(f"ch{selected.id}: wrote {path.with_suffix('.txt')}")
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
    typer.echo(
        "chapter                     | docs | fb | newest     | fetched-at           | status"
    )
    for status in statuses:
        newest = status.newest_date.isoformat() if status.newest_date else "-"
        fetched = status.last_fetch_at or "-"
        flag = " [NEWER-THAN-SYLLABUS]" if status.newer_than_syllabus else ""
        label = f"ch{status.chapter.id} {status.chapter.name}"
        typer.echo(
            f"{label:<27} | {status.doc_count:>4} | {status.fallback_docs:>2} | "
            f"{newest:<10} | {fetched:<20} | {status.status}{flag}"
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
