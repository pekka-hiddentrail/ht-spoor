# Exploration in a real browser: the `spoor explore` command — ROADMAP.md §2e.
#
# Sub-slice 5b of the fifth §2e slice. Sub-slice 5a built the explorer orchestrator
# and proved its logic in-process against a fake driver; this drives the WHOLE stack
# for real: the `spoor explore` command points a headless Chromium at a live site,
# the real Playwright BrowserDriver discovers the actionable elements from the actual
# accessibility tree, fires them, and reset-and-replay navigation walks the site into
# a state-action graph. Because a browser can't use the in-process fixture transport,
# the scenario serves a small static site over a real loopback socket (as the tier-2
# and self-healing-visual browser scenarios do) and asserts on the run summary.
#
# Sub-slice 6b then rides on the same live run to prove the `--wiki` flag: the mapped
# graph is rendered to a browsable wiki on disk (the slice-6a renderer), and the
# scenario asserts the wiki is complete and its overview counts match the run.
#
# The last scenario proves the §2f producer wiring: the same live run also persists
# its state-action graph into the local map, so the read-only serving layer can
# answer "what happens when I click X" for the URL later without re-exploring.

@browser
Feature: Exploring a live site with the spoor explore command
  As an operator pointing Spoor at a target with no config
  I want one command that maps the site in a real browser
  So that pressing every button on the whole product becomes a graph I can read

  Scenario: Mapping a live two-page site
    # Home links to Next and Next links back to Home: two states, and a transition
    # in each direction, with the return to Home recognised as an already-known
    # state rather than explored again.
    Given a live fixture site starting at "explore_home.html"
    When I run spoor explore against it
    Then it reports 2 states discovered
    And it reports 2 transitions
    And it reports 0 actions skipped

  Scenario: Writing a browsable wiki of the mapped site (slice 6b)
    # The same live run, now asked to also render the map as a wiki: a page per
    # state and per transition plus an index, written to disk and ready to open.
    Given a live fixture site starting at "explore_home.html"
    When I run spoor explore against it writing a wiki
    Then it reports where the wiki was written
    And the wiki has an index page and a page for each state and transition
    And the wiki index reports 2 states and 2 transitions

  Scenario: The mapped graph is remembered so the serving layer can answer for it
    # The same live run feeds the read-only map the serving layer answers from:
    # after exploring, the target's state-action graph is stored and servable.
    Given a live fixture site starting at "explore_home.html"
    When I run spoor explore against it
    Then the target's exploration graph is stored for serving
    And the stored exploration graph reports 2 states and 2 transitions
