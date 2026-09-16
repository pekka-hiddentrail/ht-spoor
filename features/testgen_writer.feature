# Writing the generated regression suite to disk, and proving it runs — §2g, 2g-ii.
#
# Sub-slice 2g-i shipped the pure generator: an ExplorationGraph becomes a set of
# pytest test *sources* (filename -> code), with no browser and no disk. This slice is
# the thin on-disk counterpart plus the proof the decision note named as the follow-on:
#   (1) `render_suite` writes those sources under a directory (the last-mile a consuming
#       team actually runs), the same shape as the wiki writer — pure render, then write.
#   (2) `spoor explore --gen-tests <dir>` wires the writer to the command, so a crawl can
#       emit its regression suite in one step, beside the existing --wiki output.
#   (3) A tagged, live proof: crawl a real fixture in a browser, write its suite, run
#       pytest on that suite against the same live fixture, and see it pass green — the
#       end-to-end evidence that the emitted tests are not just valid Python (2g-i pins
#       that) but actually replay, fire, and assert correctly against a running target.
#
# The fast-tier scenarios drive the writer in-process against a graph built directly (no
# browser); the tagged scenario proves the whole generate -> write -> run loop end to end
# in real Chromium. Nothing here is site-specific (§0): one writer for every target.

Feature: Write a generated regression suite to disk and run it
  As a team that mapped a site with Spoor
  I want the generated pytest suite written to a directory and runnable
  So that re-running it against the live product in CI catches behavioural drift

  Background:
    Given an explored graph:
      | state | ax_nodes | console     | storage        | network            |
      | home  | 3        | home ready  | session        | /home.js           |
      | menu  | 6        | menu opened | session; token | /home.js; /menu.js |
    And a mapped transition "Open menu" from "home" to "menu"

  Scenario: The writer puts every generated file on disk
    When I write the suite for "https://shop.example" to a directory
    Then the directory contains a pytest conftest
    And the directory contains a shared test helper module
    And the directory contains one test file per mapped transition
    And each written file's contents match the generated source

  Scenario: The writer creates the output directory if it does not exist
    When I write the suite for "https://shop.example" to a directory that does not exist yet
    Then the directory now exists
    And the directory contains a pytest conftest

  Scenario: A graph with no transitions writes no files
    Given an empty explored graph
    When I write the suite for "https://shop.example" to a directory
    Then no files are written to the directory

  @browser
  Scenario: The generated suite runs green against the live fixture it was mapped from
    Given a live crawl of "gen_home.html" was mapped at depth 1
    When I write that crawl's suite to a directory
    And I run pytest on that suite against the live fixture
    Then the generated suite passes
