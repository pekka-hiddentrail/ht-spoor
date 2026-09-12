"""Runtime politeness gate: robots.txt + crawl-delay (ROADMAP.md §2d, §6).

The declarative knobs live in `spoor.core.config.PolitenessPolicy`; this module
is the runtime that enforces them against a live crawl. §6 commits Spoor to
respecting `robots.txt` and rate-limiting by default, with overriding it an
explicit opt-out. Per §0 there is nothing site-specific here — robots.txt is
fetched and parsed the same generic way for every target.

Scope (Phase 1): allow/deny checks and per-host crawl-delay spacing over the
sequential tier-1 crawl. Concurrency caps and Retry-After honoring are deferred
until a request pool / retry mechanism exists (see the ROADMAP §2d note).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from spoor.core.config import PolitenessPolicy

# The product token we present to robots.txt for user-agent matching.
USER_AGENT = "spoor"


class Politeness:
    """Enforces a `PolitenessPolicy` across the fetches of one run.

    Fetches and caches `robots.txt` per origin (scheme + host) on first need,
    answers `can_fetch`, and spaces requests via `before_fetch` using an
    injectable `sleep` (so tests can assert timing without real waiting).
    """

    def __init__(
        self,
        policy: PolitenessPolicy,
        client: httpx.Client,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._policy = policy
        self._client = client
        self._sleep = sleep
        self._robots: dict[tuple[str, str], RobotFileParser] = {}
        self._fetched_any = False

    def _parser(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        origin = (parts.scheme, parts.netloc)
        cached = self._robots.get(origin)
        if cached is not None:
            return cached
        parser = RobotFileParser()
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            response = self._client.get(robots_url)
        except httpx.HTTPError:
            response = None
        # An empty ruleset (absent/unreadable robots.txt) allows everything.
        if response is not None and response.status_code == 200:
            parser.parse(response.text.splitlines())
        else:
            parser.parse([])
        self._robots[origin] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        """Whether robots.txt permits fetching `url` (always True when opted out)."""
        if not self._policy.respect_robots:
            return True
        return self._parser(url).can_fetch(USER_AGENT, url)

    def crawl_delay(self, url: str) -> float:
        """Seconds to wait before fetching `url`.

        An explicit config `delay` wins; otherwise the robots.txt crawl-delay
        (when robots is respected); otherwise zero.
        """
        if self._policy.delay is not None:
            return self._policy.delay
        if not self._policy.respect_robots:
            return 0.0
        declared = self._parser(url).crawl_delay(USER_AGENT)
        return float(declared) if declared is not None else 0.0

    def before_fetch(self, url: str) -> None:
        """Sleep the crawl-delay before every fetch but the first (spaces requests)."""
        delay = self.crawl_delay(url)
        if self._fetched_any and delay > 0:
            self._sleep(delay)
        self._fetched_any = True
