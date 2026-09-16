# Resuming exploration from an anchor state — §2e resume, the traversal slice.
#
# The payoff of the resume capability (§2e v2, see the resume design note). The three
# earlier slices are pure logic: resolve a selector to a state (state_selector), build
# candidates from a graph (graph_candidates), and load a persisted map back into a graph
# (persisted_map). This slice ties them to the crawl itself: given a saved map and a
# selector, `resume_exploration` loads the map, resolves the selector to one anchor
# state, resets-and-replays to it, and continues the breadth-first walk *outward from
# there* — merging every newly discovered state and transition back into the loaded map.
#
# Two behaviours are the point. (1) The walk is re-origined at the anchor: the depth
# budget counts clicks *from the anchor*, not from the site root, so a state many clicks
# deep is still reachable within a small budget once you resume from nearby. (2) The
# merge is additive: the states and transitions the earlier run mapped are preserved,
# and the new ones are added — resuming never discards what was already known.
#
# Resolution never guesses (the same stance the selector and serving layers take): a
# selector matching no saved state, or several, fails loudly rather than picking one.
# And because replay depends on the saved paths still being walkable, a target whose
# start page no longer matches the saved map is refused up front, not silently remapped.
#
# The fast-tier scenarios drive the real load -> resolve -> resume chain in-process
# against a fake site (no browser); the tagged scenario proves the same end to end in a
# real headless browser over the A -> B -> C fixture chain. Nothing here is
# site-specific (§0): one resume mechanism continues the walk for every target.

Feature: Exploration resumes from a mapped anchor and crawls outward
  As a user who mapped a site once and wants to go deeper from a known screen
  I want to name an anchor an earlier run reached and continue exploring from it
  So that a bounded crawl can reach states far from the start without re-walking
  everything, and the earlier map is extended rather than thrown away

  Background:
    Given a site whose pages are:
      | from | label | role | to   | url  |
      | home | To A  | link | a    | /a   |
      | a    | To B  | link | b    | /b   |
      | b    | To C  | link | c    | /c   |
    And an earlier crawl from "home" with a depth budget of 1 was saved

  Scenario: Resuming from an anchor discovers the states beyond it
    When I resume from the state reached by "To A" with a depth budget of 1
    Then the resumed map has page "b"
    And the earlier crawl had not mapped page "b"

  Scenario: The earlier map is preserved when resuming (the merge is additive)
    When I resume from the state reached by "To A" with a depth budget of 1
    Then the resumed map still has pages: home, a
    And the resumed map has a transition "home --To A--> a"

  Scenario: The depth budget is measured from the anchor, not the site root
    When I resume from the state reached by "To A" with a depth budget of 2
    Then the resumed map has page "c"

  Scenario: A crawl from the start with the same budget does not reach that deep
    When I crawl afresh from "home" with a depth budget of 2
    Then the fresh map does not have page "c"

  Scenario: Resuming from the root maps the whole site into the earlier map
    When I resume from the start page with a depth budget of 9
    Then the resumed map has page "c"
    And the resumed map still has pages: home, a

  Scenario: A selector that matches no saved state fails loudly
    When I resume from the selector "id:deadbeefdeadbeef" with a depth budget of 1
    Then resuming is refused because the selector matched no state

  Scenario: Resuming against a start page that no longer matches the saved map is refused
    Given a different site whose start page differs from the saved map
    When I resume that different site from the state reached by "To A" with a depth budget of 1
    Then resuming is refused because the start page no longer matches the saved map

  @browser
  Scenario: Resuming continues the walk in a real browser and reaches a new page
    Given an earlier live crawl of "explore_resume_a.html" at depth 1 was saved
    When I resume the live crawl from the state reached by "To B" at depth 1
    Then the resumed live map has a page titled "Resume C"
    And the earlier live crawl had not reached "Resume C"
