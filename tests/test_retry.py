"""Unit tests for the tier-1 retry engine (ROADMAP.md §2d, Phase 3.5).

The `.feature` scenarios exercise retry end-to-end through the dispatcher; these
probe `RetryingFetcher`'s classification and backoff directly — the categories
(success / transient / permanent), attempt counting, the Retry-After honoring
(seconds, HTTP-date, the cap, and the opt-out), and the exponential backoff — the
boundary shapes Gherkin isn't the right grain for. Plus the escalation-suppression
a dead-lettered run relies on, asserted against `_should_escalate`.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from spoor.core.config import RetryPolicy
from spoor.core.extract import RunResult, _should_escalate
from spoor.operational.retry import (
    _MAX_RETRY_AFTER_SECONDS,
    FetchFailure,
    RetryingFetcher,
    _parse_retry_after,
)

_URL = "http://example.test/page"


def _fetcher(
    handler: Callable[[httpx.Request], httpx.Response],
    policy: RetryPolicy | None = None,
) -> tuple[RetryingFetcher, list[float]]:
    """A fetcher over a MockTransport handler, plus the list its sleeps land in."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: list[float] = []
    fetcher = RetryingFetcher(client, policy or RetryPolicy(), sleep=sleeps.append)
    return fetcher, sleeps


