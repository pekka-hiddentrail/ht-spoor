"""Secret redaction for shared output (ROADMAP.md §2h, §9 backlog item).

§2h is a non-negotiable: before anything reaches a *shared* surface — the §2d
output pipeline, the §2e wiki, or a §2f MCP/API response — Spoor scans it for
known secret patterns and redacts them, so a captured live credential can never
leave the machine through a shared channel. Raw, unredacted captures stay in the
local-only run cache (`spoor/security/storage.py`); redaction guards only the
path *out*. This module is the §9 deliverable that policy named: the concrete,
maintained pattern list, built as a reusable primitive before the first
shared-output consumer (client-side storage state) is wired to it.

Design notes, and the boundaries of the claim:

- **Default-on by construction.** `redact` takes only the text; there is no
  parameter to disable it. A caller on the shared path cannot opt out — the
  only way raw values leave the machine is the separate, explicit export of the
  local cache (§2h), which does not route through here.
- **Known shapes, not entropy.** This redacts *recognized* secret formats
  (bearer/auth-scheme tokens, common auth-cookie names, common vendor API-key
  formats, JWTs). It is deliberately not a general high-entropy-string detector:
  that trades false positives (mangling legitimate data) for a promise this
  layer does not make. A value in an unknown shape is not caught here — the
  local-only cache, not redaction, is what keeps raw captures off shared output.
- **Structure-preserving.** Where a secret has a non-sensitive prefix (an auth
  scheme, a cookie name), the prefix is kept and only the credential replaced,
  so the redacted output still reads as what it was.
- **Idempotent.** The `[REDACTED]` placeholder matches none of the patterns
  (its brackets fall outside every token character class), so re-redacting
  already-redacted text is a no-op.
"""

from __future__ import annotations

import re

# The placeholder a matched secret is replaced with. Chosen so it matches none
# of the patterns below, which is what makes redaction idempotent.
REDACTED = "[REDACTED]"

# Ordered (pattern, replacement) rules, applied in sequence. A replacement may
# reference the named group ``pre`` to keep a non-sensitive prefix (auth scheme,
# cookie name) and redact only the credential that follows. Compiled once at
# import; each rule matches independently, so order matters only when two rules
# could touch the same span — and there the result is identical either way.
#
# Maintained list (§9): extend deliberately, with a fixture example in
# redaction.feature for every shape added, never a broad catch-all.
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Bearer-scheme credential: keeps "bearer " and redacts the token.
    (
        re.compile(r"\b(?P<pre>bearer\s+)[\w.~+/=-]{8,}", re.IGNORECASE),
        rf"\g<pre>{REDACTED}",
    ),
    # Common auth/session-cookie shapes: keep the cookie name, redact the value
    # up to the next cookie delimiter.
    (
        re.compile(
            r"\b(?P<pre>(?:session(?:id)?|sessid|sid|auth[_-]?token|access[_-]?token"
            r"|refresh[_-]?token|csrf[_-]?token|xsrf[_-]?token|phpsessid|jsessionid"
            r"|connect\.sid)=)[^\s;,]+",
            re.IGNORECASE,
        ),
        rf"\g<pre>{REDACTED}",
    ),
    # JSON Web Token: three base64url segments. Matched before the vendor keys so
    # a token-shaped value is caught whole.
    (re.compile(r"\beyJ[\w-]+\.eyJ[\w-]+\.[\w-]+"), REDACTED),
    # Stripe / OpenAI-style secret keys ("sk-...").
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}"), REDACTED),
    # AWS access key id.
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    # Google API key.
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), REDACTED),
    # GitHub personal-access / OAuth / server / refresh tokens.
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), REDACTED),
    # Slack tokens.
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), REDACTED),
)


def redact(text: str) -> str:
    """Return ``text`` with every recognized secret replaced by ``REDACTED``.

    The shared-output guard (§2h). Takes only the text and has no opt-out: a
    caller on the way to shared output cannot ship raw secrets through here.
    Non-secret text is returned unchanged, and the result is idempotent.
    """
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
