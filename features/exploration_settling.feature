# Exploration settling: wait for a real signal that rendering stopped — ROADMAP.md §2e.
#
# Sub-slice 7b's pure core. A live diagnostic against a real SPA showed the explorer's
# skips were not overlay interception (7a fixed the actuation engine) but that the page
# it *discovered* was not the page it *acted on*: discovery ran at one rendering instant
# and the fired action at another, so an element genuinely present at discovery time was
# absent by click time (every action skipped "not located", zero transitions). The cause
# is asynchronous rendering that continues after the crude "network is idle" signal.
#
# 7b waits for a *real* signal that rendering has stopped — DOM quiescence: no mutations
# for a quiet window — rather than a fixed sleep or a network heuristic. The wait is
# bounded: a settle timeout is only a safety net, never the normal path. Crucially, a
# page that never goes quiet (a busy SPA that polls forever) must NOT crash the run or
# hang it — the explorer records the state as "did not settle" and proceeds on the last
# snapshot, honestly flagging that the state is unreliable rather than pretending it
# settled. This is the pure decision, driven by a mutation signal and an injectable
# clock (the `RunController` seam), so it is exercised deterministically with no browser;
# the real `MutationObserver` and the reset that restores a clean first-visit state are
# 7b's live half (exploration_settling_live.feature). Nothing here is site-specific (§0):
# the same quiescence rule waits for every target.

Feature: Exploration waits for the page to stop rendering before it reads or acts
  As the exploration engine mapping an asynchronously-rendered page
  I want to wait for DOM mutations to go quiet, bounded by a safety timeout
  So that discovery and actuation see the same settled page, and a never-quiet page is
  recorded as unreliable rather than crashing or hanging the run

  Scenario: A page that keeps mutating and then stops is reported settled
    # Mutations continue for a while, then cease; once the quiet window passes with no
    # further mutation the page is settled — and the wait ends well before the timeout.
    Given a quiet window of 200 ms and a settle timeout of 5000 ms
    And a page that mutates for 600 ms and then stops
    When the explorer waits for the page to settle
    Then it reports the page settled
    And it did not wait the full timeout

  Scenario: A page that is already quiet settles after one quiet window
    Given a quiet window of 200 ms and a settle timeout of 5000 ms
    And a page that never mutates
    When the explorer waits for the page to settle
    Then it reports the page settled

  Scenario: A page that never stops mutating is reported unsettled, not crashed
    # A busy SPA that polls or animates forever never goes quiet. The wait must end at
    # the timeout and report the page did not settle — the explorer proceeds on the last
    # snapshot and flags the state, never loops or aborts.
    Given a quiet window of 200 ms and a settle timeout of 1000 ms
    And a page that mutates continuously
    When the explorer waits for the page to settle
    Then it reports the page did not settle
    And the wait ended at the timeout
