# Additional signals catalog — console output & JS errors (ROADMAP.md §2c, §2h).
#
# A Playwright session already sees a lot a bare fetch never does. This is the
# first §2c signal slice: the browser tier's console output and uncaught page
# errors, captured via page.on("console") / page.on("pageerror"). §2c groups
# this in the free/near-free tier; like the HAR (Phase 2.5), capture is opt-in
# for now (default-on is the full Phase-2.5 target) and applies only to the
# browser tier — a tier-1 fetch has no console to observe.
#
# §2h shapes what surfaces where: the raw messages (which can leak tokens in
# debug output) are written to the local-only, git-ignored run cache, never to
# shared output. The run summary reports only non-sensitive aggregates — how
# many messages, how many were errors, how many were uncaught exceptions.
# Surfacing message *content* to shared output waits on the §2h redaction
# pipeline (see the ROADMAP §2c decision note).

Feature: The browser tier observes console output and JS errors
  As someone assessing how a product behaves in the browser
  I want the browser tier to record its console output and uncaught errors
  So that I can see how noisy or broken a page is, with raw text kept off shared output

  Scenario: A browser-tier run records console output and page errors
    Given a live fixture server
    And capture is enabled with the cache redirected to a temp directory
    And a config for a page that logs to the console and throws, with console capture on:
      """
      target: SERVER_BASE/noisy.html
      item: ".card"
      fields:
        title: { selector: ".title" }
      capture:
        console: true
      """
    When I run the config through the dispatcher against a real browser
    Then a console log file is written under the run cache directory
    And the run records at least one console message, one error, and one uncaught error
    And the run summary reports the console message counts
    And the run summary reports the console log as a local-only capture

  Scenario: A run that resolves at tier 1 records no console signal
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with console capture on:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      capture:
        console: true
      """
    When I run the config with the mock client
    Then no console log file is written to the cache
    And the run summary reports no console signal

  Scenario: Console capture is off by default and nothing is recorded
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with no capture section:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      """
    When I run the config with the mock client
    Then no console log file is written to the cache
    And the run summary reports no console signal
