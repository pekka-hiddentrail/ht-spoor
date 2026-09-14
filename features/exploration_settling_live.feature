# Exploration settling and reset fidelity, live — ROADMAP.md §2e (sub-slice 7b).
#
# The live half of 7b, exercised against real fixtures in a headless browser. Where
# exploration_settling.feature pins the pure quiescence decision under a fake clock,
# these scenarios prove the two things that decision is worth nothing without on a real,
# stateful, asynchronously-rendered page:
#
#   1. Reset fidelity. Reset-and-replay navigation assumes reset() returns the app to
#      its initial state. But a browser context persists cookies and web storage across
#      navigations, so a plain re-navigation lands on a *returning-visitor* render, not a
#      first visit — replay then diverges from what discovery saw. 7b's reset clears
#      cookies, localStorage and sessionStorage before navigating, so every reset is a
#      true first visit. One browser context is kept (cheap, stable); only the per-origin
#      state is wiped.
#
#   2. Real quiescence before reading. After a reset or a click the driver waits for DOM
#      mutations to go quiet (a real MutationObserver, the live counterpart of the pure
#      decider) before it reads the DOM or the accessibility tree — so discovery and
#      actuation see the same settled page. Content that renders asynchronously after the
#      load event is present by the time discovery reads it.
#
#   3. A never-settling page is a recorded fact, not a crash. A page that mutates forever
#      never goes quiet; the driver stops at the settle timeout, records the state as "did
#      not settle", and proceeds on the last snapshot. The run neither hangs nor aborts,
#      and the unsettled flag is visible on the captured state.
#
# Nothing here is site-specific (§0): the same reset and the same quiescence wait apply
# to every target; the fixtures merely stand in for the general behaviours (persisted
# state, deferred rendering, endless churn) that any real page can exhibit.

Feature: Exploration resets to a clean first visit and waits for real quiescence
  As the exploration engine mapping a stateful, asynchronously-rendered target
  I want each reset to clear persisted state and each read to follow DOM quiescence
  So that replay is deterministic and a never-quiet page is recorded, not fatal

  Scenario: Reset clears cookies and storage so replay is a true first visit
    # The fixture shows first-visit content until it records a return marker in cookies
    # and web storage; a plain re-navigation would then show returning-visitor content.
    Given a live browser on the settling fixture "settle_returning_visitor.html"
    When the page has recorded a return visit
    And the explorer resets the browser
    Then the page shows its first-visit content

  Scenario: Discovery waits for content that renders after the load event
    # The fixture appends an actionable button a short time after load. With quiescence
    # the driver reads the tree only once mutations stop, so the deferred button is found.
    Given a live browser on the settling fixture "settle_deferred_content.html"
    When the explorer resets the browser
    Then the discovered actions include the "button" named "Deferred action"

  Scenario: A page that never stops mutating is recorded as unsettled, not fatal
    # The fixture mutates the DOM forever. The driver waits only to the settle timeout,
    # then captures the state flagged as unsettled and carries on — no hang, no crash.
    Given a live browser on the settling fixture "settle_never_quiet.html"
    When the explorer resets the browser
    Then the captured state is flagged as unsettled
