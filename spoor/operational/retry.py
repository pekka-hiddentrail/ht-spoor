"""Tier-1 fetch retry + error classification (ROADMAP.md §2d, Phase 3.5).

A crawl meets flaky servers. This module classifies each tier-1 fetch outcome
into three generic HTTP categories — success, a *transient* failure worth a
bounded retry (timeouts, dropped connections, 5xx, 429), and a *permanent* one
that retrying only wastes politeness budget on (other 4xx) — and drives the
retry with exponential backoff, honoring a `Retry-After` the server sends. A URL
that exhausts its retries or fails permanently becomes a `FetchFailure` the
caller records in its dead-letter log, rather than crashing the run on it.

Classification is by HTTP category alone — nothing site-specific (§0). Scope is
the sequential tier-1 httpx fetch path; browser-tier navigation retry is a
follow-on (see the ROADMAP §2d decision note). The `Retry-After` honoring here
is the item the `PolitenessPolicy` docstring deferred "until a retry mechanism
exists".
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx

from spoor.core.config import RetryPolicy

# A server-sent Retry-After is honored, but capped so a hostile or mistaken
# header (e.g. "Retry-After: 86400") can't freeze a run for hours. The *number*
# of waits is already bounded by max_retries; this bounds each wait's duration.
_MAX_RETRY_AFTER_SECONDS = 120.0

_Kind = Literal["success", "transient", "permanent"]


@dataclass(frozen=True)
class FetchFailure:
    """A URL the retrying fetcher could not fetch, for the dead-letter log (§2d).

    `reason` is a generic HTTP category ("server error (503)", "timeout",
    "client error (404)", ...), never anything site-specific (§0) or a captured
    secret (§2h). `status` is the last HTTP status seen, or None for a transport
    failure (timeout / dropped connection, where no response arrived). `attempts`
    is how many tries were made — 1 for a permanent error taken at its word, up
    to `1 + max_retries` for an exhausted transient one.
    """

    url: str
    reason: str
    status: int | None
    attempts: int


def _classify(response: httpx.Response) -> tuple[_Kind, str, int]:
    """Classify a response by HTTP status into (kind, reason, status).

    2xx/3xx succeed (httpx has already followed redirects on the owned client);
    429 and 5xx are transient (worth retrying); every other 4xx is permanent.
    The reason strings are the stable, generic labels the dead-letter log and the
    run summary surface — no site-specific wording (§0).
    """
    status = response.status_code
    if status < 400:
        return "success", "", status
    if status == 429:
        return "transient", "rate limited (429)", status
    if status >= 500:
        return "transient", f"server error ({status})", status
    return "permanent", f"client error ({status})", status


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Seconds to wait per a `Retry-After` header, or None if absent/unparseable.

    RFC 9110 allows either a delay in seconds or an HTTP-date; both are handled,
    the date form as a delta from now (never negative). An unparseable value
    yields None so the caller falls back to its normal backoff.
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:  # parsedate_to_datetime can return None on a bad date
        return None
    # A date with no zone parses naive; treat it as UTC so the subtraction below
    # can't raise a naive/aware TypeError (HTTP-dates are GMT, but be defensive).
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - datetime.now(UTC)).total_seconds(), 0.0)


class RetryingFetcher:
    """Fetches URLs for the tier-1 crawl, retrying transient failures (§2d).

    Bounded by the `RetryPolicy`: at most `max_retries` retries after the first
    attempt, spaced by exponential backoff (`backoff * 2**n`) unless the server
    sent a `Retry-After` and the policy honors it. `sleep` is injectable so the
    backoff can be asserted in tests without real waiting — the same seam the
    politeness gate uses. `retries` accumulates the retry attempts made across
    every `get` of the run, for the run summary's reliability line.
    """

    def __init__(
        self,
        client: httpx.Client,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._policy = policy
        self._sleep = sleep
        self.retries = 0

    def get(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> httpx.Response | FetchFailure:
        """Fetch `url`, retrying transient failures; a success or a FetchFailure.

        Returns the `Response` on the first 2xx/3xx, a `FetchFailure` immediately
        on a permanent (non-429 4xx) error, and a `FetchFailure` after exhausting
        retries on a transient one. It never raises for a classified HTTP or
        transport failure — that is the whole point, replacing the bare
        `raise_for_status()` that used to crash a run on the first 500.

        `headers` are extra request headers for every attempt — used by change
        detection to send conditional `If-None-Match` / `If-Modified-Since`
        validators, so a 304 comes back as an ordinary (3xx, unretried) success.
        """
        attempt = 0
        while True:
            attempt += 1
            retry_after: float | None = None
            try:
                response = self._client.get(url, headers=headers)
            except httpx.TimeoutException:
                # TimeoutException subclasses TransportError, so catch it first.
                kind, reason, status = "transient", "timeout", None
            except httpx.TransportError:
                kind, reason, status = "transient", "connection error", None
            else:
                kind, reason, status = _classify(response)
                if kind == "success":
                    return response
                if kind == "transient":
                    retry_after = _parse_retry_after(response)

            if kind == "permanent" or attempt > self._policy.max_retries:
                return FetchFailure(
                    url=url, reason=reason, status=status, attempts=attempt
                )
            self.retries += 1
            self._sleep(self._wait(attempt, retry_after))

    def _wait(self, attempt: int, retry_after: float | None) -> float:
        """Seconds to sleep before the next attempt: honored Retry-After or backoff.

        A server-sent Retry-After (when honored) wins over the exponential
        backoff, capped so a hostile value can't freeze the run; otherwise the
        wait grows as `backoff * 2**(attempt-1)`.
        """
        if retry_after is not None and self._policy.respect_retry_after:
            return min(retry_after, _MAX_RETRY_AFTER_SECONDS)
        return self._policy.backoff * (2 ** (attempt - 1))
