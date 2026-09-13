"""Unit tests for the browser-tier retry engine (ROADMAP.md §2d, Phase 3.5).

The `.feature` scenarios exercise browser navigation retry end-to-end through a
real browser and a flaky server; these probe `RetryingNavigator`'s classification
and backoff directly with a fake navigation callable — the categories (success /
transient / permanent), the transient-*exception* path (which a live browser
can't be made to raise on demand), attempt counting, the Retry-After honoring,
the backoff, and the same-document (None response) case. `RetryingNavigator`
shares its classification and backoff with `RetryingFetcher`; these focus on the
navigation-specific surface rather than re-testing the shared helpers.
"""

from __future__ import annotations

from collections.abc import Callable

from spoor.core.config import RetryPolicy
from spoor.operational.retry import (
    _MAX_RETRY_AFTER_SECONDS,
    FetchFailure,
    RetryingNavigator,
    _NavResponse,
)

_URL = "http://example.test/page"


class _FakeResponse:
    """A stand-in for Playwright's navigation `Response` — the `_NavResponse` slice."""

    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self._status = status
        # header_value is case-insensitive; store lower-cased for a simple lookup.
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    @property
    def status(self) -> int:
        return self._status

    def header_value(self, name: str) -> str | None:
        return self._headers.get(name.lower())


class _NavTimeout(Exception):
    """A navigation exception whose class name marks it a timeout (see _nav_reason)."""


class _NavError(Exception):
    """A generic navigation transport exception (dropped/refused connection)."""


_TRANSIENT = (_NavTimeout, _NavError)


def _navigator(
    policy: RetryPolicy | None = None,
) -> tuple[RetryingNavigator, list[float]]:
    """A navigator plus the list its backoff sleeps land in."""
    sleeps: list[float] = []
    navigator = RetryingNavigator(policy or RetryPolicy(), sleep=sleeps.append)
    return navigator, sleeps


def _scripted(
    entries: list[_NavResponse | None | Exception],
) -> Callable[[], _NavResponse | None]:
    """A go() returning (or raising) the Nth entry on the Nth call; last repeats."""
    calls = {"n": 0}

    def go() -> _NavResponse | None:
        entry = entries[min(calls["n"], len(entries) - 1)]
        calls["n"] += 1
        if isinstance(entry, Exception):
            raise entry
        return entry

    return go


def _navigate(
    navigator: RetryingNavigator, go: Callable[[], _NavResponse | None]
) -> _NavResponse | None | FetchFailure:
    return navigator.navigate(go, _URL, transient_exceptions=_TRANSIENT)


def test_a_success_returns_the_response_without_retrying() -> None:
    navigator, sleeps = _navigator()
    ok = _FakeResponse(200)
    result = _navigate(navigator, _scripted([ok]))
    assert result is ok
    assert navigator.retries == 0
    assert sleeps == []


def test_a_none_response_is_a_success_with_nothing_to_inspect() -> None:
    # A same-document navigation returns no Response; treat it as a (no-retry)
    # success rather than a failure — there is simply no status to classify.
    navigator, sleeps = _navigator()
    assert _navigate(navigator, _scripted([None])) is None
    assert navigator.retries == 0
    assert sleeps == []


def test_a_transient_status_is_retried_then_succeeds() -> None:
    navigator, sleeps = _navigator()
    ok = _FakeResponse(200)
    result = _navigate(navigator, _scripted([_FakeResponse(503), ok]))
    assert result is ok
    assert navigator.retries == 1
    assert sleeps == [0.5]  # base * 2**0


def test_an_exhausted_transient_status_is_dead_lettered() -> None:
    navigator, sleeps = _navigator()
    result = _navigate(navigator, _scripted([_FakeResponse(503)]))
    assert isinstance(result, FetchFailure)
    assert result.reason == "server error (503)"
    assert result.status == 503
    assert result.attempts == 3  # 1 + default max_retries (2)
    assert navigator.retries == 2
    assert sleeps == [0.5, 1.0]


def test_a_permanent_status_is_not_retried() -> None:
    navigator, sleeps = _navigator()
    result = _navigate(navigator, _scripted([_FakeResponse(404)]))
    assert isinstance(result, FetchFailure)
    assert result.reason == "client error (404)"
    assert result.status == 404
    assert result.attempts == 1
    assert navigator.retries == 0
    assert sleeps == []


def test_a_429_is_treated_as_transient() -> None:
    navigator, _ = _navigator()
    ok = _FakeResponse(200)
    assert _navigate(navigator, _scripted([_FakeResponse(429), ok])) is ok


def test_a_navigation_timeout_is_transient_and_classified() -> None:
    navigator, _ = _navigator()
    result = _navigate(navigator, _scripted([_NavTimeout("slow")]))
    assert isinstance(result, FetchFailure)
    assert result.reason == "navigation timeout"
    assert result.status is None


def test_a_navigation_error_is_transient_and_classified() -> None:
    navigator, _ = _navigator()
    result = _navigate(navigator, _scripted([_NavError("refused")]))
    assert isinstance(result, FetchFailure)
    assert result.reason == "navigation error"
    assert result.status is None


def test_a_transient_exception_is_retried_then_succeeds() -> None:
    navigator, sleeps = _navigator()
    ok = _FakeResponse(200)
    result = _navigate(navigator, _scripted([_NavTimeout("slow"), ok]))
    assert result is ok
    assert navigator.retries == 1
    assert sleeps == [0.5]


def test_max_retries_zero_disables_retrying() -> None:
    navigator, sleeps = _navigator(RetryPolicy(max_retries=0))
    result = _navigate(navigator, _scripted([_FakeResponse(503)]))
    assert isinstance(result, FetchFailure)
    assert result.attempts == 1
    assert navigator.retries == 0
    assert sleeps == []


def test_retry_after_header_is_honored_over_backoff() -> None:
    navigator, sleeps = _navigator()
    ok = _FakeResponse(200)
    go = _scripted([_FakeResponse(503, {"Retry-After": "7"}), ok])
    assert _navigate(navigator, go) is ok
    assert sleeps == [7.0]  # the header, not the 0.5 default backoff


def test_retry_after_header_is_capped() -> None:
    navigator, sleeps = _navigator()
    ok = _FakeResponse(200)
    go = _scripted([_FakeResponse(503, {"Retry-After": "99999"}), ok])
    assert _navigate(navigator, go) is ok
    assert sleeps == [_MAX_RETRY_AFTER_SECONDS]


def test_retry_after_is_ignored_when_the_policy_opts_out() -> None:
    navigator, sleeps = _navigator(RetryPolicy(respect_retry_after=False))
    ok = _FakeResponse(200)
    go = _scripted([_FakeResponse(503, {"Retry-After": "7"}), ok])
    assert _navigate(navigator, go) is ok
    assert sleeps == [0.5]  # falls back to backoff


def test_retries_accumulate_across_navigations() -> None:
    # The counter spans the whole run's navigations (a paginated crawl navigates
    # several times), mirroring the fetcher's per-run retry count.
    navigator, _ = _navigator()
    ok = _FakeResponse(200)
    _navigate(navigator, _scripted([_FakeResponse(503), ok]))
    _navigate(navigator, _scripted([_FakeResponse(503), ok]))
    assert navigator.retries == 2
