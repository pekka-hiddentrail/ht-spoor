Feature: Opt-in full-page screenshots in the wiki (ROADMAP.md §2e, slice 8b)
  Slice 8a taught the wiki renderer to embed a per-state screenshot when told a state
  has one. Slice 8b is the capture-and-write half: the explorer, when handed a
  screenshot sink, stores a full-page image of each screen it discovers, and the wiki
  writer places those images under a "screenshots/" subfolder and embeds them.

  The whole feature is opt-in and off by default, for one §2h reason: a screenshot is
  pixels, and text redaction cannot scrub a secret that is *visible on the page* — a
  token shown in the DOM, personal data — the way it scrubs a captured string. So a
  default run captures no screenshot at all and a default wiki stays pixel-free; images
  are captured and embedded only when a caller explicitly asks by providing the sink.
  Nothing here is site-specific (§0): the same capture and the same writer run for every
  target.

  Background:
    Given a sandbox app with screens "home" and "menu" linked by "Open menu"

  Scenario: Exploring with screenshots on captures one image per state
    When I explore it with screenshot capture on
    Then a screenshot was captured for "home"
    And a screenshot was captured for "menu"

  Scenario: Each screenshot is streamed to disk as it is captured, kept only by reference
    # The memory contract (slice 8f): a screenshot is written to disk the moment it is
    # taken and only its file reference is held in memory, so a long, deep run's images
    # never pile up in RAM. The image bytes live on disk; the sink holds paths, not pixels.
    When I explore it with screenshot capture on
    Then the screenshot sink holds a file reference for each screen, not image bytes
    And each referenced screenshot file already exists on disk

  Scenario: Exploring with screenshots off captures none
    When I explore it with screenshot capture off
    Then no screenshots were captured

  Scenario: A wiki rendered with the captured screenshots writes and embeds each one
    Given I explored it with screenshot capture on
    When I render the wiki to disk
    Then the wiki directory contains a screenshot image for "home"
    And the wiki directory contains a screenshot image for "menu"
    And the state page for "home" embeds its screenshot image
    And the state page for "menu" embeds its screenshot image

  Scenario: A wiki rendered without captured screenshots stays pixel-free
    Given I explored it with screenshot capture off
    When I render the wiki to disk
    Then the wiki directory contains no screenshot images
    And no wiki page embeds a screenshot image

  Scenario: Screenshot images are grouped in their own subfolder, not flat beside the pages
    # The images live under a "screenshots/" subfolder rather than sitting flat next to
    # the HTML pages, so the wiki directory stays readable; pages embed them by that
    # relative path.
    Given I explored it with screenshot capture on
    When I render the wiki to disk
    Then the screenshot image for "home" is under the "screenshots" subfolder
    And no screenshot image sits flat in the wiki root
