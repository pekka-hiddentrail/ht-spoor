Feature: Detect anti-bot challenges and fail loudly, never scrape one as data
  # ROADMAP.md §2d / Phase 3.5 — reliability essentials, detection *not* bypass.
  # When a fetch lands on a CAPTCHA or an anti-bot interstitial (a reCAPTCHA /
  # hCaptcha widget, a Cloudflare "just a moment" page), the worst outcome is
  # silently emitting the challenge markup as if it were the data the user asked
  # for. Spoor recognizes known challenge fingerprints in the fetched HTML and
  # surfaces an explicit "challenge detected" result on the run summary, so an
  # operator sees an honest "hit a wall here" instead of a page of garbage or an
  # empty run with no explanation. Fingerprints are generic anti-bot-vendor
  # markers (widget classes, interstitial title text) — vendor-generic, never
  # tailored to a target site (§0), and Spoor never attempts to solve or bypass a
  # challenge. A challenge is recognized whether it arrives in an otherwise-
  # successful (2xx) response or *behind* an error status — a Cloudflare/CAPTCHA
  # interstitial is commonly served with a 403 or 503, so such a fetch is both a
  # dead-letter failure and a challenge, and the summary says both: "hit a wall"
  # rather than an opaque error. Only the generic vendor/marker is ever surfaced,
  # never the challenge markup itself (§2h).

  Background:
    Given a config fetching the "title" from "h1.product-title"

  Scenario: A reCAPTCHA-guarded page is detected, not scraped as data
    Given the target returns a page guarded by reCAPTCHA
    When I run the config
    Then no real data is extracted
    And the run reports an anti-bot challenge from "reCAPTCHA"

  Scenario: A Cloudflare interstitial is detected
    Given the target returns a Cloudflare interstitial
    When I run the config
    Then no real data is extracted
    And the run reports an anti-bot challenge from "Cloudflare"

  Scenario: An ordinary page is never mistaken for a challenge
    Given the target returns an ordinary product page
    When I run the config
    Then the field is extracted
    And the run reports no anti-bot challenge

  Scenario: A challenge behind a 403 is both dead-lettered and reported
    Given the target returns a Cloudflare interstitial with status 403
    When I run the config
    Then no real data is extracted
    And the target is dead-lettered with reason "client error (403)"
    And the run reports an anti-bot challenge from "Cloudflare"

  Scenario: A challenge behind an exhausted 503 is both dead-lettered and reported
    Given the target returns a reCAPTCHA page with status 503
    When I run the config
    Then no real data is extracted
    And the target is dead-lettered with reason "server error (503)"
    And the run reports an anti-bot challenge from "reCAPTCHA"

  Scenario: An ordinary error body is dead-lettered without a phantom challenge
    Given the target returns an ordinary error page with status 503
    When I run the config
    Then no real data is extracted
    And the target is dead-lettered with reason "server error (503)"
    And the run reports no anti-bot challenge

  Scenario: A challenge behind an error status is detected through a real browser
    Given a browser navigation returning a Cloudflare interstitial with status 403
    When I run the config through a real browser
    Then no real data is extracted
    And the run reports an anti-bot challenge from "Cloudflare"
