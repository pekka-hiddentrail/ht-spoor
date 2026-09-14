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
