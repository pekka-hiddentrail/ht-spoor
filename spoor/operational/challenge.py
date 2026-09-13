"""Anti-bot / CAPTCHA challenge detection — detection, never bypass (§2d).

ROADMAP.md §2d asks Spoor to "recognize known challenge-page fingerprints ... and
fail loudly with a clear result rather than looping forever or silently returning
a challenge page as if it were data." This module is that recognizer: a scan of
already-fetched HTML for generic anti-bot-*vendor* markers (a reCAPTCHA / hCaptcha
widget, a Cloudflare interstitial). It never attempts to solve or evade a
challenge — it only names the wall so the run can report it honestly.

The markers are vendor-generic, not target-specific: any site can sit behind
Cloudflare or embed a reCAPTCHA, so recognizing those is infrastructure detection
of the same class as parsing `robots.txt`, not knowledge of a particular target
(§0). Deliberately, the signatures are *structural* tokens (widget CSS classes,
challenge-token parameters, interstitial title text) rather than vendor hostnames
— both to keep false positives low and so nothing here reads as a hardcoded
target domain. This is a maintainable, PR-extendable table, not a fixed set.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChallengeSignal:
    """A recognized anti-bot challenge in a fetched page (ROADMAP.md §2d).

    `vendor` is the human-facing name of the anti-bot system recognized
    ("reCAPTCHA", "hCaptcha", "Cloudflare"); `marker` is the specific structural
    token that matched, surfaced so an operator can see *why* Spoor called it a
    challenge. Both are generic vendor facts, never target-specific (§0) or a
    captured secret (§2h).
    """

    vendor: str
    marker: str


# Vendor -> the structural markers whose presence (case-insensitive) in a page's
# HTML fingerprints that vendor's challenge. Structural tokens only (widget
# classes, challenge-token params, interstitial title text) — never vendor
# hostnames — to keep false positives low and stay clear of §0's no-hardcoded-
# -domains rule. Extend via PR as new challenge systems show up in the wild.
_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reCAPTCHA", ("g-recaptcha", "grecaptcha", "recaptcha/api.js")),
    ("hCaptcha", ("h-captcha", "hcaptcha")),
    (
        "Cloudflare",
        (
            "cf-turnstile",
            "cf-challenge",
            "cf-browser-verification",
            "__cf_chl",
            "just a moment...",
            "checking your browser before accessing",
            "attention required! | cloudflare",
        ),
    ),
)


def detect_challenge(html: str) -> ChallengeSignal | None:
    """Recognize an anti-bot challenge in `html`, or None if it looks ordinary.

    Case-insensitive substring scan for the first vendor whose marker appears.
    Purely a read of the HTML already fetched — it makes no request, never raises,
    and never tries to solve the challenge (detection, not bypass; §2d). Order is
    stable so the same page always names the same vendor.
    """
    haystack = html.lower()
    for vendor, markers in _SIGNATURES:
        for marker in markers:
            if marker in haystack:
                return ChallengeSignal(vendor=vendor, marker=marker)
    return None
