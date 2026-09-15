# Generated regression tests from an exploration graph — ROADMAP.md §2g.
#
# Sub-slice 2g-i, the pure generator, built logic-first like the wiki renderer (6a):
# an ExplorationGraph becomes a set of pytest test *sources* (filename → code), with
# no browser and no disk in `build_tests`. §2g's premise is that a captured map is
# already a golden-master record — state X, action Y, produced signal bundle Z — so
# exporting it as a runnable test is the last-mile step. This slice emits, per mapped
# transition, a pytest test that drives Playwright to replay the path that reached the
# transition's from-state, fires the action, and asserts the signals the action was
# recorded to add still appear — a real regression test the consuming team runs in CI
# against the live product, not a check of the map's own internal consistency.
#
# Because a generated test file is a shared-output surface, §2h redaction is mandatory:
# every captured value baked into it (console lines, storage keys, request URLs, action
# names, the target URL) is redacted before it is written. That has a consequence the
# wiki did not face — a generated test *asserts* recorded values against the live page's
# raw runtime values, so both sides must be redacted like-for-like or a redacted
# expectation would never match. The generated suite therefore redacts the live values
# it observes with the same primitive before comparing, so the assertion checks that the
# behaviour *as Spoor would record and share it* is unchanged, and no raw secret is ever
# written into a test. Nothing here is site-specific (§0): one emitter for every target.
#
# Wiring the suite to a command and proving the emitted tests actually run green against
# a live fixture is sub-slice 2g-ii; this slice pins the generated sources.

Feature: Generate replayable regression tests from an exploration graph
  As a team that has mapped a site with Spoor
  I want each mapped transition exported as a runnable pytest test
  So that re-running them against the live product catches behavioural drift

  Background:
    Given an explored graph:
      | state | ax_nodes | console     | storage        | network            |
      | home  | 3        | home ready  | session        | /home.js           |
      | menu  | 6        | menu opened | session; token | /home.js; /menu.js |
      | cart  | 8        | cart open   | session; token | /menu.js; /cart.js |
    And a mapped transition "Open menu" from "home" to "menu"
    And a mapped transition "Add to cart" from "menu" to "cart"

  Scenario: The suite has a conftest, a shared helper, and one test per transition
    When I generate a pytest suite for "https://shop.example"
    Then the suite has a pytest conftest
    And the suite has a shared test helper module
    And the suite has one test file per mapped transition
    And every generated file is valid Python

  Scenario: A generated test replays, fires the action, and asserts what it changed
    When I generate a pytest suite for "https://shop.example"
    Then the test for "Open menu" fires the action named "Open menu"
    And the test for "Open menu" asserts the added console message "menu opened"
    And the test for "Open menu" asserts the added storage key "token"
    And the test for "Open menu" asserts the added network request "/menu.js"

  Scenario: A transition reached deeper in the graph replays its whole path first
    # "Add to cart" is only reachable after "Open menu", so its test must replay that
    # first action before firing the one under test — the reset-and-replay path the
    # explorer used to reach the from-state, reconstructed from the recorded edges.
    When I generate a pytest suite for "https://shop.example"
    Then the test for "Add to cart" replays the action "Open menu" first
    And the test for "Add to cart" fires the action named "Add to cart"

  Scenario: A transition that changed nothing still replays and fires the action
    # An honest empty diff: the action moved the app but touched no free signal. The
    # test still replays and fires it (a smoke check that the action is still there and
    # performable), asserting no signal change it never recorded.
    Given a mapped transition "Refresh" from "home" to "home" that changed nothing
    When I generate a pytest suite for "https://shop.example"
    Then the test for "Refresh" fires the action named "Refresh"
    And the test for "Refresh" asserts no signal changes

  Scenario: Secrets in captured signals are redacted before they reach a test
    Given a state "vault" whose console logged "Authorization: Bearer sk-supersecrettoken12345"
    And a mapped transition "Open vault" from "home" to "vault"
    When I generate a pytest suite for "https://shop.example"
    Then no generated file contains the raw secret "sk-supersecrettoken12345"
    And some generated file shows the redaction placeholder

  Scenario: A graph with no transitions generates no tests
    # Nothing was mapped to replay, so there is nothing to generate — an empty suite,
    # not a shell of a test that asserts nothing.
    Given an empty explored graph
    When I generate a pytest suite for "https://shop.example"
    Then the suite has no test files
