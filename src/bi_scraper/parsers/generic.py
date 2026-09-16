# OWNERSHIP: public-derived
"""Generic public page text/table extraction (JISDOR, SPIP, profile pages)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from .bi_rate import parse_period

_WHITESPACE_RE = re.compile(r"\s+")
_DIGIT_DATE_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
_SKIP_HEADER_CELLS = {"no", "no.", "#", "nomor", "number"}


def _parse_table_date(text: str) -> date | None:
    """Parse table dates: ``dd Month yyyy`` first, then ``dd/mm/yyyy``."""

    candidate = parse_period(text)
    if candidate is not None:
        return candidate
    match = _DIGIT_DATE_RE.search(text or "")
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass(frozen=True)
class PageContent:
    title: str
    text: str
    tables: tuple[tuple[tuple[str, ...], ...], ...]


def parse_page(html: str, url: str = "") -> PageContent:
    """Extract title, readable text and tables from a public page."""

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "header", "footer"]):
        tag.decompose()

    title = ""
    heading = soup.select_one("h1#pageTitle")
    if heading is not None:
        title = heading.get_text(" ", strip=True)
    if not title:
        title_tag = soup.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag is not None else url

    text = _WHITESPACE_RE.sub(" ", soup.get_text(" ", strip=True)).strip()

    tables: list[tuple[tuple[str, ...], ...]] = []
    for table in soup.find_all("table"):
        rows: list[tuple[str, ...]] = []
        for tr in table.find_all("tr"):
            cells = tuple(cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"]))
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(tuple(rows))
    return PageContent(title=title, text=text, tables=tuple(tables))


def parse_number(text: str) -> float | None:
    """Parse Indonesian/English formatted numbers (``16.318,00`` -> 16318.0)."""

    cleaned = re.sub(r"[^\d.,-]", "", text or "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        tail = cleaned.rsplit(",", 1)[-1]
        cleaned = cleaned.replace(",", "") if len(tail) == 3 else cleaned.replace(",", ".")
    elif cleaned.count(".") == 1:
        tail = cleaned.rsplit(".", 1)[-1]
        if len(tail) == 3 and len(cleaned.split(".")[0]) >= 1:
            cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_indicator_rows(
    content: PageContent,
) -> list[tuple[str, date | None, float]]:
    """Best-effort numeric series extraction: ``(label, period, value)`` rows.

    A table qualifies when it has a header cell mentioning date/period and at
    least two data rows; the first date-like cell provides the period and the
    first numeric cell the value.
    """

    results: list[tuple[str, date | None, float]] = []
    for table in content.tables:
        if len(table) < 2:
            continue
        header = " ".join(table[0]).lower()
        if not any(token in header for token in ("date", "tanggal", "period", "periode")):
            continue
        label = " ".join(
            cell
            for cell in table[0]
            if cell
            and not cell.strip().isdigit()
            and cell.strip().lower() not in _SKIP_HEADER_CELLS
        )
        for row in table[1:]:
            date_index: int | None = None
            period: date | None = None
            for index, cell in enumerate(row):
                candidate = _parse_table_date(cell)
                if candidate is not None:
                    date_index, period = index, candidate
                    break
            if period is None:
                continue
            value: float | None = None
            for index, cell in enumerate(row):
                if index == date_index:
                    continue
                parsed = parse_number(cell)
                if parsed is None:
                    continue
                if date_index is not None and index < date_index:
                    continue
                value = parsed
                break
            if value is None:
                continue
            results.append((label.strip() or "indicator", period, value))
    return results
