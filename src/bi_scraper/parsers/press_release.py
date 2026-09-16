# OWNERSHIP: public-derived
"""Press-release / publication listing parser.

Metadata only: ``{date, title, url, doc_type}``. PDFs are never downloaded and
no PDF-secure / login / paywall protection is ever touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from .bi_rate import BI_BASE_URL, normalise_href, parse_period


@dataclass(frozen=True)
class PressReleaseMeta:
    date: date | None
    title: str
    url: str
    doc_type: str  # "pdf" | "page"


def _is_publication_url(url: str) -> bool:
    if ".pdf" in url.lower():
        return True
    lowered = url.lower()
    return "/news-release/pages/" in lowered and lowered.endswith(".aspx")


def parse_press_release_listing(
    html: str, base_url: str = BI_BASE_URL
) -> list[PressReleaseMeta]:
    """Extract dated publication links, newest first (undated entries last)."""

    soup = BeautifulSoup(html, "lxml")
    found: dict[str, PressReleaseMeta] = {}
    for anchor in soup.find_all("a", href=True):
        url = normalise_href(str(anchor["href"]), base_url)
        if not _is_publication_url(url):
            continue
        title = anchor.get_text(" ", strip=True)
        container = anchor.find_parent(["li", "article", "div", "tr"]) or anchor
        context = container.get_text(" ", strip=True)
        doc_date = parse_period(context)
        if len(title) < 4:
            heading = container.find(["h2", "h3", "h4", "h5"])
            if heading is not None:
                title = heading.get_text(" ", strip=True)
        if len(title) < 4:
            title = url.rsplit("/", 1)[-1]
        if url in found:
            continue
        found[url] = PressReleaseMeta(
            date=doc_date,
            title=title,
            url=url,
            doc_type="pdf" if url.lower().endswith(".pdf") else "page",
        )

    dated = [item for item in found.values() if item.date is not None]
    undated = [item for item in found.values() if item.date is None]
    dated.sort(key=lambda item: item.date, reverse=True)  # type: ignore[arg-type,return-value]
    return dated + undated
