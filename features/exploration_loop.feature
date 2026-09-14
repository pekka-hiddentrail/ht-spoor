# Exploration explorer loop: the state-graph explorer — ROADMAP.md §2e.
#
# The fifth §2e slice, built logic-first in sub-slices (see the §2e decomposition
# note in ROADMAP.md). This file covers sub-slice 5a: the pure-logic graph model and
# the `explore` orchestrator, which ties together the four earlier slices —
#   * discovery (slice 3) to find the actionable elements in each state,
#   * the safety gate (slice 1) to decide which actions may be fired,
#   * state abstraction (slice 2) to recognise a revisited state instead of looping,
#   * run controls (slice 4) to bound and stop the run —
# into a `state --action--> state` graph. It runs against an injected BrowserDriver
# protocol, so the whole loop is exercised in-process with a fake deterministic app;
# the real Playwright driver, a live-browser run, and the `spoor explore` command are
# sub-slice 5b. Signal capture per transition is sub-slice 5c.
#
# In these scenarios a fake app is described as a transition table: each row is one
# action available in the `from` state that leads to the `to` state. State names are
# a test convenience — the explorer itself only ever sees the abstracted state id.

Feature: The explorer builds a state-action graph
  As the exploration engine mapping a target with no config
  I want to fire each discovered action and record where it leads
  So that the whole product becomes a browsable state --action--> state graph

  Scenario: The explorer maps a simple two-state app
    Given a sandbox target
    And an app whose actions are:
      | from | label      | role   | to   |
      | home | Open menu  | button | menu |
      | menu | Close menu | button | home |
    When I explore from "home"
    Then the graph has states: home, menu
    And the graph has a transition "home --Open menu--> menu"
    And the graph has a transition "menu --Close menu--> home"

  Scenario: A revisited state is recognised, not duplicated
    # Two different actions from home both land on the same state; state abstraction
    # (slice 2) collapses them to one node, and its actions are explored only once.
    Given a sandbox target
    And an app whose actions are:
      | from   | label | role   | to     |
      | home   | Go A  | button | shared |
      | home   | Go B  | button | shared |
      | shared | Back  | button | home   |
    When I explore from "home"
    Then the graph has states: home, shared
    And the graph has a transition "home --Go A--> shared"
    And the graph has a transition "home --Go B--> shared"
    And the graph has a transition "shared --Back--> home"

  Scenario: A destructive action on a real target is skipped, never fired
    # The state behind a destructive action is never reached on a non-sandbox target:
    # the worst case is "missed a state", never "deleted real data" (§2e).
    Given a real target
    And an app whose actions are:
      | from | label          | role   | to   |
      | home | Delete account | button | gone |
    When I explore from "home"
    Then the action "Delete account" from "home" is skipped
    And the graph has states: home

  Scenario: The same destructive action is fired inside a sandbox
    Given a sandbox target
    And an app whose actions are:
      | from | label          | role   | to   |
      | home | Delete account | button | gone |
    When I explore from "home"
    Then the graph has states: home, gone
    And the graph has a transition "home --Delete account--> gone"

  Scenario: An action that cannot be performed is recorded, and the run continues
    # On a live, dynamic site a discovered element can be gone, hidden, or otherwise
    # unclickable by the time reset-and-replay returns to it. That must never abort the
    # whole run: the action is recorded as skipped (with why), and exploration carries
    # on with the rest of the map. This is what makes a wiki reliably produced against
    # a real target rather than only against a static fixture.
    Given a sandbox target
    And an app whose actions are:
      | from | label  | role   | to   |
      | home | Broken | button | dead |
      | home | Open   | button | menu |
    And the action "Broken" cannot be performed
    When I explore from "home"
    Then the action "Broken" from "home" is skipped
    And the graph has a transition "home --Open--> menu"
    And the graph has states: home, menu

  Scenario: The run stops when the state budget is reached
    Given a sandbox target with a budget of max_states 2
    And an app whose actions are:
      | from | label | role   | to |
      | home | Next  | button | s1 |
      | s1   | Next  | button | s2 |
      | s2   | Next  | button | s3 |
    When I explore from "home"
    Then the graph has 2 states

  Scenario: A run killed before it starts explores nothing beyond the root
    Given a sandbox target whose kill switch is already thrown
    And an app whose actions are:
      | from | label | role   | to   |
      | home | Next  | button | next |
    When I explore from "home"
    Then the graph has states: home
    And the graph has no transitions
