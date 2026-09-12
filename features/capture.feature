# Raw network capture — the browser tier's HAR (ROADMAP.md §2b/§2c, §2h).
#
# The browser tier can record every request/response it makes as a HAR, the raw
# material the §2c signal catalog and the mitmproxy2swagger spike (§8.4) build on.
# This is the first, deliberately tight slice: capture is opt-in (§2c's default-on
# is the full Phase-2.5 target), applies only to the browser tier (the only tier
# with a browser context to record), and the HAR is a raw, unredacted artifact
# that stays in a local-only, git-ignored cache — never routed to shared output
# (§2h non-negotiable). A run that resolves without a browser writes no HAR and
# says so honestly, rather than emitting an empty file.

Feature: The browser tier records raw network traffic to a local-only cache
  As someone building an API/signal map from a crawl
  I want the browser tier to save the raw network traffic it saw
  So that later analysis has the real requests to work from, kept off shared output

  Scenario: Capturing a browser-tier run writes a HAR to the local-only cache
    Given a live fixture server
    And capture is enabled with the cache redirected to a temp directory
    And a config whose items only exist after JS renders them, with capture on:
      """
      target: SERVER_BASE/js-rendered.html
      item: ".card"
      fields:
        title: { selector: ".title" }
      capture:
        har: true
      """
    When I run the config through the dispatcher against a real browser
    Then a HAR file is written under the run cache directory
    And the HAR parses as JSON with a request for the rendered page
    And the run summary reports the captured HAR path

  Scenario: A run that resolves at tier 1 captures no HAR
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with capture on:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      capture:
        har: true
      """
    When I run the config with the mock client
    Then no HAR file is written to the cache
    And the run summary reports no capture

  Scenario: Capture is off by default and nothing is written
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with no capture section:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      """
    When I run the config with the mock client
    Then no HAR file is written to the cache
    And the run summary reports no capture
