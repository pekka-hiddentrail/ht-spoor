# Additional signals catalog — accessibility tree (ROADMAP.md §2c, §2h).
#
# The second §2c signal: the browser tier's accessibility-tree snapshot, read
# over CDP (Accessibility.getFullAXTree; the old snapshot() API is gone). §2c
# calls the tree "a structural view independent
# of visual markup; doubles as a resilience signal for tiers 1/3" — a page that
# exposes almost no accessible structure (e.g. a canvas-rendered UI) is a red
# flag for selector-based extraction, not just extra data.
#
# Same shape as the console signal: opt-in for now via capture (§2c's default-on
# is the full Phase-2.5 target), browser-tier only (a tier-1 fetch has no
# rendered tree to snapshot), and the raw tree is written to the local-only,
# git-ignored run cache. The run summary reports only an aggregate — the number
# of accessible nodes — never the raw tree.

Feature: The browser tier snapshots the accessibility tree
  As someone assessing how extractable and resilient a page is
  I want the browser tier to snapshot the page's accessibility tree
  So that I have a structural view independent of the visual markup

  Scenario: A browser-tier run snapshots the accessibility tree
    Given a live fixture server
    And capture is enabled with the cache redirected to a temp directory
    And a config whose items only exist after JS renders them, with a11y capture on:
      """
      target: SERVER_BASE/js-rendered.html
      item: ".card"
      fields:
        title: { selector: ".title" }
      capture:
        accessibility: true
      """
    When I run the config through the dispatcher against a real browser
    Then an accessibility snapshot file is written under the run cache directory
    And the run records at least one accessible node
    And the run summary reports the accessible node count
    And the run summary reports the accessibility snapshot as a local-only capture

  Scenario: A run that resolves at tier 1 snapshots no accessibility tree
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with a11y capture on:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      capture:
        accessibility: true
      """
    When I run the config with the mock client
    Then no accessibility snapshot file is written to the cache
    And the run summary reports no accessibility signal

  Scenario: Accessibility capture is off by default and nothing is snapshotted
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with no capture section:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      """
    When I run the config with the mock client
    Then no accessibility snapshot file is written to the cache
    And the run summary reports no accessibility signal
