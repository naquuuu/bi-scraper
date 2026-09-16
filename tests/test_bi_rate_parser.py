# OWNERSHIP: public-derived
"""BI-Rate form/table parsing against the trimmed real-page fixture."""

from __future__ import annotations

from datetime import date

from bi_scraper.parsers.bi_rate import (
    build_page_payload,
    build_search_payload,
    extract_form_state,
    find_next_page_target,
    normalise_href,
    parse_period,
    parse_rate,
    parse_rate_rows,
)

TARGET = "ctl00$ctl54$g_2cf3ee94_31d3_4970_bba5_ec3766a63c9a$ctl00$DataPagerBI7DRR$ctl01$ctl01"


def test_extract_form_state_resolves_real_control_names(fixture_text):
    state = extract_form_state(fixture_text("bi_rate_form.html"))
    assert state.controls["date_start"].endswith("$TextBoxDateStart")
    assert state.controls["date_end"].endswith("$TextBoxDateEnd")
    assert state.controls["hidden_from"].endswith("$HiddenFieldDateFrom")
    assert state.controls["hidden_to"].endswith("$HiddenFieldDateTo")
    assert state.controls["button"].endswith("$ButtonSearch")
    assert state.hidden["__VIEWSTATE"].startswith("/wEP")
    assert "__EVENTVALIDATION" in state.hidden
    assert "__REQUESTDIGEST" in state.hidden


def test_build_search_payload_sets_visible_and_hidden_dates(fixture_text):
    state = extract_form_state(fixture_text("bi_rate_form.html"))
    payload = build_search_payload(state, date(2026, 8, 1), date(2026, 9, 1))
    assert payload[state.controls["date_start"]] == "01/08/2026"
    assert payload[state.controls["date_end"]] == "01/09/2026"
    assert payload[state.controls["hidden_from"]] == "01/08/2026"
    assert payload[state.controls["hidden_to"]] == "01/09/2026"
    assert payload[state.controls["button"]] == "Search"


def test_build_page_payload_targets_datapager(fixture_text):
    state = extract_form_state(fixture_text("bi_rate_form.html"))
    payload = build_page_payload(state, TARGET)
    assert payload["__EVENTTARGET"] == TARGET
    assert payload["__EVENTARGUMENT"] == ""


def test_parse_rate_rows_with_commented_bi7day_column(fixture_text):
    rows = parse_rate_rows(fixture_text("bi_rate_form.html"))
    assert len(rows) == 3
    first = rows[0]
    assert first.no == 1
    assert first.period == date(2026, 8, 19)
    assert first.rate_percent == 5.75
    assert first.press_url == (
        "https://www.bi.go.id/id/publikasi/ruang-media/news-release/Pages/sp_2816226.aspx"
    )
    assert rows[1].press_url.startswith("https://www.bi.go.id/en/")
    assert rows[2].period == date(2026, 8, 18)
    assert rows[2].rate_percent == 5.50
    assert rows[2].press_url.endswith("sp_2812626.aspx")  # fragment stripped


def test_parse_rate_rows_with_bi7day_column_present():
    html = """
    <div id="tableData">
      <table class="table">
        <tbody>
          <tr>
            <th>1</th><td>19 August 2026</td><td>5.00 %</td><td>5.75 %</td>
            <td><a href="/en/publikasi/ruang-media/news-release/Pages/x.aspx">View</a></td>
          </tr>
        </tbody>
      </table>
    </div>
    """
    rows = parse_rate_rows(html)
    assert len(rows) == 1
    assert rows[0].period == date(2026, 8, 19)
    assert rows[0].rate_percent == 5.75  # BI-Rate, not the BI-7 Day column
    assert rows[0].press_url == (
        "https://www.bi.go.id/en/publikasi/ruang-media/news-release/Pages/x.aspx"
    )


def test_find_next_page_target(fixture_text):
    assert find_next_page_target(fixture_text("bi_rate_form.html")) == TARGET


def test_find_next_page_target_none_without_pagination():
    html = '<div id="tableData"><table class="table"><tbody></tbody></table></div>'
    assert find_next_page_target(html) is None


def test_normalise_href_strips_fragment_and_absolutises():
    assert normalise_href("/id/x/Pages/y.aspx#top") == "https://www.bi.go.id/id/x/Pages/y.aspx"
    assert normalise_href("https://www.bi.go.id/en/z.aspx") == "https://www.bi.go.id/en/z.aspx"


def test_parse_period_and_rate_edge_cases():
    assert parse_period("garbage") is None
    assert parse_period("31 February 2026") is None
    assert parse_rate("no percentage here") is None
    assert parse_rate("5,50 %") == 5.50
