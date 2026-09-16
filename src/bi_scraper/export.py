# OWNERSHIP: tooling
"""NotebookLM study packs and public-data-only portfolio exports."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from .chapter_map import Chapter
from .config import Settings
from .freshness import STATUS_UNKNOWN, CoverageStatus, evaluate_chapter
from .storage.sqlite_store import StudyStore

OWNERSHIP_NOTEBOOK = "public-derived metadata + my-notes text"
OWNERSHIP_PORTFOLIO = "my-notes analysis + public-derived data"

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")

MIN_THIN_DOCS = 3


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value).strip("-").lower() or "export"


def _chapter_status(store: StudyStore, chapter: Chapter, settings: Settings, now: datetime | None) -> CoverageStatus:
    today = (now or datetime.now()).date()
    return evaluate_chapter(
        chapter,
        doc_count=store.doc_count(chapter.id, source_type="public"),
        fallback_docs=store.fallback_doc_count(chapter.id),
        newest_date=store.newest_real_date(chapter.id),
        last_fetch_at=store.last_fetch_at(chapter.id),
        today=today,
        horizon_days=settings.horizon_days,
    )


def _newest_date_text(status: CoverageStatus) -> str:
    if status.newest_date is not None:
        return status.newest_date.isoformat()
    if status.fallback_docs:
        return (
            f"HONEST-UNKNOWN ({status.fallback_docs} undated doc(s); "
            "fetch-fallback dates excluded from the gate)"
        )
    return "HONEST-UNKNOWN (no dated docs)"


def _header_lines(status: CoverageStatus, settings: Settings) -> list[str]:
    chapter = status.chapter
    lines = [
        f"# Chapter {chapter.id} -- {chapter.name}",
        "",
        f"- Fetched-At: {status.last_fetch_at or 'never'}",
        f"- Chapter newest dated public doc: {_newest_date_text(status)}",
        f"- Syllabus pin: {chapter.syllabus_version} ({chapter.syllabus_date})",
        f"- Freshness: {status.status} (horizon {settings.horizon_days} days)",
    ]
    if status.newer_than_syllabus:
        lines.append(
            "- [NEWER-THAN-SYLLABUS] newest dated document postdates the pinned syllabus version"
        )
    return lines


def _warning_lines(status: CoverageStatus) -> list[str]:
    warnings: list[str] = []
    if status.chapter.report_only:
        warnings.append(
            "thin coverage expected: this chapter uses general public sources only "
            "(course material is read in-browser and is never scraped)"
        )
    if status.status == STATUS_UNKNOWN:
        warnings.append(
            "freshness unknown: no parsed publish dates in this chapter "
            "(fetch-fallback dates are excluded from the gate)"
        )
    if status.stale:
        warnings.append(
            "STALE: newest parsed public document is older than the freshness horizon"
        )
    if status.doc_count < MIN_THIN_DOCS:
        warnings.append(f"thin coverage: only {status.doc_count} public document(s) indexed")
    return warnings


def export_notebook(
    store: StudyStore,
    chapter: Chapter,
    settings: Settings,
    now: datetime | None = None,
) -> Path:
    """Write one NotebookLM-ready Markdown study pack for a chapter."""

    status = _chapter_status(store, chapter, settings, now)
    lines: list[str] = [f"<!-- OWNERSHIP: {OWNERSHIP_NOTEBOOK} -->"]
    lines += _header_lines(status, settings)
    lines.append("")

    warnings = _warning_lines(status)
    lines.append("## Warnings")
    lines += [f"- {warning}" for warning in warnings] if warnings else ["- none"]
    lines.append("")

    lines.append("## Key data points")
    series = store.indicator_series(chapter.id)
    if series:
        latest: dict[str, tuple[str, float, str | None]] = {}
        for row in series:
            latest[str(row["name"])] = (
                str(row["period"]),
                float(row["value"]),
                str(row["unit"]) if row["unit"] else None,
            )
        for name in sorted(latest):
            period, value, unit = latest[name]
            unit_text = f" {unit}" if unit else ""
            lines.append(f"- Latest {name}: {value}{unit_text} ({period})")
    else:
        lines.append("- no numeric indicators stored yet")
    lines.append("")

    lines.append("## Dated source links (newest first)")
    public_docs = store.documents_for_chapter(chapter.id, source_type="public", limit=50)
    if public_docs:
        for row in public_docs:
            dated = row["doc_date"] or str(row["fetched_at"])[:10]
            lines.append(f"- {dated} -- {row['title']} -- {row['url']}")
    else:
        lines.append("- no public documents stored yet")
    lines.append("")

    lines.append("## My notes")
    notes = store.documents_for_chapter(chapter.id, source_type="my-notes")
    if notes:
        for row in notes:
            lines.append(f"### {row['title']}")
            lines.append("")
            lines.append(str(row["content"]) or "_(empty)_")
            lines.append("")
    else:
        lines.append("_No inbox notes ingested for this chapter yet._")
        lines.append("")

    out_dir = settings.exports_dir / "notebook"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ch{chapter.id}_{_slug(chapter.name)}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _render_series_chart(
    points: list[tuple[str, float]], title: str, out_png: Path
) -> bool:
    """Render a simple public-data line chart; returns False when unavailable."""

    if len(points) < 2:
        return False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - matplotlib is a declared dependency
        return False

    xs = [date.fromisoformat(period) for period, _ in points]
    ys = [value for _, value in points]
    figure, axes = plt.subplots(figsize=(8, 4), dpi=120)
    axes.plot(xs, ys, marker="o", linewidth=1.5, color="#045498")
    axes.set_title(title)
    axes.grid(True, alpha=0.3)
    figure.autofmt_xdate()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_png, bbox_inches="tight")
    plt.close(figure)
    return True


def export_portfolio(
    store: StudyStore,
    chapter: Chapter,
    settings: Settings,
    now: datetime | None = None,
) -> Path:
    """Public-data-only charts + my analysis. No verbatim text, no PDFs."""

    status = _chapter_status(store, chapter, settings, now)
    lines: list[str] = [f"<!-- OWNERSHIP: {OWNERSHIP_PORTFOLIO} -->"]
    lines += _header_lines(status, settings)
    lines.append("")
    lines.append(
        "> Public-data-only export: charts and numeric tables from bi.go.id "
        "plus my own analysis. Zero course-verbatim text, zero third-party PDFs."
    )
    lines.append("")

    warnings = _warning_lines(status)
    if warnings:
        lines.append("## Warnings")
        lines += [f"- {warning}" for warning in warnings]
        lines.append("")

    chart_dir = settings.exports_dir / "portfolio"
    chart_dir.mkdir(parents=True, exist_ok=True)

    lines.append("## Charts")
    series = store.indicator_series(chapter.id)
    by_name: dict[str, list[tuple[str, float]]] = {}
    for row in series:
        by_name.setdefault(str(row["name"]), []).append(
            (str(row["period"]), float(row["value"]))
        )
    chart_count = 0
    for name in sorted(by_name):
        points = sorted(by_name[name], key=lambda item: item[0])
        chart_path = chart_dir / f"ch{chapter.id}_{_slug(name)}.png"
        if _render_series_chart(points, f"{name} - chapter {chapter.id}", chart_path):
            lines.append(f"![{name}]({chart_path.name})")
            chart_count += 1
    if chart_count == 0:
        lines.append("_No chartable indicator series stored yet._")
    lines.append("")

    lines.append("## Data table")
    if series:
        lines.append("| Period | Indicator | Value | Unit |")
        lines.append("| :--- | :--- | ---: | :--- |")
        for row in series:
            unit = row["unit"] or ""
            lines.append(
                f"| {row['period']} | {row['name']} | {row['value']} | {unit} |"
            )
    else:
        lines.append("_No indicator rows stored yet._")
    lines.append("")

    lines.append("## My analysis")
    notes = store.documents_for_chapter(chapter.id, source_type="my-notes")
    if notes:
        for row in notes:
            lines.append(f"### {row['title']}")
            lines.append("")
            lines.append(str(row["content"]) or "_(empty)_")
            lines.append("")
    else:
        lines.append("_Add analysis after reading the chapter (data/inbox). _")
        lines.append("")

    lines.append("## Sources (public, bi.go.id)")
    seen: list[str] = []
    for row in store.documents_for_chapter(chapter.id, source_type="public"):
        url = str(row["url"])
        if url not in seen:
            seen.append(url)
    lines += [f"- {url}" for url in seen] if seen else ["- none stored yet"]
    lines.append("")

    out_path = chart_dir / f"ch{chapter.id}_{_slug(chapter.name)}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
