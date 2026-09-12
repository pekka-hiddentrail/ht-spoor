# Operational essentials — ROADMAP.md §2d (+ §6).
#
# §2d is split across phases: this file's Phase-1 slice is the politeness policy
# (respect robots.txt, honor crawl-delay). §6 commits Spoor to respecting
# robots.txt and rate-limiting *by default*, with overriding it an explicit,
# documented opt-out — never the default. The output pipeline (JSON/CSV sinks)
# and the Phase-3.5 items (retry/error classification, CAPTCHA detection, change
# detection, run observability) are authored here when their turn comes.
#
# Concurrency caps and Retry-After honoring are part of §2d's PolitenessPolicy
# but wait for a request pool / retry mechanism to exist — see the ROADMAP §2d
# decision note. The tier-1 crawl is sequential, so there is nothing to cap yet.

Feature: Polite crawling — robots.txt and crawl-delay
  As the operator of a crawl
  I want Spoor to respect robots.txt and space out its requests by default
  So that a run is well-behaved against a target without my having to remember to ask

  Scenario: A disallowed target is not fetched (robots.txt respected by default)
    Given a site whose robots.txt disallows "/private/"
    And a page at "/private/secret.html" with title "Secret"
    And a config targeting "http://localhost:8000/private/secret.html"
    When I run the config with politeness
    Then no request is made to "/private/secret.html"
    And the output contains no items
    And the run reports "http://localhost:8000/private/secret.html" as blocked by robots.txt

  Scenario: An allowed path is fetched normally
    Given a site whose robots.txt disallows "/private/"
    And a page at "/products.html" with title "Ceramic Mug"
    And a config targeting "http://localhost:8000/products.html"
    When I run the config with politeness
    Then the output contains one item
    And the item field "title" equals "Ceramic Mug"

  Scenario: A missing robots.txt allows everything
    Given a site with no robots.txt
    And a page at "/products.html" with title "Ceramic Mug"
    And a config targeting "http://localhost:8000/products.html"
    When I run the config with politeness
    Then the output contains one item

  Scenario: The crawl-delay from robots.txt is honored between fetches
    Given a site whose robots.txt sets a crawl-delay of 2 seconds
    And a 3-page catalog linked by "a.next-page"
    And a config paginating the catalog
    When I run the config with politeness
    Then the output contains 3 items
    And it waits 2 seconds before each fetch after the first
    And it waits 2 times in total

  Scenario: An explicit config delay overrides the robots.txt crawl-delay
    Given a site whose robots.txt sets a crawl-delay of 2 seconds
    And a 3-page catalog linked by "a.next-page"
    And a config paginating the catalog with a politeness delay of 5 seconds
    When I run the config with politeness
    Then it waits 5 seconds before each fetch after the first

  Scenario: Ignoring robots.txt requires an explicit opt-out
    Given a site whose robots.txt disallows "/private/"
    And a page at "/private/secret.html" with title "Secret"
    And a config targeting "http://localhost:8000/private/secret.html" that opts out of robots.txt
    When I run the config with politeness
    Then the output contains one item
    And the item field "title" equals "Secret"