def _scripted(
    responses: list[httpx.Response | Exception],
) -> Callable[[httpx.Request], httpx.Response]:
    """A handler returning (or raising) the Nth entry on the Nth call; last repeats."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        entry = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        if isinstance(entry, Exception):
            raise entry
        return entry

    return handler


def test_a_success_returns_the_response_without_retrying() -> None:
    fetcher, sleeps = _fetcher(_scripted([httpx.Response(200, text="ok")]))
    result = fetcher.get(_URL)
    assert isinstance(result, httpx.Response)
    assert result.text == "ok"
    assert fetcher.retries == 0
    assert sleeps == []


def test_a_redirect_status_counts_as_success() -> None:
    # 3xx is below 400: the owned client follows redirects itself, so a fetcher
    # that ever sees one treats it as a non-error and returns it (no retry).
    fetcher, _ = _fetcher(_scripted([httpx.Response(302, text="")]))
    assert isinstance(fetcher.get(_URL), httpx.Response)


def test_a_transient_error_is_retried_then_succeeds() -> None:
    fetcher, sleeps = _fetcher(
        _scripted([httpx.Response(503), httpx.Response(200, text="ok")])
    )
    result = fetcher.get(_URL)
    assert isinstance(result, httpx.Response)
    assert result.status_code == 200
    assert fetcher.retries == 1
    assert sleeps == [0.5]  # one backoff wait: base * 2**0


def test_an_exhausted_transient_error_is_dead_lettered() -> None:
    fetcher, sleeps = _fetcher(_scripted([httpx.Response(503)]))
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.reason == "server error (503)"
    assert result.status == 503
    assert result.attempts == 3  # 1 + default max_retries (2)
    assert fetcher.retries == 2
    assert sleeps == [0.5, 1.0]  # base * 2**0, base * 2**1


_CHALLENGE_BODY = (
    "<html><head><title>Just a moment...</title></head>"
    '<body><div class="cf-turnstile"></div></body></html>'
)


def test_a_challenge_behind_a_permanent_error_is_carried_on_the_failure() -> None:
    # A 403/503 often *is* a challenge interstitial: the FetchFailure carries the
    # recognized vendor (§2d) — the generic signal only, never the body (§2h).
    fetcher, _ = _fetcher(_scripted([httpx.Response(403, text=_CHALLENGE_BODY)]))
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.challenge is not None
    assert result.challenge.vendor == "Cloudflare"


def test_a_challenge_behind_an_exhausted_transient_error_is_carried() -> None:
    fetcher, _ = _fetcher(_scripted([httpx.Response(503, text=_CHALLENGE_BODY)]))
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.challenge is not None
    assert result.challenge.vendor == "Cloudflare"


def test_an_ordinary_error_body_carries_no_phantom_challenge() -> None:
    fetcher, _ = _fetcher(_scripted([httpx.Response(503, text="server on fire")]))
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.challenge is None


def test_a_transport_failure_carries_no_challenge() -> None:
    # A timeout after an earlier challenged attempt has no body to scan; the
    # per-attempt reset means the terminal failure reports None, not a stale hit.
    fetcher, _ = _fetcher(
        _scripted(
            [httpx.Response(503, text=_CHALLENGE_BODY), httpx.TimeoutException("slow")]
        )
    )
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.reason == "timeout"
    assert result.challenge is None


def test_a_permanent_error_is_not_retried() -> None:
    fetcher, sleeps = _fetcher(_scripted([httpx.Response(404)]))
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.reason == "client error (404)"
    assert result.attempts == 1
    assert fetcher.retries == 0
    assert sleeps == []


def test_a_429_is_treated_as_transient() -> None:
    fetcher, _ = _fetcher(
        _scripted([httpx.Response(429), httpx.Response(200, text="ok")])
    )
    result = fetcher.get(_URL)
    assert isinstance(result, httpx.Response)
    assert result.status_code == 200


def test_a_timeout_is_transient_and_classified() -> None:
    fetcher, _ = _fetcher(_scripted([httpx.TimeoutException("slow")]))
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.reason == "timeout"
    assert result.status is None


def test_a_connection_error_is_transient_and_classified() -> None:
    fetcher, _ = _fetcher(_scripted([httpx.ConnectError("refused")]))
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.reason == "connection error"
    assert result.status is None


def test_max_retries_zero_disables_retrying() -> None:
    fetcher, sleeps = _fetcher(
        _scripted([httpx.Response(503)]), RetryPolicy(max_retries=0)
    )
    result = fetcher.get(_URL)
    assert isinstance(result, FetchFailure)
    assert result.attempts == 1
    assert fetcher.retries == 0
    assert sleeps == []


def test_retry_after_seconds_is_honored_over_backoff() -> None:
    fetcher, sleeps = _fetcher(
        _scripted(
            [
                httpx.Response(503, headers={"Retry-After": "7"}),
                httpx.Response(200, text="ok"),
            ]
        )
    )
    assert isinstance(fetcher.get(_URL), httpx.Response)
    assert sleeps == [7.0]  # the header, not the 0.5 default backoff


def test_retry_after_is_ignored_when_the_policy_opts_out() -> None:
    fetcher, sleeps = _fetcher(
        _scripted(
            [
                httpx.Response(503, headers={"Retry-After": "7"}),
                httpx.Response(200, text="ok"),
            ]
        ),
        RetryPolicy(respect_retry_after=False),
    )
    assert isinstance(fetcher.get(_URL), httpx.Response)
    assert sleeps == [0.5]  # falls back to backoff


def test_retry_after_is_capped() -> None:
    fetcher, sleeps = _fetcher(
        _scripted(
            [
                httpx.Response(503, headers={"Retry-After": "99999"}),
                httpx.Response(200, text="ok"),
            ]
        )
    )
    assert isinstance(fetcher.get(_URL), httpx.Response)
    assert sleeps == [_MAX_RETRY_AFTER_SECONDS]


def test_parse_retry_after_reads_an_http_date() -> None:
    # A future HTTP-date parses to a non-negative delta; a bad value -> None.
    future = httpx.Response(
        503, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}
    )
    delta = _parse_retry_after(future)
    assert delta is not None and delta > 0
    garbage = httpx.Response(503, headers={"Retry-After": "soon"})
    assert _parse_retry_after(garbage) is None
    assert _parse_retry_after(httpx.Response(503)) is None


def test_a_zoneless_retry_after_date_does_not_raise() -> None:
    # "-0000" means an unknown zone, so parsedate_to_datetime returns a *naive*
    # datetime; treating it as UTC must not raise a naive/aware TypeError.
    naive = httpx.Response(
        503, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 -0000"}
    )
    delta = _parse_retry_after(naive)
    assert delta is not None and delta > 0


def test_a_past_retry_after_date_never_goes_negative() -> None:
    past = httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct 1998 07:28:00 GMT"})
    assert _parse_retry_after(past) == 0.0


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (RunResult(records=[{"a": 1}]), False),  # has records
        (RunResult(blocked=["u"]), False),  # blocked is a definite result
        (RunResult(), True),  # truly empty -> escalate
        (
            RunResult(dead_letter=[FetchFailure("u", "server error (503)", 503, 3)]),
            False,  # a classified failure is definite; don't burn a browser on it
        ),
    ],
)
def test_should_escalate_treats_dead_letter_as_a_definite_result(
    result: RunResult, expected: bool
) -> None:
    assert _should_escalate(result) is expected
