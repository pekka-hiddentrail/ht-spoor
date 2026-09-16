# Building anchor candidates from an exploration graph — §2e resume, slice 2.
#
# The second slice of the anchored, depth-relative *resume* capability (§2e v2, see
# the resume design note). Slice 1 (exploration_state_selector) resolves a selector
# over an abstract candidate set; this slice is the adapter that produces that set
# from a real in-memory ExplorationGraph, so a resume run can name an anchor by what
# an earlier run actually mapped. Still pure logic: no browser, no disk.
#
# Each mapped state becomes one candidate. Its `id` is the state id; its `title` is
# the state's captured page title, run through the same secret redaction the wiki
# applies before anything is shared (§2h) — and is absent when the state carries no
# captured signals, so such a state is still anchorable by id or path. Its `path` is
# the shortest reset-and-replay action sequence from the root (the graph's
# `paths_from_root` primitive; the root's path is empty).
#
# One kind is deliberately NOT populated: a per-state URL. Neither the state node nor
# its signal bundle records a URL — a state is DOM-identity only, and one state can
# render at several routes — so `url:` cannot resolve against a graph today. That is
# its own decision slice (see the resume design note); here the gap is pinned
# honestly: candidates carry no url, so a url selector finds nothing. Nothing is
# site-specific (§0): the adapter reads any graph the same way.

Feature: Anchor candidates are built from an exploration graph
  As a user resuming exploration from a state an earlier run mapped
  I want the states that run discovered turned into resolvable anchor candidates
  So that I can name one by its title or the path that reaches it, with secrets
  redacted, and be told plainly that a route is not something a state records

  Background:
    Given an explored graph with states:
      | id       | title            |
      | s0000000 | Home             |
      | s1111111 | Search results   |
      | s2222222 | Welcome back Bearer abc123def456ghi789 |
      | s3333333 |                  |
    And explored transitions:
      | from     | action        | to       |
      | s0000000 | link=Search   | s1111111 |
      | s1111111 | button=Go     | s2222222 |
      | s0000000 | link=Account  | s3333333 |

  Scenario: Every mapped state becomes one candidate keyed by its state id
    When I build anchor candidates from the graph
    Then the candidate ids are "s0000000", "s1111111", "s2222222" and "s3333333"

  Scenario: A candidate carries its state's captured page title
    When I build anchor candidates from the graph
    Then the candidate "s1111111" has title "Search results"

  Scenario: A secret in a captured title is redacted in the candidate title
    When I build anchor candidates from the graph
    Then the candidate "s2222222" title has no secret in it

  Scenario: A state with no captured signals has no title
    When I build anchor candidates from the graph
    Then the candidate "s3333333" has no title

  Scenario: The root state's path is empty
    When I build anchor candidates from the graph
    Then the candidate "s0000000" has an empty path

  Scenario: A candidate's path is the shortest action sequence from the root
    When I build anchor candidates from the graph
    Then the candidate "s2222222" has the path "link=Search>button=Go"

  Scenario: A title selector resolves against the candidates built from the graph
    When I build anchor candidates from the graph
    And I resolve the selector "title:Search results" against them
    Then it resolves to the state "s1111111"

  Scenario: A path selector resolves against the candidates built from the graph
    When I build anchor candidates from the graph
    And I resolve the path selector "link=Account" against them
    Then it resolves to the state "s3333333"

  Scenario: A url selector finds nothing because a graph state records no route
    When I build anchor candidates from the graph
    And I resolve the selector "url:/#/search" against them
    Then it reports no matching state
