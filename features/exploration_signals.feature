# Per-transition signal capture: the free-signal bundle and its diff — ROADMAP.md §2e.
#
# Sub-slice 5c of the fifth §2e slice, built logic-first (see the §2e decomposition
# note in ROADMAP.md). This file covers sub-slice 5c-i: the pure-logic signal model
# and its wiring into the explorer. §2e captures a "free/near-free" signal bundle for
# every transition — the accessibility snapshot, console output, client-side storage,
# the network/HAR trace, and a screenshot — and records what each fired action
# CHANGED. This slice pins the model (a StateSignals bundle captured at each state,
# and a before/after diff computed for each transition) and that the explorer attaches
# a bundle to every state node and a diff to every transition. It runs in-process
# against the fake driver through a new capture_signals() seam on the BrowserDriver
# protocol; filling that bundle from a real page (real screenshot hash, live HAR and
# console deltas) is sub-slice 5c-ii.
#
# In these scenarios a fake app gives each state a signal bundle. State names are a
# test convenience; the explorer only ever sees the abstracted state id.

Feature: The explorer records a signal diff for every transition
  As the exploration engine mapping a target with no config
  I want each transition to record what its action changed on every free signal
  So that the map answers "what happens, on every signal level, when I press this"

  Background:
    Given a sandbox app whose states are:
      | state | ax_nodes | console      | storage      | network         | screenshot |
      | home  | 3        | ready        | guest        |                 | hashA      |
      | menu  | 5        | ready; open  | guest; token | /api/menu       | hashB      |
      | home2 | 3        | ready        | guest        |                 | hashA      |

  Scenario: A transition records what its action changed across every signal
    Given an action "Open menu" (button) from "home" to "menu"
    When I explore from "home"
    Then the transition "home --Open menu--> menu" added console messages: open
    And the transition "home --Open menu--> menu" added storage keys: token
    And the transition "home --Open menu--> menu" removed no storage keys
    And the transition "home --Open menu--> menu" added network requests: /api/menu
    And the transition "home --Open menu--> menu" has an accessibility node delta of 2
    And the transition "home --Open menu--> menu" changed the screenshot

  Scenario: A transition that changes nothing records an empty, no-change diff
    # home and home2 carry identical signal bundles: firing this action moves the app
    # but touches no free signal, and the diff must say so honestly.
    Given an action "Refresh" (button) from "home" to "home2"
    When I explore from "home"
    Then the transition "home --Refresh--> home2" added no console messages
    And the transition "home --Refresh--> home2" added no storage keys
    And the transition "home --Refresh--> home2" added no network requests
    And the transition "home --Refresh--> home2" has an accessibility node delta of 0
    And the transition "home --Refresh--> home2" did not change the screenshot

  Scenario: A transition records storage keys removed as well as added
    Given an action "Log out" (button) from "menu" to "home"
    When I explore from "menu"
    Then the transition "menu --Log out--> home" removed storage keys: token
    And the transition "menu --Log out--> home" added no storage keys

  Scenario: Each state node carries the signal bundle captured there
    Given an action "Open menu" (button) from "home" to "menu"
    When I explore from "home"
    Then the state "home" recorded 3 accessibility nodes
    And the state "menu" recorded 5 accessibility nodes
