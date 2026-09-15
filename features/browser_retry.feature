@browser
Feature: Retry transient browser navigations and dead-letter the unrecoverable
  # ROADMAP.md §2d / Phase 3.5 — reliability essentials, browser tier. The tier-1
  # retry slice classified and retried the httpx fetch path and left "browser-tier
  # navigation retry is a follow-on" as an explicit note; this closes it. When the
  # browser tier renders a page, a navigation can meet the same flaky server: a
  # 503/429 on the response (or a timeout / dropped connection at the transport
  # level) is often momentary and worth a bounded retry, while a 404 is a settled
  # answer. Spoor drives the browser navigation through the same generic,
  # transport-agnostic classification and backoff as tier 1 — retrying the
  # transient ones, dead-lettering the URLs it ultimately cannot load — so a run
  # degrades honestly instead of an uncaught Playwright error crashing it on the
  # first failed navigation. Classification is by HTTP category alone, never
  # anything site-specific (§0).

  Background:
    Given a browser config fetching the "title" from "h1.product-title"

  Scenario: A transient navigation status is retried and then succeeds
    Given the navigation returns 503 once, then the page
    When I run the config through a real browser
    Then the field is extracted
    And the run reports 1 transient retry
    And nothing is dead-lettered

  Scenario: An unrecoverable navigation status is dead-lettered, not crashed
    Given the navigation always returns 503
    When I run the config through a real browser
    Then no records are extracted
    And the run does not crash
    And the target is dead-lettered with reason "server error (503)"

  Scenario: A client error is dead-lettered without being retried
    Given the navigation returns 404
    When I run the config through a real browser
    Then no records are extracted
    And the target is dead-lettered with reason "client error (404)"
    And the run reports 0 transient retries
