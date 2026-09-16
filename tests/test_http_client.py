# OWNERSHIP: tooling
"""Polite client behavior: throttle, UA rotation, retries, host allowlist."""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from bi_scraper.http_client import (
    AllowAllRobots,
    ForbiddenSourceError,
    PoliteClient,
    RobotsDisallowedError,
    USER_AGENTS,
)


class CyclingRng:
    """Deterministic rng: zero jitter, cycling user-agent choices."""

    def __init__(self, user_agents: list[str]) -> None:
        self._user_agents = list(user_agents)
        self._index = 0

    def uniform(self, low: float, high: float) -> float:  # noqa: ARG002
        return 0.0

    def choice(self, seq: list[str]) -> str:
        value = self._user_agents[self._index % len(self._user_agents)]
        self._index += 1
        return value


class DenyAllRobots:
    def allowed(self, url: str, user_agent: str) -> bool:  # noqa: ARG002
        return False


def make_client(handler, settings, sleeps, *, rng=None, robots=None) -> PoliteClient:
    return PoliteClient(
        settings=settings,
        transport=httpx.MockTransport(handler),
        sleep=lambda seconds: sleeps.append(seconds),
        rng=rng or CyclingRng(list(USER_AGENTS[:2])),
        robots_gate=robots or AllowAllRobots(),
    )


def test_throttle_applies_min_delay_plus_jitter(settings):
    settings = replace(settings, min_delay=2.0, jitter=1.0)
    sleeps: list[float] = []
    client = make_client(lambda request: httpx.Response(200, text="ok"), settings, sleeps)
    client.get("https://www.bi.go.id/id/a")
    client.get("https://www.bi.go.id/id/b")
    assert sleeps[0] == pytest.approx(2.0)
    assert sleeps[1] > 1.5


def test_user_agent_rotation(settings):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, text="ok")

    client = make_client(handler, settings, [], rng=CyclingRng([USER_AGENTS[0], USER_AGENTS[1]]))
    client.get("https://www.bi.go.id/id/a")
    client.get("https://www.bi.go.id/id/b")
    assert seen == [USER_AGENTS[0], USER_AGENTS[1]]


def test_retries_on_server_error(settings):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        status = 500 if calls["count"] == 1 else 200
        return httpx.Response(status, text="x")

    sleeps: list[float] = []
    client = make_client(handler, settings, sleeps)
    response = client.get("https://www.bi.go.id/id/a")
    assert response.status_code == 200
    assert calls["count"] == 2
    assert 1.0 in sleeps


def test_no_retry_on_client_error(settings):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, text="missing")

    client = make_client(handler, settings, [])
    assert client.get("https://www.bi.go.id/id/missing").status_code == 404
    assert calls["count"] == 1


def test_timeout_retries_then_raises(settings):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.TimeoutException("boom", request=request)

    client = make_client(handler, settings, [])
    with pytest.raises(httpx.TimeoutException):
        client.get("https://www.bi.go.id/id/slow")
    assert calls["count"] == 3  # initial attempt + 2 retries


def test_forbidden_hosts_are_refused(settings):
    client = make_client(lambda request: httpx.Response(200, text="x"), settings, [])
    with pytest.raises(ForbiddenSourceError):
        client.get("https://pejuang.berkarirbi.id/modul")
    with pytest.raises(ForbiddenSourceError):
        client.get("https://example.com/")


def test_robots_disallowed_raises(settings):
    client = make_client(
        lambda request: httpx.Response(200, text="x"), settings, [], robots=DenyAllRobots()
    )
    with pytest.raises(RobotsDisallowedError):
        client.get("https://www.bi.go.id/id/a")
