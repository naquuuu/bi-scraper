# OWNERSHIP: public-derived
"""Generic page text/table extraction (JISDOR-style numeric tables)."""

from __future__ import annotations

from datetime import date

from bi_scraper.parsers.generic import parse_indicator_rows, parse_number, parse_page


def test_parse_page_strips_navigation_and_scripts(fixture_text):
    content = parse_page(fixture_text("sample_page.html"))
    assert content.title == "Inflasi"
    assert "Informasi inflasi" in content.text
    assert "menu noise" not in content.text
    assert "var noise" not in content.text
    assert "footer noise" not in content.text


def test_parse_number_handles_indonesian_and_english_formats():
    assert parse_number("16.318,00") == 16318.0
    assert parse_number("16.290,00") == 16290.0
    assert parse_number("16.318") == 16318.0
    assert parse_number("5.75") == 5.75
    assert parse_number("2,5") == 2.5
    assert parse_number("") is None


def test_parse_indicator_rows_skips_row_number_column(fixture_text):
    content = parse_page(fixture_text("jisdor.html"))
    rows = parse_indicator_rows(content)
    assert [(period, value) for _, period, value in rows] == [
        (date(2026, 9, 16), 16318.0),
        (date(2026, 9, 15), 16290.0),
    ]


def test_parse_indicator_rows_parses_slash_dates():
    html = """
    <h1 id="pageTitle">Kurs</h1>
    <table>
      <thead><tr><th>No</th><th>Date</th><th>Kurs</th></tr></thead>
      <tbody><tr><td>1</td><td>16/09/2026</td><td>16.318</td></tr></tbody>
    </table>
    """
    rows = parse_indicator_rows(parse_page(html))
    assert rows == [("Date Kurs", date(2026, 9, 16), 16318.0)]
