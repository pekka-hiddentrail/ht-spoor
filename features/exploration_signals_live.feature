# Live per-transition signal capture: the real Playwright driver — ROADMAP.md §2e.
#
# Sub-slice 5c-ii of the fifth §2e slice. Sub-slice 5c-i built the pure signal model
# (StateSignals + diff_signals) and wired it through the explorer against a fake
# driver; this fills the bundle from a REAL page. It drives the real PlaywrightDriver
# against a signal-rich static fixture served over a loopback socket and asserts that
# capture_signals reads genuine console output, web-storage keys, network requests,
# accessibility nodes, and a screenshot — and that the before/after diff of a real
# click reports what that click actually changed. Nothing here is site-specific (§0):
# the same five signals are read from every target.

Feature: The live browser driver captures real page signals
  As the exploration engine mapping a target with no config
  I want the real driver to read every free signal from the live page
  So that each transition records what pressing a button truly changed

  Scenario: The captured bundle reflects the live page
    Given a live browser on the signals fixture "explore_signals_home.html"
    When I capture the current signals
    Then the bundle has a screenshot hash
    And the bundle includes the storage key "session"
    And the bundle logged the console message "home ready"
    And the bundle counts more than zero accessibility nodes

  Scenario: The diff of a real click reports what it changed
    # Clicking "Go next" logs to the console, writes a storage key, fires a fetch,
    # and navigates to a visually-distinct page — the diff must capture each.
    Given a live browser on the signals fixture "explore_signals_home.html"
    When I capture, click "Go next", and capture again
    Then the diff added the console message "going next"
    And the diff added the storage key "opened"
    And the diff recorded at least one network request
    And the diff marks the screenshot as changed

  Scenario: A reset scopes captured signals to the current visit
    # The console and network buffers accumulate across reloads within a visit, so
    # without scoping a state reached late in the run would show the whole session's
    # cumulative output. Reset-and-replay revisits a state as a fresh first visit, so a
    # reset clears the buffers: signals captured after it reflect only this visit, not
    # an earlier walk's fetch to "/ping.txt" or its "going next" console line. The
    # click's own before/after diff is unaffected — its two captures straddle a single
    # action with no reset between them (the scenario above still holds).
    Given a live browser on the signals fixture "explore_signals_home.html"
    When I capture, click "Go next", then reset and capture
    Then the reset capture omits the network request "/ping.txt"
    And the reset capture omits the console message "going next"
    And the reset capture includes the console message "home ready"
