# Secret redaction before shared output (ROADMAP.md §2h, §9 backlog item).
#
# §2h non-negotiable: before anything reaches a *shared* surface — the §2d output
# pipeline, the §2e wiki, or a §2f MCP/API response — Spoor scans it for known
# secret patterns (bearer tokens, common auth-cookie shapes, common vendor
# API-key formats) and redacts them. Raw, unredacted captures stay in the
# local-only cache; redaction guards only the shared path. This is the §9
# backlog deliverable: the concrete, maintained pattern list, built as a reusable
# primitive here, before the first shared-output consumer (client-side storage)
# is wired to it in the next slice. Redaction is default-on: there is no flag to
# turn it off, so nothing can silently ship a secret to shared output.

Feature: Known secret patterns are redacted before reaching shared output
  As someone whose captures may contain live tokens and cookies
  I want secrets scrubbed before anything is shared, exported, or served
  So that a captured secret never leaves my machine through a shared surface

  Scenario: A bearer token is redacted, keeping the scheme
    When I redact "Authorization: Bearer sk_live_abcdef1234567890XYZ"
    Then the result is "Authorization: Bearer [REDACTED]"

  Scenario: A session-cookie value is redacted, keeping the cookie name
    When I redact "sessionid=8f9a1b2c3d4e5f6071829304; Path=/; HttpOnly"
    Then the result is "sessionid=[REDACTED]; Path=/; HttpOnly"

  Scenario Outline: Common vendor API-key formats are redacted
    When I redact "<text>"
    Then the result is "<expected>"

    Examples:
      | text                                                         | expected              |
      | key AKIAIOSFODNN7EXAMPLE here                                 | key [REDACTED] here   |
      | token ghp_16C7e42F292c6912E7710c838347Ae178B4a here          | token [REDACTED] here |
      | slack xoxb-not-a-real-slack-token-for-tests here             | slack [REDACTED] here |

  Scenario: A JSON Web Token is redacted
    When I redact "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.abcDEF123-_x"
    Then the result is "[REDACTED]"

  Scenario: Every secret in a multi-secret string is redacted
    When I redact "Bearer sk_live_ABCDEF1234567890 and sessionid=deadbeefcafe1234"
    Then the result is "Bearer [REDACTED] and sessionid=[REDACTED]"

  Scenario: Text with no known secret is left unchanged
    When I redact "Server: nginx; Content-Type: text/html; charset=utf-8"
    Then the result is unchanged

  Scenario: Redaction is idempotent
    When I redact "Authorization: Bearer sk_live_abcdef1234567890XYZ" twice
    Then the two results are identical
