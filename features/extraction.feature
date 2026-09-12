# Declarative extraction configs — ROADMAP.md §2a.
#
# The user-facing contract: config in, structured data out. The schema shape is
# identical for every target (§0 — pointing at a new site is a new config, never
# new code). Each field's `selector` is only the tier-1 starting point; the
# escalation dispatcher (§2) walks it through later tiers automatically, so a
# config author never writes tier-specific logic. Escalation internals are
# specified in resolution.feature; output-sink details in output.feature.

Feature: Declarative extraction from a config file
  As someone who knows what they want from a target
  I want to describe fields and pagination in a config file
  So that I get structured data out without writing any per-target code

  Background:
    Given a fixture page at "http://localhost:8000/products.html"

  Scenario: Extract named fields from a single page
    Given a config:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
        price: { selector: ".price", type: number }
        availability: { selector: ".stock-status" }
      """
    When I run the config
    Then the output contains one item
    And the item field "title" equals "Ceramic Mug"
    And the item field "availability" equals "In stock"

  Scenario: Extract many records from a listing page via an item selector
    Given a fixture listing page with 5 product cards at "http://localhost:8000/listing.html"
    And a config:
      """
      target: http://localhost:8000/listing.html
      item: "li.product-card"
      fields:
        title: { selector: "h2.title" }
        price: { selector: ".price", type: number }
      """
    When I run the config
    Then the output contains 5 items
    And every item has non-null fields "title" and "price"

  Scenario: A field declared as number is coerced to a numeric type
    Given a config:
      """
      target: http://localhost:8000/products.html
      fields:
        price: { selector: ".price", type: number }
      """
    When I run the config
    Then the item field "price" is the number 12.5

  Scenario: A missing optional field yields null, not an error
    Given a config:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
        subtitle: { selector: ".subtitle-that-does-not-exist" }
      """
    When I run the config
    Then the output contains one item
    And the item field "subtitle" is null

  Scenario: Follow pagination until there is no next page
    Given a fixture site of 3 pages linked by "a.next-page"
    And a config:
      """
      target: http://localhost:8000/catalog/page-1.html
      fields:
        title: { selector: "h2.item-title" }
      pagination:
        next: "a.next-page"
      """
    When I run the config
    Then items are extracted from all 3 pages
    And the run stops after the page with no "a.next-page" link

  @tier2
  Scenario: Infinite-scroll pagination is driven by a flag
    Given a fixture page that loads more items on scroll
    And a config:
      """
      target: http://localhost:8000/feed.html
      fields:
        title: { selector: ".card .title" }
      pagination:
        infinite_scroll: true
      """
    When I run the config
    Then more than one screen of items is extracted

  Scenario: Output is written to the path given with -o
    Given a config that extracts "title" from the fixture page
    When I run the config with output path "out.json"
    Then a file "out.json" exists
    And it contains the extracted items as structured data

  Scenario: The config author writes only the tier-1 selector
    Given a config whose "title" selector is a plain CSS selector
    Then the config declares no tier-2, tier-3, or tier-3.5 logic
    And escalation across tiers is handled by the dispatcher, not the config

  Scenario: A config missing the required target is rejected with a clear error
    Given a config:
      """
      fields:
        title: { selector: "h1" }
      """
    When I run the config
    Then the run fails before fetching anything
    And the error message names the missing "target" field

  Scenario: An unknown field option is reported, not silently ignored
    Given a config:
      """
      target: http://localhost:8000/products.html
      fields:
        price: { selector: ".price", typ: number }
      """
    When I run the config
    Then the run fails with an error naming the unknown option "typ"
