# Live URL reporting for the crawl frontier — ROADMAP.md §2e (slice 9).
#
# The live half of slice 9. exploration_traversal.feature pins the pure breadth-first
# walk, the depth bound, and the URL-path frontier fork against a fake site; but the
# fork is worth nothing unless the real driver actually reports the page URL — and
# reports it *after* a navigation, not the stale entry URL. This scenario proves that
# end to end in a headless browser: the real PlaywrightDriver's current_url tracks a
# real navigation from one page to the next, which is the signal the explorer forks on.
#
# Nothing here is site-specific (§0): current_url reads Playwright's live page URL for
# every target; the two-page fixture merely stands in for any navigation.

@browser
Feature: The live driver reports the current page URL for the crawl frontier
  As the exploration engine forking its frontier on the URL path
  I want the driver to report the URL of the page actually loaded now
  So that a navigation to a distinct page is seen as a distinct thing to explore

  Scenario: The reported URL tracks a navigation from one page to the next
    Given a live browser on the traversal fixture "explore_home.html"
    Then the driver reports a current URL ending in "explore_home.html"
    When I actuate the "link" named "Open next"
    Then the driver reports a current URL ending in "explore_next.html"
