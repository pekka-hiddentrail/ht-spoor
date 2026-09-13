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
  # challenge. A challenge served with an error status (a 403/503 interstitial) is
  # already surfaced loudly by the retry/dead-letter path; this recognises a
  # challenge delivered in an otherwise-successful (2xx) response.

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
