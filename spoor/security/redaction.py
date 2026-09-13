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
- **Known shapes, not entropy.** This redacts *recognized* secret formats:
  auth-scheme credentials (``Bearer``, and ``Basic`` when it rides an
  Authorization header), common auth/session-cookie *and* secret field names
  (``sessionid``, ``api_key``, ``client_secret``, ``password``, …), common
  vendor API-key formats (OpenAI ``sk-``/``sk-proj-``, Stripe ``sk_live_``/
  ``rk_live_``, AWS ``AKIA…``, Google ``AIza…`` and ``GOCSPX-…``, GitHub, Slack),
  JWTs, and PEM private-key blocks. It is deliberately not a general
  high-entropy-string detector: that trades false positives (mangling legitimate
  data) for a promise this layer does not make — a keyless 40-char blob such as
  an AWS *secret* access key has no recognizable shape and is not caught here. A
  value in an unknown shape relies on the local-only cache, not redaction, to
  stay off shared output.
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
    # Basic-scheme credential. Unlike Bearer, "Basic" is a common English word
    # ("Basic authentication"), so this is anchored to an Authorization header to
    # avoid mangling prose — it keeps the scheme and redacts the base64 blob.
    (
        re.compile(
            r"(?P<pre>(?:proxy-)?authorization:\s*basic\s+)[A-Za-z0-9+/=]{8,}",
            re.IGNORECASE,
        ),
        rf"\g<pre>{REDACTED}",
    ),
    # Common credential-bearing key=value shapes (auth/session cookies, and the
    # obvious secret field names): keep the name, redact the value up to the next
    # delimiter. A curated list of known-sensitive names — not a catch-all — so a
    # bare opaque value under an unrecognized name still relies on the local-only
    # cache, never this rule (the known-shapes boundary, §2h).
    (
        re.compile(
            r"\b(?P<pre>(?:session(?:id)?|sessid|sid|auth[_-]?token|access[_-]?token"
            r"|refresh[_-]?token|id[_-]?token|csrf[_-]?token|xsrf[_-]?token|token"
            r"|phpsessid|jsessionid|connect\.sid|api[_-]?key|apikey"
            r"|client[_-]?secret|api[_-]?secret|password|passwd|pwd)=)[^\s;,]+",
            re.IGNORECASE,
        ),
        rf"\g<pre>{REDACTED}",
    ),
    # PEM private-key block: redact the whole armored block (any key type).
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        REDACTED,
    ),
    # JSON Web Token: three base64url segments. Matched before the vendor keys so
    # a token-shaped value is caught whole.
    (re.compile(r"\beyJ[\w-]+\.eyJ[\w-]+\.[\w-]+"), REDACTED),
    # OpenAI-style secret keys: "sk-..." including the modern "sk-proj-..." form,
    # whose hyphenated body the plain alphanumeric class would truncate.
    (re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{15,}"), REDACTED),
    # Stripe secret ("sk_") and restricted ("rk_") keys — underscore form, live or
    # test. (Publishable "pk_" keys are not secret and are deliberately excluded.)
    (re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"), REDACTED),
    # Google OAuth client secret.
    (re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{16,}"), REDACTED),
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
