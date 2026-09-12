# Additional signals catalog — client-side storage state (ROADMAP.md §2c, §2h).
#
# The last free/near-free §2c signal: the browser context's storage state —
# cookies plus per-origin localStorage — captured via Playwright's
# context.storage_state(). §2h names it explicitly as bring-your-own-session's
# input and as the archetypal secret-bearing capture: session cookies and
# localStorage tokens ARE the sensitive data, so unlike the count-only signals
# this one cannot sidestep redaction. It is the forcing function for the §2h
# redaction pipeline (already built): the raw, unredacted storage state (all
# cookie and localStorage values) is written to the local-only run cache and
# never shared, while the shareable signal carries the entries with known secret
# shapes redacted — cookie/entry names kept (structural signal), secret values
# scrubbed. Redaction keys off the recognized name=value form, so a recognized
# session cookie or auth-token key is redacted; an unknown-shaped opaque value is
# not caught here — the local-only cache, not redaction, is what keeps it off
# shared output. Same opt-in / browser-tier-only / off-by-default shape as the
# other §2c captures; nothing here is site-specific (§0).

Feature: The browser tier captures client-side storage state, redacted for sharing
  As someone mapping an authenticated app and its client-side state
  I want the browser tier to record cookies and localStorage
  So that I can see the app's client state with secrets kept off shared output

  Scenario: A browser-tier run captures storage state and redacts it for sharing
    Given a live fixture server
    And capture is enabled with the cache redirected to a temp directory
    And a config whose items only exist after JS renders them, with storage capture on:
      """
      target: SERVER_BASE/stateful.html
      item: ".card"
      fields:
        title: { selector: ".title" }
      capture:
        storage: true
      """
    When I run the config through the dispatcher against a real browser
    Then a storage-state file is written under the run cache directory
    And the run records at least one cookie and one localStorage entry
    And the shared storage signal shows the recognized session cookie redacted
    And the shared storage signal keeps the non-secret entry intact
    And no raw secret value appears in shared output
    And the raw storage-state file still contains the unredacted secret value
    And the run summary reports the storage-state counts
    And the run summary reports the storage state as a local-only capture

  Scenario: A run that resolves at tier 1 captures no storage state
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with storage capture on:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      capture:
        storage: true
      """
    When I run the config with the mock client
    Then no storage-state file is written to the cache
    And the run summary reports no storage signal

  Scenario: Storage capture is off by default and nothing is captured
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with no capture section:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      """
    When I run the config with the mock client
    Then no storage-state file is written to the cache
    And the run summary reports no storage signal
