# Additional signals catalog — response headers (ROADMAP.md §2c, §2h).
#
# The third §2c signal: the browser tier's response headers — CSP, HSTS,
# X-Frame-Options, server/infra headers — a cheap fingerprint of backend tech
# and security posture (§2c). Same shape as the console and accessibility
# signals: opt-in for now via capture, browser-tier only.
#
# §2h decision (recorded in the ROADMAP §2c note): header VALUES are not surfaced
# to shared output, because some headers (set-cookie, authorization) are known
# secret shapes. The raw full headers — all values — are written to the
# local-only, git-ignored run cache; the run summary carries only non-sensitive
# derived facts: how many distinct headers were seen, and presence booleans for
# the key security headers. Surfacing header values waits on the §2h redaction
# pipeline.

Feature: The browser tier records response-header fingerprints
  As someone assessing a product's backend and security posture
  I want the browser tier to record the response headers it saw
  So that I get a fingerprint without header values leaking to shared output

  Scenario: A browser-tier run records response headers
    Given a live fixture server
    And capture is enabled with the cache redirected to a temp directory
    And a config whose items only exist after JS renders them, with header capture on:
      """
      target: SERVER_BASE/js-rendered.html
      item: ".card"
      fields:
        title: { selector: ".title" }
      capture:
        headers: true
      """
    When I run the config through the dispatcher against a real browser
    Then a response-headers file is written under the run cache directory
    And the run records at least one response header
    And the run summary reports the response-header count
    And the run summary reports the security-header presence
    And the run summary reports the response headers as a local-only capture
    And the run summary shows no header values

  Scenario: A run that resolves at tier 1 records no header signal
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with header capture on:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      capture:
        headers: true
      """
    When I run the config with the mock client
    Then no response-headers file is written to the cache
    And the run summary reports no header signal

  Scenario: Header capture is off by default and nothing is recorded
    Given capture is enabled with the cache redirected to a temp directory
    And a static config with no capture section:
      """
      target: http://localhost:8000/products.html
      fields:
        title: { selector: "h1.product-title" }
      """
    When I run the config with the mock client
    Then no response-headers file is written to the cache
    And the run summary reports no header signal
