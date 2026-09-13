# Extraction robustness against adversarial and malformed input — ROADMAP.md §2a.
#
# The declarative contract (extraction.feature) covers well-formed pages. This
# file locks the other half: a real crawl meets empty responses, non-HTML bodies,
# unclosed/broken markup, pathologically deep DOMs, and non-ASCII text. Spoor must
# degrade gracefully — extract what it can, leave the rest null, and never crash —
# rather than raise on a hostile page and abort the run. These scenarios were
# distilled from an adversarial probe of the engine; they exist so that verified
# robustness can never silently regress. Nothing here is site-specific (§0): the
# same generic parse-and-select path handles every one of these inputs.

Feature: Extraction degrades gracefully on malformed and hostile input
  As someone pointing Spoor at real, uncontrolled pages
  I want a broken or surprising page to yield what data it can, not an error
  So that one bad page never aborts a crawl or corrupts the output

  Scenario: An empty page yields a record with null fields, not a crash
    Given a config:
      """
      target: http://localhost:8000/empty.html
      fields:
        title: { selector: "h1" }
        price: { selector: ".price", type: number }
      """
    When I run the config
    Then the output contains one item
    And the item field "title" is null
    And the item field "price" is null

  Scenario: A body of non-HTML garbage yields null fields, not a crash
    Given a config:
      """
      target: http://localhost:8000/garbage.html
      fields:
        title: { selector: "h1" }
        price: { selector: ".price", type: number }
      """
    When I run the config
    Then the output contains one item
    And the item field "title" is null
    And the item field "price" is null

  Scenario: Unclosed, malformed markup still yields the fields it can find
    Given a config:
      """
      target: http://localhost:8000/malformed.html
      fields:
        title: { selector: "h1.product-title" }
        price: { selector: ".price", type: number }
      """
    When I run the config
    Then the item field "title" equals "Recovered Title"
    And the item field "price" is the number 7.5

  Scenario: A pathologically deep DOM is handled without crashing
    Given a config:
      """
      target: http://localhost:8000/deep.html
      fields:
        title: { selector: "h1.buried" }
      """
    When I run the config
    Then the item field "title" equals "Buried Deep"

  Scenario: Non-ASCII text is preserved exactly
    Given a config:
      """
      target: http://localhost:8000/unicode.html
      fields:
        title: { selector: "h1" }
      """
    When I run the config
    Then the item field "title" equals "Café ☕ 日本語 😀"
