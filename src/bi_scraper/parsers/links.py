# OWNERSHIP: public-derived
"""Internal link extraction for hub crawling (same bi.go.id section only)."""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .bi_rate import normalise_href

ALLOWED_HOSTS = frozenset({"www.bi.go.id", "bi.go.id"})

SKIP_EXTENSIONS = (
    ".css",
    ".js",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".ico",
    ".zip",
    ".rar",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".mp4",
    ".mp3",
)

SKIP_PATH_FRAGMENTS = (
    "/_layouts/",
    "/style library/",
    "/lists/",
    "/_vti_bin/",
    "/sosial media/",
    "/siteassets/logo",
    "/banner",
    "/menu image",
    "/id/archive",
    "/id/minisite",
)


def is_crawlable(url: str, prefix: str) -> bool:
    """True when the URL is an in-section, link-followable public page."""

    lowered = url.lower()
    parsed = urlparse(lowered)
    if parsed.netloc not in ALLOWED_HOSTS:
        return False
    if not parsed.path.startswith(prefix.lower()):
        return False
    if "?" in lowered:
        return False
    if lowered.endswith(SKIP_EXTENSIONS):
        return False
    if any(fragment in lowered for fragment in SKIP_PATH_FRAGMENTS):
        return False
    return True


def extract_internal_links(html: str, base_url: str, prefix: str) -> list[str]:
    """All unique crawlable links on the page, in document order."""

    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        url = normalise_href(str(anchor["href"]), base_url)
        if is_crawlable(url, prefix) and url not in found:
            found.append(url)
    return found
