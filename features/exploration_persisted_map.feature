# Loading a persisted exploration map back into a graph — §2e resume, slice 3.
#
# The third slice of the anchored, depth-relative *resume* capability (§2e v2, see
# the resume design note), and the one that makes the earlier slices testable across
# a real save/load boundary. A run persists its graph to maps/<domain>.json as the
# §2h-shareable projection the serving layer produces; this slice is that
# projection's inverse, so a LATER invocation can rebuild the graph, build anchor
# candidates from it, and resolve a selector against a crawl no longer held in memory.
#
# The reconstruction matches what the projection actually carries: state ids (in
# order, root first), each state's action inventory (role + name), and the transition
# topology. That is what `id:` and `path` anchoring need, so both resolve against a
# loaded map. What the projection does NOT carry cannot come back: signals are stored
# as counts without a title, so a loaded state has no title and `title:` finds
# nothing against a saved map (extending the projection is its own slice). The core
# scenario is a round-trip — project a known graph, load it back — which is exactly
# how we validate that the resume machinery works end to end, not just in memory.
# Nothing is site-specific (§0): every stored map is read the same way.

Feature: A persisted exploration map loads back into a resolvable graph
  As a user resuming exploration in a new run
  I want the map an earlier run saved rebuilt into a graph
  So that I can anchor a resume by id or path against a crawl no longer in memory,
  and be told plainly that a title (which the saved map does not keep) matches nothing

  Background:
    Given an explored graph with states:
      | id       | title            |
      | s0000000 | Home             |
      | s1111111 | Search results   |
      | s2222222 | Account          |
    And explored transitions:
      | from     | action        | to       |
      | s0000000 | link=Search   | s1111111 |
      | s1111111 | button=Go     | s2222222 |
    And the graph is persisted to its shareable map

  Scenario: Loading the persisted map restores the states in order
    When I load the persisted map into a graph
    Then the loaded graph has states "s0000000", "s1111111" and "s2222222"

  Scenario: Loading the persisted map restores the transition topology
    When I load the persisted map into a graph
    Then the loaded graph has 2 transitions

  Scenario: An id selector resolves against candidates from the loaded map
    When I load the persisted map into a graph
    And I build anchor candidates from the loaded graph
    And I resolve the selector "id:s1111111" against them
    Then it resolves to the state "s1111111"

  Scenario: A path selector resolves against candidates from the loaded map
    When I load the persisted map into a graph
    And I build anchor candidates from the loaded graph
    And I resolve the path selector "link=Search>button=Go" against them
    Then it resolves to the state "s2222222"

  Scenario: A title selector finds nothing because the saved map keeps no title
    When I load the persisted map into a graph
    And I build anchor candidates from the loaded graph
    And I resolve the selector "title:Search results" against them
    Then it reports no matching state

  Scenario: The round-trip preserves the anchors id and path resolve to
    When I resolve "id:s2222222" against the original in-memory graph
    And I load the persisted map into a graph
    And I resolve "id:s2222222" against the loaded graph
    Then both resolve to the same state "s2222222"

  Scenario: An empty map loads into an empty graph
    Given an empty persisted map
    When I load the persisted map into a graph
    Then the loaded graph has no states
