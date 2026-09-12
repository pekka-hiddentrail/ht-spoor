# Run observability — ROADMAP.md §2d.
#
# The gap between "extracts data" and "usable tool": after a run, a structured
# summary tells the operator whether it went well without reading raw logs —
# items scraped, pages fetched, which tier resolved it, whether it had to
# escalate, and what robots.txt blocked. This Phase-1 slice reports only what the
# current machinery can honestly derive (see the run-observability decision note
# in ROADMAP §2d); error/retry counts and tier-3/4 field fallbacks arrive with
# the machinery that produces them, and are absent here rather than faked.

Feature: A run reports what it did
  As the operator of a crawl
  I want a structured summary of each run
  So that I can tell whether it went well without reading raw logs

  Scenario: A single-page run summarizes items and the resolving tier
    Given a page at "/products.html" with title "Ceramic Mug"
    And a config targeting "http://localhost:8000/products.html"
    When I run the config and capture the summary
    Then the summary reports 1 item scraped
    And the summary reports 1 page fetched
    And the summary reports tier 1 resolved the run
    And the summary reports no escalation
    And the summary reports 0 blocked pages

  Scenario: A paginated run counts every page fetched
    Given a 3-page catalog linked by "a.next-page"
    And a config paginating the catalog
    When I run the config and capture the summary
    Then the summary reports 3 items scraped
    And the summary reports 3 pages fetched
    And the summary reports tier 1 resolved the run

  Scenario: A robots-blocked target is counted and listed in the summary
    Given a site whose robots.txt disallows "/private/"
    And a page at "/private/secret.html" with title "Secret"
    And a config targeting "http://localhost:8000/private/secret.html"
    When I run the config and capture the summary
    Then the summary reports 0 items scraped
    And the summary reports 0 pages fetched
    And the summary reports 1 blocked page
    And the summary lists "http://localhost:8000/private/secret.html" as blocked

  Scenario: The summary renders as human-readable text
    Given a page at "/products.html" with title "Ceramic Mug"
    And a config targeting "http://localhost:8000/products.html"
    When I run the config and capture the summary
    Then the rendered summary mentions "items scraped: 1"
    And the rendered summary mentions "tier 1"
