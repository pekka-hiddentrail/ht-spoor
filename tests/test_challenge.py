"""Unit tests for anti-bot challenge detection (ROADMAP.md §2d, Phase 3.5).

The `.feature` scenarios exercise detection end-to-end through a tier-1 run; these
probe `detect_challenge` directly across vendors and — most importantly — its
*false-positive* safety: an ordinary page, and a page that merely mentions a
vendor in prose, must not be mistaken for a challenge, or the detector would
suppress real data. Detection is never bypass: the function only names the wall.
"""

from __future__ import annotations

import pytest

from spoor.operational.challenge import ChallengeSignal, detect_challenge


@pytest.mark.parametrize(
    ("html", "vendor"),
    [
        ('<div class="g-recaptcha" data-sitekey="x"></div>', "reCAPTCHA"),
        ('<script src="https://www/recaptcha/api.js"></script>', "reCAPTCHA"),
        ('<div class="h-captcha"></div>', "hCaptcha"),
        ("<title>Just a moment...</title>", "Cloudflare"),
        ('<div class="cf-turnstile"></div>', "Cloudflare"),
        ("<title>Attention Required! | Cloudflare</title>", "Cloudflare"),
        ("<p>Checking your browser before accessing the site</p>", "Cloudflare"),
    ],
)
def test_a_known_challenge_marker_is_recognized(html: str, vendor: str) -> None:
    signal = detect_challenge(html)
    assert signal is not None
    assert signal.vendor == vendor


def test_detection_is_case_insensitive() -> None:
    signal = detect_challenge('<DIV CLASS="G-RECAPTCHA"></DIV>')
    assert signal is not None
    assert signal.vendor == "reCAPTCHA"


def test_the_matched_marker_is_reported() -> None:
    # The operator gets to see *why* it was called a challenge, not just the vendor.
    signal = detect_challenge('<div class="cf-turnstile"></div>')
    assert signal == ChallengeSignal(vendor="Cloudflare", marker="cf-turnstile")


def test_an_ordinary_page_is_not_a_challenge() -> None:
    html = '<html><body><h1 class="product-title">Gizmo</h1><p>$9.99</p></body></html>'
    assert detect_challenge(html) is None


def test_an_empty_page_is_not_a_challenge() -> None:
    assert detect_challenge("") is None


def test_a_generic_attention_phrase_is_not_a_cloudflare_challenge() -> None:
    # "Attention Required!" on its own is a common alert heading; only the full
    # Cloudflare block-page title counts, so a real page isn't falsely flagged.
    assert detect_challenge("<div class='alert'>Attention Required!</div>") is None


def test_the_first_vendor_in_order_wins_on_a_multi_marker_page() -> None:
    # A page carrying both a reCAPTCHA widget and Cloudflare text names the first
    # signature in table order deterministically, never flip-flopping.
    html = '<div class="g-recaptcha"></div><title>Just a moment...</title>'
    signal = detect_challenge(html)
    assert signal is not None
    assert signal.vendor == "reCAPTCHA"
