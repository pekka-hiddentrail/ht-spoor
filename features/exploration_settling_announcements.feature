# Exploration settling also waits out urgent live-region announcements — §2e (7f).
#
# 7b settles on DOM quiescence and 7e widens "is the page quiet?" to the network. A live
# diagnostic on the Juice Shop bench (§5.1) showed a third, distinct capture-timing race.
# The entry page renders, goes DOM-quiet and network-idle for several seconds, and only
# then removes a transient toast it had shown on load (an "assertive" ARIA live region
# that auto-dismisses on a timer, no network involved). DOM-quiet + network-idle both
# fire during that long lull, so one capture includes the toast and a later one does not:
# two captures of the same screen land on different state ids, and reset-and-replay (7d)
# flags a spurious "reset did not return to the start state" and skips the action. The
# measured effect was a graph shape that reproduced for several runs then drifted when
# the runner's timing straddled the dismissal — a capture-timing race, not real drift.
#
# 7f widens the signal once more: an *urgent* live-region announcement in progress —
# `aria-live="assertive"` or `role="alert"` holding text — is treated as page activity,
# so the wait cannot settle while such an announcement is on screen and reads only the
# page left behind once it clears. This is deliberately narrow: `assertive`/`alert` mark
# an interrupting, by-nature transient announcement, whereas `polite`/`status` regions
# are commonly durable status (Juice Shop's persistent cookie banner is `aria-live=
# "polite"`) and must NOT hold the page unsettled forever. The bound is unchanged — an
# assertive region that never clears makes the page unsettled at the safety timeout,
# exactly like a page that mutates or fetches forever, and the run proceeds on the last
# snapshot rather than hanging. The pure decision is exercised under a fake clock with a
# scripted announcement signal (no browser); the live half proves the real driver detects
# an on-screen assertive announcement and holds the wait until it clears. Nothing here is
# site-specific (§0): the same ARIA rule waits for every target.

Feature: Exploration waits out an urgent announcement before it reads the page
  As the exploration engine mapping a page that shows a transient announcement on load
  I want the settle wait to treat an in-progress assertive announcement as page activity
  So that a toast that auto-dismisses can't leave two captures of one screen on different
  state ids, while a durable status region never holds the page unsettled

  Scenario: An assertive announcement holds the page unsettled until it clears
    # The DOM is quiet and the network idle the whole time, but an assertive announcement
    # is on screen until 600 ms. The wait must not settle during the quiet lull; it settles
    # only after the announcement clears and a further quiet window passes.
    Given a quiet window of 200 ms and a settle timeout of 5000 ms
    And a page whose DOM is quiet but an assertive announcement is showing until 600 ms
    When the explorer waits for the page to settle
    Then it reports the page settled
    And the wait lasted at least 600 ms
    And it did not wait the full timeout

  Scenario: An announcement that never clears is reported unsettled, not hung
    # A page that keeps asserting (a stuck toast, a polling announcer) never goes quiet.
    # The wait ends at the timeout and reports unsettled — the explorer proceeds on the
    # last snapshot and flags the state, never loops or aborts.
    Given a quiet window of 200 ms and a settle timeout of 1000 ms
    And a page whose DOM is quiet but an assertive announcement never clears
    When the explorer waits for the page to settle
    Then it reports the page did not settle
    And the wait ended at the timeout

  @browser
  Scenario: A capture waits out a toast that auto-dismisses after the load
    # The entry page renders instantly, shows an assertive toast carrying a button, and
    # removes it on a timer past the quiet window. Settling on DOM-quiet alone would read
    # the page while the toast is up; waiting out the announcement means the settled read
    # is the page left behind, so the toast's button is gone by the time discovery reads.
    Given a live site whose entry page shows a toast that auto-dismisses after a delay
    When the explorer resets the browser
    Then the discovered actions do not include the "button" named "Dismiss notification"
