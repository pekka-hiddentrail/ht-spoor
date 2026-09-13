Feature: Retry transient failures and dead-letter the unrecoverable
  # ROADMAP.md §2d / Phase 3.5 — reliability essentials. A crawl meets flaky
  # servers: a 503 or a dropped connection is often momentary and worth a bounded
  # retry, while a 404 is a settled answer that retrying only burns politeness
  # budget on. Spoor classifies each tier-1 fetch outcome by generic HTTP category
  # — success, a *transient* failure worth retrying (timeouts, dropped
  # connections, 5xx, 429), or a *permanent* one (other 4xx) — retries the
  # transient ones with backoff (honoring a Retry-After the server sends), and
  # records the URLs it ultimately could not fetch in a dead-letter log surfaced
  # on the run summary. So a run degrades honestly instead of crashing on the
  # first 500 or silently dropping a page. Classification is by HTTP category
  # alone, never anything site-specific (§0). This slice covers the tier-1 httpx
  # fetch path; browser-tier navigation retry is a follow-on (§2d decision note).

  Background:
    Given a config fetching the "title" from "h1.product-title"

  Scenario: A transient server error is retried and then succeeds
    Given the target returns 503 once, then the page
    When I run the config
    Then the field is extracted
    And the run reports 1 transient retry
    And nothing is dead-lettered

  Scenario: An unrecoverable server error is dead-lettered, not crashed
    Given the target always returns 503
    When I run the config
    Then no records are extracted
    And the run does not crash
    And the target is dead-lettered with reason "server error (503)"

  Scenario: A client error is dead-lettered without being retried
    Given the target returns 404
    When I run the config
    Then no records are extracted
    And the target is dead-lettered with reason "client error (404)"
    And the run reports 0 transient retries

  Scenario: A server-sent Retry-After is honored over the default backoff
    Given the target returns 503 with a Retry-After of 7 seconds once, then the page
    When I run the config
    Then the field is extracted
    And it waited 7 seconds before retrying
