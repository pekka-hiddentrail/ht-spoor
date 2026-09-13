Feature: Skip re-extracting pages that haven't changed since the last run
  # ROADMAP.md §2d / Phase 3.5 — reliability essentials. Monitoring-style use
  # (price tracking, content-change alerts) re-runs the same config on a schedule;
  # re-scraping unchanged pages every time is wasteful. With change detection on,
  # a re-fetch sends the validators (ETag / Last-Modified) a prior run recorded as
  # a conditional request: a "304 Not Modified" — or, when the server sends no
  # validators, a body whose content hash matches — means the page is unchanged,
  # so it is recorded as such and not re-extracted, rather than producing the same
  # records again. It is opt-in: a plain run always re-extracts, because skipping
  # extraction is a behavior change a one-shot scrape shouldn't get by surprise.
  # The validator/hash store is per-domain, local-only (§2h) and runtime-learned,
  # the same §0-sanctioned exception as the tier-3 fingerprint cache. Scope is the
  # tier-1 fetch path; browser-tier change detection is a follow-on (§2d note).

  Background:
    Given a config fetching the "title" from "h1.product-title"

  Scenario: An unchanged page (304 Not Modified) is not re-extracted
    Given change detection is enabled
    And the page was fetched and recorded on a previous run
    When the page has not changed and I run it again
    Then no records are extracted on the second run
    And the run reports 1 unchanged page
    And the second run sent a conditional request

  Scenario: A page unchanged by content hash (no validators) is not re-extracted
    Given change detection is enabled
    And the server sends no validators, and the page was recorded on a previous run
    When the page has not changed and I run it again
    Then no records are extracted on the second run
    And the run reports 1 unchanged page

  Scenario: A changed page is re-extracted
    Given change detection is enabled
    And the page was fetched and recorded on a previous run
    When the page has changed and I run it again
    Then the field is extracted on the second run
    And the run reports no unchanged pages

  Scenario: The first run of a page has nothing to compare and always extracts
    Given change detection is enabled
    When I run the config against a page never seen before
    Then the field is extracted on the second run
    And the run reports no unchanged pages

  Scenario: Change detection is off by default and every run re-extracts
    Given change detection is not configured
    And the page was fetched and recorded on a previous run
    When the page has not changed and I run it again
    Then the field is extracted on the second run
    And the second run sent no conditional request
