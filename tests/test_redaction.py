"""Unit tests for the §2h secret-redaction primitive (ROADMAP.md §2h, §9).

Below redaction.feature: the scenarios pin the headline shapes in reviewable
Gherkin; these pin the edges — empty input, non-secret identity, each pattern in
the maintained list, idempotency, and the default-on contract (no opt-out
parameter) — so the shared-output guard can't quietly regress.
"""

from __future__ import annotations

import inspect

from spoor.security.redaction import REDACTED, redact


def test_empty_string_is_unchanged() -> None:
    assert redact("") == ""


def test_text_without_secrets_is_identity() -> None:
    text = "Server: nginx; Content-Type: text/html; charset=utf-8; max-age=600"
    assert redact(text) == text


def test_bearer_token_keeps_scheme() -> None:
    assert redact("Bearer sk_live_abcdef1234567890XYZ") == f"Bearer {REDACTED}"


def test_bearer_is_case_insensitive_and_preserves_original_case() -> None:
    assert redact("authorization: BEARER abcdef1234567890") == (
        f"authorization: BEARER {REDACTED}"
    )


def test_short_word_after_bearer_scheme_is_not_redacted() -> None:
    # The credential must be long enough to be a token; a stray short word after
    # "bearer" is left alone rather than mangled.
    assert redact("bearer of bad news") == "bearer of bad news"


def test_session_cookie_keeps_name_and_stops_at_delimiter() -> None:
    assert redact("PHPSESSID=abcdef0123456789; Path=/") == (
        f"PHPSESSID={REDACTED}; Path=/"
    )


def test_non_secret_key_value_pair_is_left_alone() -> None:
    # charset= / max-age= are not auth-cookie names; they must not be redacted.
    text = "charset=utf-8; max-age=31536000"
    assert redact(text) == text


def test_jwt_is_redacted_whole() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.abcDEF123-_x"
    assert redact(jwt) == REDACTED


def test_vendor_keys_are_redacted() -> None:
    for token in (
        "AKIAIOSFODNN7EXAMPLE",
        "AIzaSyA1234567890abcdefghijklmnopqrstuv",  # AIza + 35 chars
        "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
        "github_pat_11ABCDE0123456789_abcdefghij",
        "xoxb-not-a-real-slack-token-for-tests",
        "sk-abcdefghijklmnop0123456789",
    ):
        assert redact(f"val {token} end") == f"val {REDACTED} end", token


def test_every_secret_in_a_multi_secret_string_is_redacted() -> None:
    text = "Bearer sk_live_ABCDEF1234567890 and sessionid=deadbeefcafe1234"
    assert redact(text) == f"Bearer {REDACTED} and sessionid={REDACTED}"


def test_redaction_is_idempotent() -> None:
    text = "Authorization: Bearer sk_live_abcdef1234567890XYZ; sid=cafebabefeed"
    once = redact(text)
    assert redact(once) == once
    assert REDACTED in once


def test_redact_has_no_opt_out_parameter() -> None:
    # §2h default-on: a caller on the shared path cannot disable redaction. The
    # only parameter is the text itself.
    params = list(inspect.signature(redact).parameters)
    assert params == ["text"]
