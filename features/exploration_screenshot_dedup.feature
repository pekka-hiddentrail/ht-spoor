Feature: Screenshots are deduplicated and clips reuse the bigger picture (§2e, 8g)
  Slice 8f streamed every capture straight to disk so a long run never held its images
  in memory. A comprehensive run then showed the next waste: the same picture written
  many times over. One live crawl produced 2,409 element clips against just 40 full-page
  screenshots — nearly every clip is a region of the page it was taken from — and states
  that look identical each wrote their own copy. Slice 8g removes that redundancy so the
  wiki refers to one shared picture instead of storing duplicates.

  Two mechanisms, both deterministic (§0 — pure image maths, nothing site-specific):

  - Duplicate detection. A capture identical to one already written reuses that file
    instead of writing a second (byte-exact match). Near-identical captures — the same
    screen re-rendered with only anti-aliasing or cursor noise between them — are matched
    by a perceptual hash within a tight distance and share one file too. This never
    merges two distinct states: only the image a state's page embeds is shared, the state
    pages stay separate. A flat, featureless image is matched only byte-exactly, never
    perceptually, so blank screens are not collapsed together.
  - Sub-image containment. A small clip that is part of a bigger picture is stored as a
    reference to that bigger picture plus the rectangle it occupies, not as its own file.
    The element's on-page geometry is used first (the driver already knows each element's
    box); when that is unavailable the clip is located inside the full-page image by pixel
    search. Only when a clip is in no bigger picture is it written as its own file.

  The opt-in, off-by-default posture is unchanged (§2h): dedup and containment only ever
  touch pixels a caller already opted into capturing, a crop reference carries nothing
  but a filename and integer coordinates, and a default run still writes no images at all.

  Background:
    Given a sandbox app whose screens and elements render real pictures

  Scenario: Two states that look identical share one screenshot file
    Given screens "home" and "home-again" render the same picture
    When I explore it with screenshots on
    Then only one screenshot file is written for those two screens
    And both state pages embed the same screenshot reference

  Scenario: Two near-identical screens are matched perceptually and share one file
    # The same screen re-rendered with only sub-threshold pixel noise between visits.
    Given screens "home" and "home-again" render near-identical pictures
    When I explore it with screenshots on
    Then only one screenshot file is written for those two screens

  Scenario: Two clearly different screens are not merged
    Given screens "home" and "menu" render clearly different pictures
    When I explore it with screenshots on
    Then a separate screenshot file is written for each of the two screens

  Scenario: An element clip that is part of its page reuses the full-page picture
    # Geometry path: the clip is a region of the state's own full-page shot, so it is
    # stored as a crop reference into that picture — no separate clip file is written.
    Given the screen has an element that is part of the full-page picture
    And the driver reports element geometry
    When I explore it with screenshots on
    Then no separate clip file is written for that element
    And the element's row embeds a crop of the full-page picture

  Scenario: A clip is located inside the page by pixel search when geometry is missing
    Given the screen has an element that is part of the full-page picture
    And the driver cannot report element geometry
    When I explore it with screenshots on
    Then no separate clip file is written for that element
    And the element's row embeds a crop of the full-page picture

  Scenario: A clip that is in no bigger picture is written as its own file
    Given the screen has an element whose picture is not part of any page
    When I explore it with screenshots on
    Then a clip file is written for that element

  Scenario: The same run twice produces the identical set of files
    # Determinism (§0): dedup and containment decisions depend only on the pixels, so a
    # re-run writes the very same files with the very same references.
    Given screens "home" and "menu" render clearly different pictures
    When I explore it with screenshots on twice
    Then both runs write the identical set of screenshot files
