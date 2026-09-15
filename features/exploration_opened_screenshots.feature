Feature: Opt-in opened-contents screenshots in the wiki (ROADMAP.md §2e, slice 8e)
  Slice 8d clipped each actionable element as it sits closed on the screen. Slice 8e
  adds the other half of what the user asked for: a picture of what a *disclosure*
  element — a dropdown or list (an ARIA combobox or listbox) — reveals when it is
  opened, so the wiki shows not only the closed "Currency" control but the list of
  currencies it exposes. Each
  opened capture fills a new "Opened contents" column in the Actions table, beside the
  closed clip, one image per element row.

  Opening an element clicks it, which mutates the page, so this capture is fenced by two
  rules that keep the explorer honest. It fires only for a disclosure role the safety
  gate also permits, so opening never actuates a destructive element on a non-sandbox
  target (§2e non-negotiable). And it runs only after the state's id, signals and every
  closed clip are already recorded, so the mutation never contaminates the mapped graph.

  Like every screenshot it is opt-in and off by default, for the same §2h reason: pixels
  cannot be secret-redacted the way a captured text value is, so a default run captures
  no opened image and a default wiki stays pixel-free. A driver that can clip elements
  but cannot open them simply produces no opened images. Nothing here is site-specific
  (§0): the same disclosure roles are opened for every target.

  Background:
    Given a sandbox screen with a "Currency" dropdown and a "Delete" button

  Scenario: Opening capture pictures the contents a disclosure element reveals
    When I explore it with opened-contents capture on
    Then an opened-contents screenshot was captured for "Currency"

  Scenario: A non-disclosure element is never opened
    When I explore it with opened-contents capture on
    Then no opened-contents screenshot was captured for "Delete"

  Scenario: A destructive disclosure element is never opened outside a sandbox
    Given a "Delete account" dropdown on the screen
    And the target is a real site, not a sandbox
    When I explore it with opened-contents capture on
    Then no opened-contents screenshot was captured for "Delete account"

  Scenario: Opening capture off captures nothing
    When I explore it with opened-contents capture off
    Then no opened-contents screenshots were captured

  Scenario: A clip-only driver produces no opened images
    Given the driver can clip elements but cannot open them
    When I explore it with opened-contents capture on
    Then no opened-contents screenshots were captured

  Scenario: A wiki rendered with opened captures writes and embeds each in its row
    Given I explored it with opened-contents capture on
    When I render the wiki to disk
    Then the Actions row for "Currency" embeds its opened-contents screenshot
    And every element image sits under the "screenshots" subfolder

  Scenario: A wiki rendered without opened captures stays free of opened images
    Given I explored it with opened-contents capture off
    When I render the wiki to disk
    Then no wiki page embeds an opened-contents screenshot
