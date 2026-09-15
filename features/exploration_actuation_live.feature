# Live robust actuation: the real driver clicks by verified coordinates — ROADMAP.md §2e.
#
# Slice 7a's second half. exploration_actuation.feature fixed the pure verdict; this
# fills it from a REAL page. It drives the real PlaywrightDriver against a static
# fixture served over a loopback socket and proves the actuation contract end to end:
#
#   * relocation stays in one engine — an element discovered from the accessibility
#     tree (including an icon button whose name is an aria-label, the exact shape the
#     diagnostic tripped on) is clicked reliably, where the old role+name relocation
#     could match nothing;
#   * the click is by verified coordinates — the element is scrolled into view, its
#     live box centre is read, and elementFromPoint confirms the point resolves to the
#     element before the mouse click fires, so a below-the-fold element still actuates;
#   * a covered element is DETECTED as covered — a button under a full-page overlay is
#     reported covered (not clicked), and crucially the overlay is NOT activated, so a
#     coordinate is never fired blind at whatever happens to be on top;
#   * the viewport is fixed — the driver pins a known viewport (and device-scale 1) so
#     layout, and therefore every computed coordinate, is reproducible run to run.
#
# Nothing here is site-specific (§0): the same relocation, coordinate click, and
# verification drive every target's every element. Juice Shop is only the witness that
# exposed the bug; the fixture reproduces the *class* of it, not that one site.

@browser
Feature: The live driver actuates elements reliably and detects covered ones
  As the exploration engine acting on a real, dynamic page in a headless browser
  I want clicks located by the accessibility tree and landed by verified coordinates
  So that a visible element is never skipped for a relocation quirk, and a covered one
  is recognised rather than mis-clicked

  Scenario: An icon button named only by its aria-label is actuated
    # The button carries an aria-label and icon-glyph text — the shape the diagnostic
    # showed the old relocation could not click. Discovery-then-actuation must round
    # trip through the accessibility name and land the click.
    Given a live browser on the actuation fixture "explore_actuation.html"
    When I actuate the "button" named "Open account menu"
    Then the fixture records that "Open account menu" was clicked

  Scenario: A below-the-fold element is scrolled into view and actuated
    Given a live browser on the actuation fixture "explore_actuation.html"
    When I actuate the "button" named "Far below the fold"
    Then the fixture records that "Far below the fold" was clicked

  Scenario: A covered element is detected as covered, not mis-clicked
    # A full-page overlay sits over the "Checkout" button. Clicking its coordinate would
    # hit the overlay; the driver must report the element covered and must NOT activate
    # the overlay — the coordinate is verified before any click, never fired blind.
    Given a live browser on the actuation fixture "explore_actuation.html"
    When I try to actuate the "button" named "Checkout"
    Then the driver reports the element as covered
    And the fixture records that the overlay was not activated

  Scenario: The driver runs at a fixed, known viewport for reproducibility
    Given a live browser on the actuation fixture "explore_actuation.html"
    Then the live page reports a fixed viewport
