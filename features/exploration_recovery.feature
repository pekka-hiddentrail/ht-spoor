# Exploration recovery: dealing with blockers instead of dying on them — ROADMAP.md §2e.
#
# Today the explorer abandons an action the moment its element can't be actuated, and
# records a mute skip. When the screen sits behind a *resolvable* layer — a welcome
# dialog, a consent panel, a chat widget that intercepts the click — that collapses the
# whole map to the first screen. A crawler that dies on the first screen because it is
# not the simplest one is not useful.
#
# This capability teaches the explorer to treat a blocking layer as its own state and
# to *interact its way past it* toward making the original action reachable — then fire
# the original action and carry on. It never guesses with a model (the recovery is the
# same deterministic discovery + safety gate the explorer already applies everywhere),
# and it never weakens the §2e non-negotiable: every interaction with the layer, like
# every other action, passes the safety gate, so a layer whose only exit is a
# destructive action outside a sandbox stays blocked rather than being forced. When it
# cannot get past, it FLAGS the blocker with a real reason instead of a mute skip, and
# never loops.
#
# Most scenarios are pure logic against a fake app (as exploration_loop.feature is): a
# layer covers a state, intercepting its actions until the layer's own actions clear it.
# The last scenario drives the whole real stack against a live fixture whose entry
# screen is behind an overlay, proving the recovery works in a real browser.

Feature: Exploration deals with blockers instead of abandoning what is behind them
  As someone pointing autonomous exploration at a real target
  I want the explorer to interact past a recoverable layer that blocks a click
  So that a site guarded by a welcome or consent overlay is still mapped, not lost

  Scenario: A blocker is dealt with so the actions behind it are mapped
    # "home" is covered by a consent layer whose one action clears it. Both of home's
    # own actions are mapped — which is only possible if the layer is cleared again
    # each time reset-and-replay returns to home, not merely the first time.
    Given a sandbox target
    And an app whose actions are:
      | from | label     | role   | to   |
      | home | Open menu | button | menu |
      | home | Open cart | button | cart |
    And the "home" state is covered by a layer whose actions are:
      | label          | role   | clears |
      | Accept cookies | button | yes    |
    When I explore from "home"
    Then the graph has a transition "home --Open menu--> menu"
    And the graph has a transition "home --Open cart--> cart"
    And the graph has states: home, menu, cart

  Scenario: A multi-step blocker is worked through, not abandoned
    # The layer is not cleared by a single click: it takes "Manage" (which changes the
    # layer but does not clear it) and then "Confirm choices" (which does). The explorer
    # must converge over several steps, driven by progress, rather than trying once.
    Given a sandbox target
    And an app whose actions are:
      | from | label     | role   | to   |
      | home | Open menu | button | menu |
    And the "home" state is covered by a layer cleared only by this sequence:
      | step | label           | role   |
      | 1    | Manage cookies  | button |
      | 2    | Confirm choices | button |
    When I explore from "home"
    Then the graph has a transition "home --Open menu--> menu"
    And the graph has states: home, menu

  Scenario: A blocker whose only exit is a destructive action stays blocked outside a sandbox
    # The §2e non-negotiable holds through recovery: the only action that would clear
    # the layer is destructive, and on a real target the gate skips it — so the layer is
    # never forced open. The blocked action is flagged (not fired), and the destructive
    # layer action is itself recorded as skipped. Recovery is never a backdoor.
    Given a real target
    And an app whose actions are:
      | from | label     | role   | to   |
      | home | Open menu | button | menu |
    And the "home" state is covered by a layer whose actions are:
      | label          | role   | clears |
      | Delete cookies | button | yes    |
    When I explore from "home"
    Then the layer action "Delete cookies" from "home" is skipped
    And the action "Open menu" from "home" is flagged as blocked by an unresolved layer
    And the graph has no transitions

  Scenario: An unresolvable blocker is flagged, and exploration carries on elsewhere
    # A layer no available action can clear (think a CAPTCHA a click cannot solve) blocks
    # the actions behind it. The explorer flags them with a reason, does not loop, and
    # keeps mapping the parts of the site that are not behind the layer.
    Given a sandbox target
    And an app whose actions are:
      | from | label         | role   | to       |
      | home | Open menu     | button | menu     |
      | home | Open help     | button | help     |
      | menu | Open settings | button | settings |
    And the "menu" state is covered by a layer that nothing clears:
      | label     | role   |
      | I am human | button |
    When I explore from "home"
    Then the graph has a transition "home --Open menu--> menu"
    And the graph has a transition "home --Open help--> help"
    And the action "Open settings" from "menu" is flagged as blocked by an unresolved layer
    And the graph has states: home, menu, help

  Scenario: A genuinely missing element is flagged as missing, not treated as a blocker
    # Recovery only applies when the element is there but covered. An element that is
    # simply gone after reset-and-replay (nothing is intercepting the click) must be
    # flagged as not located and skipped — the explorer must not spin trying to "clear"
    # a layer that does not exist.
    Given a sandbox target
    And an app whose actions are:
      | from | label   | role   | to   |
      | home | Missing | button | dead |
      | home | Open    | button | menu |
    And the action "Missing" cannot be located
    When I explore from "home"
    Then the action "Missing" from "home" is flagged as not located
    And the graph has a transition "home --Open--> menu"
    And the graph has states: home, menu

  @browser
  Scenario: Mapping a live site whose entry screen is behind an overlay
    # The whole real stack: a headless browser against a fixture that shows a consent
    # overlay intercepting every click until it is accepted. Before this capability the
    # explorer would map only the overlay screen; now it clears the overlay and maps the
    # site behind it.
    Given a live fixture site starting at "explore_gated.html"
    When I run spoor explore against it
    Then it reports more than 1 state discovered
    And it reports at least 1 action recovered from behind a blocker
