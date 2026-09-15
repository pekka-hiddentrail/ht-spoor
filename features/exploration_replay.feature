# Exploration survives a flaky, nondeterministic replay — ROADMAP.md §2e.
#
# The explorer navigates by reset-and-replay: to revisit a state it resets to the start
# and replays the actions that first reached it. That rests on the target being a
# deterministic function of the action sequence from a clean start — but a real SPA is
# not. A live diagnostic against the Juice Shop bench showed the same reset landing on a
# *degraded* render under load (an intermittently-present "Force page reload" fallback,
# element counts flipping 6 ↔ 7), so a step found on the first visit can be gone by the
# time replay returns to it. Two flaws turned that transient into lost coverage: replay
# was all-or-nothing (one flaky step killed the whole subtree behind it), and the skip
# was mis-attributed to the leaf action rather than the replay step that actually failed.
#
# This capability makes replay resilient and honest. Resilient: a reset-and-replay that
# can't reach a step, or that lands on a *different* state than when the path was first
# mapped, is retried a bounded number of times — a transient degraded render usually
# clears on the next reset, so coverage that used to be lost is regained. Honest: when
# retries are exhausted the action is flagged with a real reason that distinguishes a
# step that stayed unreachable from a replay that *diverged* to another state (verified
# against the state id first mapped for that step), and never a mute skip. A layer that
# is stably blocked (recovery's concern, §2e 7c) is reported at once, not retried — there
# is nothing transient to wait out.
#
# The pure scenarios drive the explorer in-process against a fake app that can be told to
# make a step transiently or persistently miss, or transiently or persistently diverge;
# the final scenario drives the whole real stack against a scripted server whose first
# render of the entry page is degraded, proving retry regains coverage in a real browser.

Feature: Exploration survives a flaky, nondeterministic reset-and-replay
  As someone pointing autonomous exploration at a real, asynchronously-rendered target
  I want a transient bad render during replay to be retried, and a real divergence flagged
  So that coverage is not lost to a flaky reload and the map never lies about what it reached

  Scenario: A transient replay miss is retried so the state behind it is still mapped
    # Reaching "vault" replays through "Enter". On the first replay the reset lands on a
    # degraded render where "Enter" is gone; a retry meets a good render and the path
    # completes — so "vault" is mapped, not lost to one bad reload.
    Given a sandbox target
    And an app whose actions are:
      | from | label | role   | to    |
      | home | Enter | button | hall  |
      | hall | Look  | button | vault |
    And the action "Enter" is missing on the first replay but present afterwards
    When I explore from "home"
    Then the graph has a transition "hall --Look--> vault"
    And the graph has states: home, hall, vault

  Scenario: A persistently unreachable replay step is flagged honestly, not silently dropped
    # If every reset lands on a render missing "Enter", no retry can complete the path.
    # The action behind it is flagged with a reason naming the replay step that could not
    # be reached — not a mute skip, and not mis-attributed as the leaf being missing.
    Given a sandbox target
    And an app whose actions are:
      | from | label | role   | to    |
      | home | Enter | button | hall  |
      | hall | Look  | button | vault |
    And the action "Enter" is missing on every replay
    When I explore from "home"
    Then the graph has a transition "home --Enter--> hall"
    And the action "Look" from "hall" is flagged as an unreachable replay step
    And the graph has states: home, hall

  Scenario: A replay that lands on the wrong state is detected and flagged as divergence
    # Replaying "Enter" always lands somewhere other than the "hall" it first mapped to.
    # Firing "Look" there would record a false edge, so the fidelity check catches the
    # divergence against the state id first seen and flags it distinctly, rather than
    # silently mapping "Look" from the wrong place.
    Given a sandbox target
    And an app whose actions are:
      | from | label | role   | to    |
      | home | Enter | button | hall  |
      | hall | Look  | button | vault |
    And the action "Enter" always lands on a different state on replay
    When I explore from "home"
    Then the graph has a transition "home --Enter--> hall"
    And the action "Look" from "hall" is flagged as a replay divergence
    And the graph has states: home, hall

  Scenario: A transient divergence is retried so the state is still mapped
    # The first replay of "Enter" lands on the wrong state; a retry lands correctly, so
    # "vault" is mapped. A single bad render must not cost the branch behind it.
    Given a sandbox target
    And an app whose actions are:
      | from | label | role   | to    |
      | home | Enter | button | hall  |
      | hall | Look  | button | vault |
    And the action "Enter" lands on a different state on the first replay but is correct afterwards
    When I explore from "home"
    Then the graph has a transition "hall --Look--> vault"
    And the graph has states: home, hall, vault

  @browser
  Scenario: Mapping a live site whose first render of a step is degraded
    # The whole real stack: a scripted server whose entry page is served degraded on one
    # reset (no link to the page behind it) and complete otherwise. Without retry the
    # explorer would give up on that reset and map only the entry screen; with retry it
    # meets a good render on the next reset and maps the page behind the flaky one.
    Given a live site whose entry page is degraded on the first replay
    When I run spoor explore against it
    Then it reports more than 1 state discovered
