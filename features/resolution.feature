# Escalation across resolution tiers — the dispatcher (ROADMAP.md §2).
#
# Resolution is a ladder: tier 1 (static fetch + selectors), tier 2 (JS
# rendering), tier 3 (self-healing). The config author never names a tier (§2a,
# §0) — the dispatcher picks one and escalates. This file specifies the seam
# itself: which tier runs, and what happens when a config needs a tier that is
# declared but not yet implemented. Tier-2 rendering and tier-3 self-healing
# behaviour arrive with their own scenarios when those tiers are built; the
# @tier2 extraction scenarios stay skipped until then.

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
    And it fails with a clear message that tier 2 is not yet available

  Scenario: Both tiers are registered, with tier 2 declared but not yet built
    Then the dispatcher registers tier 1 and tier 2 in order
    And tier 1 is implemented while tier 2 is a declared stub
