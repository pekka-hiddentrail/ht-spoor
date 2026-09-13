# Secret redaction before shared output (ROADMAP.md §2h, §9 backlog item).
#
# §2h non-negotiable: before anything reaches a *shared* surface — the §2d output
# pipeline, the §2e wiki, or a §2f MCP/API response — Spoor scans it for known
# secret patterns (Bearer/Basic auth credentials, auth/session-cookie and secret
# field names, common vendor API-key formats, JWTs, PEM private-key blocks) and
# redacts them. Known shapes only, never a high-entropy detector. Raw captures stay in the
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

  Scenario Outline: Stripe secret/restricted keys (underscore form) are redacted
    When I redact "<text>"
    Then the result is "<expected>"

    Examples:
      | text                                 | expected            |
      | key sk_live_NOTAREALKEY000example    | key [REDACTED]      |
      | key sk_test_NOTAREALKEY000example    | key [REDACTED]      |
      | key rk_live_NOTAREALKEY000example    | key [REDACTED]      |

  Scenario: A modern OpenAI project key (with hyphens in the body) is redacted
    When I redact "key sk-proj-abcDEF1234567890ghiJKL0mno here"
    Then the result is "key [REDACTED] here"

  Scenario: A Basic auth credential is redacted, keeping the scheme
    When I redact "Authorization: Basic dXNlcjpzM2NyZXRwYXNzd29yZA=="
    Then the result is "Authorization: Basic [REDACTED]"

  Scenario: The word "Basic" in ordinary prose is not mistaken for a credential
    When I redact "This endpoint uses Basic authentication over HTTPS"
    Then the result is unchanged

  Scenario: A Google OAuth client secret is redacted
    When I redact "secret GOCSPX-1A2b3C4d5E6f7G8h9I0jKlMnOp here"
    Then the result is "secret [REDACTED] here"

  Scenario: A PEM private key block is redacted whole
    When I redact the text:
      """
      -----BEGIN RSA PRIVATE KEY-----
      MIIEpAIBAAKCAQEA7Yn8k2example+base64+material+that+is+not+real==
      -----END RSA PRIVATE KEY-----
      """
    Then the result no longer contains "PRIVATE KEY"
    And the result no longer contains "MIIEpAIBAAKCAQEA"

  Scenario Outline: Credential-bearing key=value fields are redacted, keeping the name
    When I redact "<text>"
    Then the result is "<expected>"

    Examples:
      | text                              | expected             |
      | password=hunter2secretpw          | password=[REDACTED]  |
      | pwd=hunter2secretpw               | pwd=[REDACTED]       |
      | api_key=AbCdEf1234567890xyz       | api_key=[REDACTED]   |
      | apikey=AbCdEf1234567890xyz        | apikey=[REDACTED]    |
      | client_secret=AbCdEf1234567890xyz | client_secret=[REDACTED] |
      | token=deadbeefcafe12345678        | token=[REDACTED]     |
      | id_token=deadbeefcafe12345678     | id_token=[REDACTED]  |

  Scenario: Every secret in a multi-secret string is redacted
    When I redact "Bearer sk_live_ABCDEF1234567890 and sessionid=deadbeefcafe1234"
    Then the result is "Bearer [REDACTED] and sessionid=[REDACTED]"

  Scenario: Text with no known secret is left unchanged
    When I redact "Server: nginx; Content-Type: text/html; charset=utf-8"
    Then the result is unchanged

  Scenario: Redaction is idempotent
    When I redact "Authorization: Bearer sk_live_abcdef1234567890XYZ" twice
    Then the two results are identical
