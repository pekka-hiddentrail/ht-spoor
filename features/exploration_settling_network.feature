# Exploration settling also waits for the network to go idle — ROADMAP.md §2e (7e).
#
# Sub-slice 7b settles on DOM quiescence: it reads a page only once its mutations have
# been quiet for a window. A live diagnostic on the server-rendered PrestaShop bench
# (§5.1) showed that is not enough on its own. A hydration lull longer than the quiet
# window opens while an AJAX widget or lazy-loaded images are still in flight; DOM-quiet
# fires during the lull, and then a late burst of network responses mutates the DOM. Two
# captures of the same screen therefore land on different state ids, and reset-and-replay
# (7d) flags a spurious "replay diverged" and skips the action — coverage lost to a
# capture-timing race, not a real divergence. The measured effect: 6 states, 32
# transitions, 17 skips, every skip a divergence on an ever-present menu link; the
# fully-settled page was deterministic, the wait just fired too early to reach it.
#
# 7e widens the "is the page quiet?" signal to include the network: while any request is
# in flight the page is treated as active, so the wait cannot settle past a late response
# that will still mutate the DOM. The bound is unchanged — a request that never completes
# (a long-poll, a hung fetch) makes the page unsettled at the safety timeout, exactly like
# a page that mutates forever, and the run proceeds on the last snapshot rather than
# hanging. The pure decision is exercised under a fake clock with a scripted network
# signal (no browser); the live half proves the real driver's in-flight request counter
# feeds it, so content fetched after the load event is present by the time discovery
# reads it. Nothing here is site-specific (§0): the same rule waits for every target; the
# fixtures merely stand in for a slow, asynchronously-loaded page.

Feature: Exploration waits for in-flight requests to finish before it reads the page
  As the exploration engine mapping an asynchronously-loaded page
  I want the settle wait to treat the page as busy while a request is in flight
  So that a late network response can't render a different page after I have read it,
  while a request that never completes is recorded as unsettled rather than hanging

  Scenario: An in-flight request holds the page unsettled until it completes
    # The DOM is quiet the whole time, but a request is outstanding until 600 ms. The wait
    # must not settle during the early DOM-quiet lull; it settles only after the request
    # completes and a further quiet window passes — well past the lull, well under timeout.
    Given a quiet window of 200 ms and a settle timeout of 5000 ms
    And a page whose DOM is quiet but a request is in flight until 600 ms
    When the explorer waits for the page to settle
    Then it reports the page settled
    And the wait lasted at least 600 ms
    And it did not wait the full timeout

  Scenario: A request that never completes is reported unsettled, not hung
    # A hung fetch or a long-poll never finishes. The wait ends at the timeout and reports
    # the page did not settle — the explorer proceeds on the last snapshot, never hangs.
    Given a quiet window of 200 ms and a settle timeout of 1000 ms
    And a page whose DOM is quiet but a request stays in flight forever
    When the explorer waits for the page to settle
    Then it reports the page did not settle
    And the wait ended at the timeout

  @browser
  Scenario: Discovery waits for content fetched after the load event
    # The entry page renders instantly and then fetches a fragment whose response the
    # server delays past the quiet window, injecting a button on arrival. DOM-quiet alone
    # would settle during the delay and miss the button; waiting for the network to go
    # idle means the fetched button is present by the time discovery reads the tree.
    Given a live site whose entry page fetches deferred content after a network delay
    When the explorer resets the browser
    Then the discovered actions include the "button" named "Loaded over the network"
