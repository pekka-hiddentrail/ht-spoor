# Exploration traversal strategy: breadth-first, depth-bounded, URL-forked — §2e slice 9.
#
# The explorer's walk (slice 5a) was depth-first, so a bounded run dived into the first
# deep branch and spent its budget before reaching sibling pages one click from the
# start — a shop's other top categories, its cart. Slice 9 makes the walk breadth-first
# (peel the site layer by layer), adds a --max-depth reach bound (map only the first N
# layers), and — when the driver reports page URLs — forks the crawl frontier on the URL
# path so a distinct page that renders an already-seen DOM is still explored.
#
# These scenarios run in-process against a fake site (the same BrowserDriver-protocol
# style as exploration_loop.feature) described as a page table: each row is one action
# in the `from` page leading to the `to` page, plus the URL the `to` page lives at.
# The graph's state identity stays the abstract DOM state id; page names are a test
# convenience the explorer never sees.

Feature: The explorer walks breadth-first, depth-bounded, and forks on URL path
  As the exploration engine mapping a target with no config
  I want to peel the site outward layer by layer within an optional depth bound
  So that a bounded run maps the shallow, high-value pages before the deep tendrils

  Scenario: Breadth-first reaches shallow siblings before a deep descendant
    # home has two first-layer pages (catA, catB) and catA has a deeper page (prod).
    # Under a 3-state budget, breadth-first maps home + both siblings; depth-first would
    # have dived home -> catA -> prod and missed catB.
    Given a sandbox target with a budget of max_states 3
    And a site whose pages are:
      | from | label      | role | to   | url    |
      | home | Category A | link | catA | /a     |
      | home | Category B | link | catB | /b     |
      | catA | Product    | link | prod | /a/p   |
    When I explore the site from "home"
    Then the graph has pages: home, catA, catB
    And the graph does not have page "prod"

  Scenario: A shallow-destination link is tried before a deep one under a budget
    # Both links are on home; discovery lists the deep one first. Ordering the walk by
    # the links' destination depth (§2e slice 9b) fires the shallow, top-level link
    # first, so a 2-state budget maps it and not the deep one — peeling the onion in
    # priority order, not discovery order.
    Given a sandbox target with a budget of max_states 2
    And a site whose pages are:
      | from | label   | role | to      | url    |
      | home | Deep    | link | deep    | /x/y/z |
      | home | Shallow | link | shallow | /a     |
    When I explore the site from "home"
    Then the graph has pages: home, shallow
    And the graph does not have page "deep"

  Scenario: A depth bound maps a layer but does not descend past it
    Given a sandbox target with a budget of max_depth 1
    And a site whose pages are:
      | from | label      | role | to   | url  |
      | home | Category A | link | catA | /a   |
      | catA | Product    | link | prod | /a/p |
    When I explore the site from "home"
    Then the graph has pages: home, catA
    And the graph has a transition "home --Category A--> catA"
    And the graph does not have page "prod"

  Scenario: A larger depth bound reaches the deeper layer
    Given a sandbox target with a budget of max_depth 2
    And a site whose pages are:
      | from | label      | role | to   | url  |
      | home | Category A | link | catA | /a   |
      | catA | Product    | link | prod | /a/p |
    When I explore the site from "home"
    Then the graph has pages: home, catA, prod

  Scenario: A distinct URL rendering an identical screen is still explored
    # pageP and pageQ render the same DOM (one state id, one node) but live at different
    # URLs and lead onward to different pages. Forking the frontier on the URL path means
    # both are expanded, so both destinations are reached.
    Given a sandbox target
    And a site whose pages are:
      | from  | label    | role | to    | url |
      | home  | Go P     | link | pageP | /p  |
      | home  | Go Q     | link | pageQ | /q  |
      | pageP | Continue | link | destX | /x  |
      | pageQ | Continue | link | destY | /y  |
    And pages "pageP" and "pageQ" render an identical screen
    When I explore the site from "home"
    Then the graph has pages: home, pageP, destX, destY

  Scenario: Without URL reporting, an identical screen collapses and is explored once
    # The same site, but a driver that reports no URLs: the frontier keys on the DOM
    # state id alone, so pageQ collapses onto pageP and only the first destination is
    # reached. This is the pre-slice-9 behaviour every URL-less driver keeps.
    Given a sandbox target
    And a site whose pages are:
      | from  | label    | role | to    | url |
      | home  | Go P     | link | pageP | /p  |
      | home  | Go Q     | link | pageQ | /q  |
      | pageP | Continue | link | destX | /x  |
      | pageQ | Continue | link | destY | /y  |
    And pages "pageP" and "pageQ" render an identical screen
    And the driver does not report page URLs
    When I explore the site from "home"
    Then the graph has pages: home, pageP, destX
    And the graph does not have page "destY"
