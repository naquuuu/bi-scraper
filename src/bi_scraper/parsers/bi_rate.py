# OWNERSHIP: public-derived
"""BI-Rate date-range table parser (selectors reused from the bi-rate probe).

Verified against the live public page (www.bi.go.id/id/statistik/indikator/bi-rate.aspx):

- form ``#aspnetForm`` with SharePoint hidden fields (``__VIEWSTATE``,
  ``__EVENTVALIDATION``, ``__REQUESTDIGEST``, ...);
- inputs ``#TextBoxDateStart`` / ``#TextBoxDateEnd`` mirrored into
  ``#HiddenFieldDateFrom`` / ``#HiddenFieldDateTo``, submit ``#...ButtonSearch``;
- results: ``#tableData > table.table`` with rows ``tbody tr``;
- press-release hrefs come as ``/id/...`` or ``/en/...`` -> normalised via urljoin;
- the ``BI-7 Day`` column may be present, commented out, or absent (tolerated);
- pagination via ``DataPager`` ``__doPostBack`` targets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

BI_BASE_URL = "https://www.bi.go.id"
DEFAULT_PAGE_URL = "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx"

_MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "oktober": 10,
    "desember": 12,
}

_PERIOD_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
_RATE_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*%")
_POSTBACK_RE = re.compile(r"__doPostBack\(\s*'([^']+)'\s*,")
_CONTROL_IDS = {
    "date_start": "TextBoxDateStart",
    "date_end": "TextBoxDateEnd",
    "hidden_from": "HiddenFieldDateFrom",
    "hidden_to": "HiddenFieldDateTo",
    "button": "ButtonSearch",
}


class RateFormError(RuntimeError):
    """Raised when the BI-Rate search form cannot be located/parsed."""


@dataclass(frozen=True)
class RateFormState:
    hidden: dict[str, str]
    controls: dict[str, str]


@dataclass(frozen=True)
class RateRow:
    no: int | None
    period: date | None
    period_raw: str
    rate_percent: float | None
    press_url: str | None


def parse_period(text: str) -> date | None:
    """Parse ``dd Month yyyy`` (Indonesian or English month names)."""

    match = _PERIOD_RE.search(text or "")
    if not match:
        return None
    day, month_name, year = match.groups()
    month = _MONTHS.get(month_name.lower())
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def parse_rate(text: str) -> float | None:
    """Parse a percentage value such as ``5.75 %``."""

    match = _RATE_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def normalise_href(href: str, base_url: str = BI_BASE_URL) -> str:
    """Absolutise and normalise ``/id/`` vs ``/en/`` hrefs (fragment dropped)."""

    href = (href or "").strip()
    absolute = urljoin(base_url, href)
    parsed = urlsplit(absolute)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _find_control(form, element_id: str):
    """Find a form control by exact id, then by id/name suffix.

    ``TextBoxDateStart`` etc. use literal ids, while the search button id is
    prefixed (``ctl00_..._ButtonSearch``) in the real SharePoint markup.
    """

    element = form.find(id=element_id)
    if element is not None and element.get("name"):
        return element
    pattern = re.compile(rf"{re.escape(element_id)}$")
    for candidate in form.find_all("input"):
        name = candidate.get("name") or ""
        candidate_id = candidate.get("id") or ""
        if not name:
            continue
        if pattern.search(candidate_id) or pattern.search(name):
            return candidate
    return None


def extract_form_state(html: str) -> RateFormState:
    """Collect hidden fields and resolve the real control names from ids."""

    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form", id="aspnetForm") or soup.find("form")
    if form is None:
        raise RateFormError("no postback form found on the BI-Rate page")
    hidden: dict[str, str] = {}
    for inp in form.find_all("input", attrs={"type": "hidden"}):
        name = inp.get("name")
        if name:
            hidden[name] = inp.get("value") or ""
    controls: dict[str, str] = {}
    for key, element_id in _CONTROL_IDS.items():
        element = _find_control(form, element_id)
        if element is None or not element.get("name"):
            raise RateFormError(f"missing BI-Rate form control: {element_id}")
        controls[key] = str(element["name"])
    return RateFormState(hidden=hidden, controls=controls)


def _format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def build_search_payload(
    state: RateFormState, start: date, end: date
) -> dict[str, str]:
    """Build the date-range POST payload (visible + hidden date fields)."""

    payload = dict(state.hidden)
    payload[state.controls["date_start"]] = _format_date(start)
    payload[state.controls["date_end"]] = _format_date(end)
    payload[state.controls["hidden_from"]] = _format_date(start)
    payload[state.controls["hidden_to"]] = _format_date(end)
    payload[state.controls["button"]] = "Search"
    return payload


def build_page_payload(state: RateFormState, target: str) -> dict[str, str]:
    """Build a ``DataPager`` postback payload for the next result page."""

    payload = dict(state.hidden)
    payload["__EVENTTARGET"] = target
    payload["__EVENTARGUMENT"] = ""
    return payload


def parse_rate_rows(html: str, base_url: str = BI_BASE_URL) -> list[RateRow]:
    """Parse result rows, tolerant of the optional/absent ``BI-7 Day`` column."""

    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("#tableData > table.table") or soup.select_one(
        "#tableData table"
    )
    if table is None:
        return []
    rows: list[RateRow] = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        texts = [cell.get_text(" ", strip=True) for cell in cells]
        no: int | None = None
        if texts and texts[0].strip().isdigit():
            no = int(texts[0].strip())
        period_raw = ""
        period: date | None = None
        for text in texts:
            candidate = parse_period(text)
            if candidate is not None:
                period, period_raw = candidate, text
                break
        rate: float | None = None
        for text in texts:
            candidate = parse_rate(text)
            if candidate is not None:
                # BI-Rate is the last percentage column (BI-7 Day, when
                # present, comes first); the last match tolerates both layouts.
                rate = candidate
        anchor = tr.find("a", href=True)
        press_url = normalise_href(str(anchor["href"]), base_url) if anchor else None
        if period is None and rate is None and press_url is None:
            continue
        rows.append(
            RateRow(
                no=no,
                period=period,
                period_raw=period_raw,
                rate_percent=rate,
                press_url=press_url,
            )
        )
    return rows


def find_next_page_target(html: str) -> str | None:
    """Find the ``DataPager`` target for the next results page, if any.

    Multi-window pagers are followed: directly visible next page numbers win,
    otherwise the ellipsis anchor that follows the last visible page number is
    used to jump to the next pager window. The real "..." anchor carries no CSS
    class, so anchors are matched by their ``__doPostBack`` href alone.
    """

    soup = BeautifulSoup(html, "lxml")
    active_el = soup.select_one(
        ".pagination .page-link--custom.active"
    ) or soup.select_one(".page-link--custom.active")
    active: int | None = None
    if active_el is not None:
        digits = re.sub(r"\D", "", active_el.get_text())
        active = int(digits) if digits else None

    ordered: list[tuple[str, int]] = []  # (kind, index into pages/gaps)
    pages: list[tuple[int, str]] = []
    gaps: list[str] = []
    for anchor in soup.find_all("a", href=True):
        match = _POSTBACK_RE.search(str(anchor.get("href") or ""))
        if not match:
            continue
        text = anchor.get_text(strip=True)
        if text.isdigit():
            pages.append((int(text), match.group(1)))
            ordered.append(("page", len(pages) - 1))
        elif text in {"...", "..", "…"}:
            gaps.append(match.group(1))
            ordered.append(("gap", len(gaps) - 1))

    if active is not None:
        newer = [item for item in pages if item[0] > active]
        if newer:
            return min(newer, key=lambda item: item[0])[1]
        # No visible next number: jump forward via the gap that follows the
        # last visible page number (the trailing "..." of the pager window).
        last_page_pos = max(
            (pos for pos, (kind, _) in enumerate(ordered) if kind == "page"),
            default=None,
        )
        if last_page_pos is not None:
            for kind, index in ordered[last_page_pos + 1:]:
                if kind == "gap":
                    return gaps[index]
        return gaps[-1] if gaps else None

    if pages:
        return min(pages, key=lambda item: item[0])[1]
    return gaps[-1] if gaps else None
