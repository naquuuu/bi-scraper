# OWNERSHIP: tooling
"""Offline fetch pipeline tests (httpx.MockTransport only, zero live hits)."""

from __future__ import annotations

import dataclasses
import random
from datetime import date

import httpx

from bi_scraper.chapter_map import get_chapter
from bi_scraper.cli import FetchSummary, _fetch_bi_rate_form, run_fetch
from bi_scraper.http_client import AllowAllRobots, PoliteClient
from bi_scraper.sources import KIND_BI_RATE_FORM, sources_for_chapter


def _offline_client(settings, handler) -> PoliteClient:
    return PoliteClient(
        settings=settings,
        transport=httpx.MockTransport(handler),
        sleep=lambda seconds: None,
        rng=random.Random(3),
        robots_gate=AllowAllRobots(),
    )


def test_bi_rate_form_fetch_offline(store, settings, fixture_text):
    settings = dataclasses.replace(settings, max_pages=1)
    source = sources_for_chapter(2)[0]
    assert source.kind == KIND_BI_RATE_FORM
    html = fixture_text("bi_rate_form.html")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    summary = FetchSummary(
        chapter=2, name=source.name, mode="incremental", start="2026-08-01", end="2026-09-01"
    )
    _fetch_bi_rate_form(
        store=store,
        settings=settings,
        client=_offline_client(settings, handler),
        source=source,
        chapter=get_chapter(2),
        start=date(2026, 8, 1),
        end=date(2026, 9, 1),
        summary=summary,
    )
    assert summary.fetched == 2  # 22 July row is outside the requested window
    assert len(store.indicator_series(2, "BI-Rate")) == 2
    assert len(store.documents_for_chapter(2, source_type="public")) == 2
    assert (settings.raw_dir / "ch2").is_dir()


def test_bi_rate_form_fetch_includes_full_window(store, settings, fixture_text):
    settings = dataclasses.replace(settings, max_pages=1)
    source = sources_for_chapter(2)[0]
    html = fixture_text("bi_rate_form.html")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    summary = FetchSummary(
        chapter=2, name=source.name, mode="full", start="2026-07-01", end="2026-09-01"
    )
    _fetch_bi_rate_form(
        store=store,
        settings=settings,
        client=_offline_client(settings, handler),
        source=source,
        chapter=get_chapter(2),
        start=date(2026, 7, 1),
        end=date(2026, 9, 1),
        summary=summary,
    )
    assert summary.fetched == 3
    assert len(store.indicator_series(2, "BI-Rate")) == 3
    assert len(store.documents_for_chapter(2, source_type="public")) == 3


def test_run_fetch_incremental_up_to_date_short_circuits(store, settings):
    store.add_document(
        chapter=7, url="https://www.bi.go.id/x", title="existing", doc_date="2026-09-01"
    )

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no HTTP request expected when up to date")

    summaries = run_fetch(
        store=store,
        settings=settings,
        chapters=[get_chapter(7)],
        start=None,
        end=date(2026, 9, 1),
        full=False,
        client=_offline_client(settings, handler),
    )
    assert summaries[0].fetched == 0
    assert "up to date" in summaries[0].note


def test_run_fetch_page_chapter_offline(store, settings, fixture_text):
    html = fixture_text("sample_page.html")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    summaries = run_fetch(
        store=store,
        settings=settings,
        chapters=[get_chapter(7)],
        start=None,
        end=date(2026, 9, 17),
        full=False,
        client=_offline_client(settings, handler),
    )
    assert summaries[0].fetched == 3  # three ch7 page sources
    assert summaries[0].failures == []
    assert store.last_fetch_at(7) is not None
    assert store.doc_count(7, source_type="public") == 3
    # page docs have no dated source; freshness falls back to fetched_at
    assert store.newest_public_date(7) is not None


def test_run_fetch_full_ignores_stored_newest(store, settings, fixture_text):
    store.add_document(
        chapter=7, url="https://www.bi.go.id/x", title="existing", doc_date="2026-09-01"
    )
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, text=fixture_text("sample_page.html"))

    summaries = run_fetch(
        store=store,
        settings=settings,
        chapters=[get_chapter(7)],
        start=None,
        end=date(2026, 9, 10),
        full=True,
        client=_offline_client(settings, handler),
    )
    assert calls["count"] == 3
    assert summaries[0].mode == "full"
    assert summaries[0].start == "2016-01-01"
