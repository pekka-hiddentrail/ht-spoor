Feature: Opt-in per-element screenshots in the wiki (ROADMAP.md §2e, slice 8d)
  Slice 8b captured one full-page image per state. Slice 8d captures a *per-element*
  image: a clip of each actionable element a screen exposes — the "Next" button, the
  "Currency" dropdown — so the wiki's Actions table can show what each control looks
  like, not only its label. Each clip fills the Actions table's long-reserved "Screen
  capture" column, one image per element row.

  Like every screenshot it is opt-in and off by default, for the same §2h reason a
  full-page shot is: pixels cannot be secret-redacted the way a captured text value is,
  so a default run captures no element image and a default wiki stays pixel-free. Images
  are captured and embedded only when a caller explicitly provides the element sink.
  Nothing here is site-specific (§0): the same clip is taken for every target's elements.

  Background:
    Given a sandbox screen with a "Currency" dropdown and a "Next" button

  Scenario: Exploring with element capture on clips one image per actionable element
    When I explore it with element-screenshot capture on
    Then an element screenshot was captured for "Currency"
    And an element screenshot was captured for "Next"

  Scenario: Each element clip is streamed to disk as it is captured, kept only by reference
    # The memory contract (slice 8f): each clip is written to disk the moment it is taken
    # and the shot holds only its file reference, so a run over many elements never piles
    # image bytes up in RAM.
    When I explore it with element-screenshot capture on
    Then each captured element clip is a file reference on disk, not image bytes

  Scenario: Exploring with element capture off clips none
    When I explore it with element-screenshot capture off
    Then no element screenshots were captured

  Scenario: A wiki rendered with element clips writes and embeds each one in its row
    Given I explored it with element-screenshot capture on
    When I render the wiki to disk
    Then the Actions row for "Currency" embeds its element screenshot
    And the Actions row for "Next" embeds its element screenshot
    And every element image sits under the "screenshots" subfolder

  Scenario: A wiki rendered without element clips stays pixel-free
    Given I explored it with element-screenshot capture off
    When I render the wiki to disk
    Then no wiki page embeds an element screenshot
