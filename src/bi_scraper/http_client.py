# OWNERSHIP: tooling
"""Polite, bi.go.id-only HTTP client.

Politeness policy (binding):
- minimum 2s delay + jitter between requests
- randomized browser user-agent rotation
- 3s timeout, max 2 retries, exponential backoff
- robots.txt respected (cached per host)
- allowlist: only ``bi.go.id`` hosts; login-walled/paywalled sources are refused
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import Settings, get_settings

ALLOWED_HOSTS = frozenset({"bi.go.id", "www.bi.go.id"})
FORBIDDEN_HOSTS = frozenset({"pejuang.berkarirbi.id"})

USER_AGENTS = (
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
)


class ForbiddenSourceError(RuntimeError):
    """Raised when a URL points outside the public bi.go.id allowlist."""


class RobotsDisallowedError(RuntimeError):
    """Raised when robots.txt disallows fetching a URL."""


class AllowAllRobots:
    """Test double: allow every URL without touching the network."""

    def allowed(self, url: str, user_agent: str) -> bool:  # noqa: ARG002
        return True


class RobotsGate:
    """robots.txt checker with a per-host cache.

    robots.txt is fetched through the same polite client (one extra polite
    request per host). If robots.txt is unavailable, fetching proceeds, which
    matches the observed bi.go.id policy (``Allow: /``).
    """

    def __init__(self, client: "PoliteClient") -> None:
        self._client = client
        self._cache: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str, user_agent: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in self._cache:
            self._cache[host] = self._fetch(host, parsed.scheme or "https")
        parser = self._cache[host]
        if parser is None:
            return True
        return parser.can_fetch(user_agent, url)

    def _fetch(self, host: str, scheme: str) -> RobotFileParser | None:
        robots_url = f"{scheme}://{host}/robots.txt"
        try:
            response = self._client.fetch_raw(robots_url)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


class PoliteClient:
    """Thin httpx wrapper enforcing the politeness policy."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        robots_gate: object | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._rng = rng or random.Random()
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._client = httpx.Client(
            transport=transport,
            timeout=self.settings.timeout,
            follow_redirects=True,
            headers={"Accept-Language": "id-ID,id;q=0.9,en;q=0.8"},
        )
        self.robots: object = (
            robots_gate if robots_gate is not None else RobotsGate(self)
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def user_agent(self) -> str:
        """Rotate browser user agents per request."""

        return self._rng.choice(USER_AGENTS)

    def _validate(self, url: str) -> None:
        host = urlparse(url).netloc.lower().split(":")[0]
        if host in FORBIDDEN_HOSTS:
            raise ForbiddenSourceError(
                f"refused: {host} is read-in-browser only and never fetched"
            )
        if host not in ALLOWED_HOSTS:
            raise ForbiddenSourceError(
                f"refused: only public bi.go.id sources are allowed (got {host!r})"
            )

    def _throttle(self) -> None:
        wait = self.settings.min_delay + self._rng.uniform(0.0, self.settings.jitter)
        if self._last_request_at is not None:
            wait -= self._clock() - self._last_request_at
        if wait > 0:
            self._sleep(wait)
        self._last_request_at = self._clock()

    def fetch_raw(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
        user_agent: str | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Single polite attempt (used by the robots gate and by ``request``)."""

        self._throttle()
        kwargs = {} if timeout is None else {"timeout": timeout}
        return self._client.request(
            method,
            url,
            headers={"User-Agent": user_agent or self.user_agent()},
            data=data,
            **kwargs,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Fetch with robots check, retries and exponential backoff."""

        self._validate(url)
        agent = self.user_agent()
        if not self.robots.allowed(url, agent):  # type: ignore[attr-defined]
            raise RobotsDisallowedError(f"robots.txt disallows: {url}")
        attempt = 0
        while True:
            try:
                response = self.fetch_raw(
                    url, method=method, data=data, user_agent=agent, timeout=timeout
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt >= self.settings.max_retries:
                    raise
            else:
                if response.status_code < 500 or attempt >= self.settings.max_retries:
                    return response
            self._sleep(2.0**attempt)
            attempt += 1

    def get(self, url: str, timeout: float | None = None) -> httpx.Response:
        return self.request("GET", url, timeout=timeout)

    def post(
        self, url: str, data: dict[str, str], timeout: float | None = None
    ) -> httpx.Response:
        return self.request("POST", url, data=data, timeout=timeout)
