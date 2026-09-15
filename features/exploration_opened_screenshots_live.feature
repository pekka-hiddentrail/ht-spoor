@browser
Feature: Live opened-contents capture in a real browser (ROADMAP.md §2e, slice 8e)
  The in-process scenarios prove the explorer and wiki wire opened captures through
  correctly with fake bytes. This proves the piece they can't: that the real
  PlaywrightDriver actually opens a disclosure element in a headless Chromium, captures
  what it reveals, and restores. Against a loopback fixture whose ARIA "Currency"
  combobox reveals an in-DOM option list on click, opening it must produce a real PNG
  that differs from the closed page — showing the click genuinely disclosed the content
  the screenshot then captured — and the page must be restored to closed afterwards.

  Scenario: The driver opens a disclosure element and captures what it reveals
    Given a live browser on the opened-contents fixture "explore_opened.html"
    When I capture the opened contents of the "combobox" named "Currency"
    Then a PNG image of the opened contents is returned
    And it differs from the closed page, so the click revealed content
    And the page is restored to its closed state afterwards
