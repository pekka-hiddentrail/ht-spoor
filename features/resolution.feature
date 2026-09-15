# Escalation across resolution tiers — the dispatcher (ROADMAP.md §2).
#
# Resolution is a ladder: tier 1 (static fetch + selectors), tier 2 (JS
# rendering), tier 3 (self-healing). The config author never names a tier (§2a,
# §0) — the dispatcher picks one and escalates. This file specifies the seam
# itself: which tier a config routes to, that tier 1 hands a browser-only
# *capability* up to tier 2, and that an empty tier-1 result escalates to the
# browser on *content* grounds (zero records extracted). What tier 2 then *does*
# in a real browser is covered here and in extraction.feature; tier-3
# self-healing arrives with its own scenarios when that tier is built.

Feature: The dispatcher resolves a config through the right tier
  As someone who just describes what to extract
  I want the tool to pick and escalate resolution tiers for me
  So that I never write tier-specific logic in a config

  Background:
    Given a fixture page at "http://localhost:8000/products.html"

  Scenario: Tier 1 satisfies a config it can resolve, without escalating
    Given a config that tier 1 can fully satisfy:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      """
    When the dispatcher resolves the config
    Then tier 1 handles the run
    And the run produces records without engaging a higher tier

  Scenario: A capability tier 1 cannot provide escalates to tier 2
    Given a config that needs JS-rendered (infinite-scroll) pagination:
      """
      target: http://localhost:8000/feed.html
      fields:
        title: { selector: ".card .title" }
      pagination:
        infinite_scroll: true
      """
    When the dispatcher resolves the config
    Then the run escalates past tier 1 to tier 2
    And tier 1 declined it while tier 2 accepted it

  @browser
  Scenario: An empty tier-1 result escalates to the browser tier
    Given a live fixture server
    And a config whose items only exist after JS renders them:
      """
      target: SERVER_BASE/js-rendered.html
      item: ".card"
      fields:
        title: { selector: ".title" }
      """
    When I run the config through the dispatcher against a real browser
    Then tier 1 on its own extracts nothing
    And the dispatcher escalates to tier 2 and returns the rendered records

  Scenario: Both tiers are registered in order, tier 1 then the browser tier
    Then the dispatcher registers tier 1 and tier 2 in order
    And both tiers are implemented, tier 2 rendering in a real browser
