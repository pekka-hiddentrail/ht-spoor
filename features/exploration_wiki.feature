Feature: Exploration wiki generation — the browsable map (ROADMAP.md §2e, slice 6a)
  The explored state-action graph is §2e's real product only once it is browsable.
  This slice is the pure renderer: an ExplorationGraph becomes a set of static HTML
  pages — an index with a graph overview and run counts, one page per state showing
  the free-signal bundle captured there, and one page per transition showing what its
  action changed. Because the wiki is a shared-output surface, every captured value it
  renders (console messages, storage keys, network URLs, action labels) is redacted
  before rendering (§2h). Screenshots are reported as a hash / changed-or-not for now,
  not embedded as images.

  Slice 6c sharpens the state pages after a live PrestaShop run showed them barely
  readable. Two defects, both generic (§0): states were labelled only by their opaque
  64-char hash, so the index and the overview graph read as noise; and repeated console
  and network lines were shown in full, so a chatty library or a polled endpoint dumped
  the same line many times over. So a state now carries its page title as a human-
  readable label (falling back to the short id when the page has no title), and a state
  page collapses repeated console/network lines into one row with an "× count".
  Transition pages already show a first-seen-deduplicated diff, so they are unchanged.

  Slice 6d then groups a state's network requests by kind — a small fixed taxonomy
  (Documents, Scripts, Styles, Images, Fonts, Media, Data, Other) derived from each URL
  alone — so a reader sees what the page loaded at a glance, with a per-group count,
  rather than one flat list. (The buffers behind these signals are scoped per visit by
  the driver, so a state reflects only the walk that reached it; that behaviour is
  covered by the live signal-capture feature, not this pure-renderer one.)

  Slice 8a is the first step of embedding screenshots in the wiki (the "Visual capture"
  backlog item). The pure renderer learns to embed a per-state full-page screenshot as
  an <img>, referenced by a relative filename, when it is told that a state has one
  captured. Capturing the image bytes and the opt-in flag that turns embedding on are a
  later slice; here, by default no state has a screenshot and the pages stay pixel-free.
  Because a screenshot is pixels, not text, it cannot be secret-redacted the way every
  other signal is (§2h) — a token or PII visible on the page survives as an image — so a
  screenshot is only ever embedded behind an explicit opt-in, never on a default run.

  Slice 6f adds a help/glossary page linked from every page's nav — a fixed,
  target-independent glossary that explains, in plain language, every term the other
  pages use (state, transition, accessibility nodes, storage keys added, network
  requests, the redaction placeholder, and so on) for a reader who did not build Spoor.

  Slice 6e rearranges the state page to lead with its actionable elements. The old
  "Actions here" bullet list and the separate "Outgoing transitions" list are replaced
  by one "Actions" table (Label, Type, Screen capture, Destination / target state)
  placed immediately after the state-identity block, before the captured signals, so the
  thing a reader acts on comes first. The destination cell folds in what the outgoing
  list carried — a link to the transition page, labelled by the target state — when the
  element was fired, and reads "none" otherwise. The screen-capture column reads "none"
  for every element for now: Spoor captures no per-element screenshot yet, so the column
  is honest about there being nothing to show rather than implying one exists.

  Slice 6g groups the page set into subfolders so the wiki directory stays readable as
  the map grows. State pages move under a "states/" subfolder and transition pages under
  a "transitions/" subfolder; the index and help pages stay at the root as the entry
  points, and screenshots keep the "screenshots/" subfolder they already have. Grouping
  the pages turns the links between them into relative paths that climb out of a
  subfolder and back into another, so every navigation — index to a state, a state's
  screenshot and destination, a transition back to its states, and the shared nav to the
  index and help — must still resolve. Purely a layout change: the pages' content and
  their redaction (§2h) are untouched, and it stays generic across every target (§0).

  Background:
    Given an explored graph of a small app:
      | state | title     | ax_nodes | console     | storage        | network            |
      | home  | Home page | 3        | home ready  | session        | /home.js           |
      | menu  | Menu open | 6        | menu opened | session; token | /home.js; /menu.js |
    And a transition "Open menu" from "home" to "menu"

  Scenario: The wiki has an index, a page per state, and a page per transition
    When I render the wiki for "https://shop.example"
    Then the wiki has an index page
    And the wiki has a page for each state
    And the wiki has a page for each transition
    And the index reports 2 states and 1 transition
    And the index links to every state page
    And the index includes a graph overview

  Scenario: A state page shows the signal bundle captured there
    When I render the wiki for "https://shop.example"
    Then the state page for "menu" reports 6 accessibility nodes
    And the state page for "menu" shows the console message "menu opened"
    And the state page for "menu" shows the storage key "session"

  Scenario: A transition page shows what its action changed
    When I render the wiki for "https://shop.example"
    Then the transition page reports an accessibility node delta of 3
    And the transition page shows the added console message "menu opened"
    And the transition page shows the added storage key "token"
    And the transition page shows the added network request "/menu.js"

  Scenario: Secrets in captured signals are redacted before rendering
    Given a state "vault" whose console logged "Authorization: Bearer sk-supersecrettoken12345"
    When I render the wiki for "https://shop.example"
    Then no wiki page contains the raw secret "sk-supersecrettoken12345"
    And some wiki page shows the redaction placeholder

  Scenario: A state is labelled by its page title, not only its opaque id
    # The hash is still shown as the state's full id, but the human-readable label a
    # reader scans by — on the state page, in the index list, and in the graph — is the
    # page title, so the map is legible instead of a wall of hashes.
    When I render the wiki for "https://shop.example"
    Then the state page for "menu" is titled "Menu open"
    And the index lists the state labelled "Menu open"
    And the overview graph labels a state "Menu open"

  Scenario: A state with no page title falls back to its id
    # A page that reports no title (an SPA before it sets one, an error page) must still
    # be identifiable, so the label falls back to the short id rather than going blank.
    Given a state "blank" with no page title
    When I render the wiki for "https://shop.example"
    Then the state page for "blank" is labelled by its short id

  Scenario: Repeated console lines on a state page are collapsed with a count
    # The console buffer accumulates across a visit's reloads, so a chatty library logs
    # the same line many times. The state page shows it once with an "× count", not 40 rows.
    Given a state "noisy" whose console logged "JQMIGRATE: Migrate is installed" 40 times
    When I render the wiki for "https://shop.example"
    Then the state page for "noisy" shows the console message "JQMIGRATE: Migrate is installed"
    And the state page for "noisy" shows that console message only once
    And the state page for "noisy" marks that console message "× 40"

  Scenario: Repeated network requests on a state page are collapsed with a count
    # The network buffer likewise accumulates within a visit, so a polled endpoint appears
    # many times. The state page collapses identical URLs to one row carrying the hit count.
    Given a state "poller" that requested "/api/ping" 12 times
    When I render the wiki for "https://shop.example"
    Then the state page for "poller" shows the network request "/api/ping"
    And the state page for "poller" shows that network request only once
    And the state page for "poller" marks that network request "× 12"

  Scenario: The wiki has a help page that defines its terms
    # A reader who did not build Spoor can look up any term the pages use. The glossary
    # is linked from every page's nav so it is always one click away.
    When I render the wiki for "https://shop.example"
    Then the wiki has a help page
    And the help page defines "Accessibility nodes"
    And the help page defines "Storage keys added"
    And the help page defines "Network requests"
    And the help page defines "Screenshot hash"
    And every wiki page links to the help page

  Scenario: A state page leads with an Actions table of its elements, before the signals
    # The elements a tester acts on come first: an Actions table sits immediately after
    # the state-identity block and ahead of the captured-signal sections.
    When I render the wiki for "https://shop.example"
    Then the state page for "home" has an Actions table
    And the Actions table on the "home" state page comes before the captured signals
    And the state page for "home" lists the element "Open menu" of type "button"

  Scenario: A fired element's destination links to the target state
    # "Open menu" was fired and produced a transition, so its Destination cell links on
    # to that transition, labelled by the state it reached.
    When I render the wiki for "https://shop.example"
    Then the element "Open menu" on the "home" state page has destination "Menu open"

  Scenario: An element that was never fired shows no destination
    # A discovered-but-unfired element still gets a row; its Destination cell reads none.
    Given a discovered element "Search" on "home"
    When I render the wiki for "https://shop.example"
    Then the state page for "home" lists the element "Search" of type "button"
    And the element "Search" on the "home" state page has no destination

  Scenario: A state page embeds its full-page screenshot when one was captured
    # When the renderer is told a state has a captured screenshot, the state page embeds
    # it as an image referenced by a relative filename, leading the page as the screen's
    # visual identity — ahead of the Actions table.
    Given a captured screenshot for state "home"
    When I render the wiki for "https://shop.example"
    Then the state page for "home" embeds its screenshot image
    And the screenshot on the "home" state page comes before the Actions table

  Scenario: A state with no captured screenshot embeds no image
    Given a captured screenshot for state "home"
    When I render the wiki for "https://shop.example"
    Then the state page for "menu" embeds no screenshot image

  Scenario: By default a wiki embeds no screenshots
    # A default run is told of no screenshots, so every page stays pixel-free — pixels
    # reach the shared wiki only behind an explicit opt-in (§2h).
    When I render the wiki for "https://shop.example"
    Then no wiki page embeds a screenshot image

  Scenario: Network requests on a state page are grouped by kind
    # A flat list of every request is noise. Slice 6d collates them under a small fixed
    # taxonomy derived from each URL — scripts, styles, images, fonts, media, data, and
    # documents — so a reader sees at a glance what the page loaded, with the count per
    # group. The kind is a URL heuristic (extension, or an "/api/" path for data), so it
    # stays generic across every target rather than needing a captured content-type.
    Given a state "shop" requested a mix of resources:
      | url                            |
      | https://cdn.example/app.js     |
      | https://cdn.example/main.css   |
      | https://cdn.example/logo.png   |
      | https://cdn.example/hero.png   |
      | https://shop.example/api/cart  |
      | https://shop.example/account   |
    When I render the wiki for "https://shop.example"
    Then the state page for "shop" groups the network request "app.js" under "Scripts"
    And the state page for "shop" groups the network request "main.css" under "Styles"
    And the state page for "shop" groups the network request "logo.png" under "Images"
    And the state page for "shop" groups the network request "api/cart" under "Data"
    And the state page for "shop" groups the network request "account" under "Documents"
    And the state page for "shop" shows the network category "Images" with 2 requests

  Scenario: State and transition pages are grouped into their own subfolders
    # The wiki root keeps only the entry points; each kind of page gets its own subfolder.
    When I render the wiki for "https://shop.example"
    Then every state page is under the "states/" subfolder
    And every transition page is under the "transitions/" subfolder
    And the index and help pages stay at the wiki root

  Scenario: Links between the subfolders resolve
    # Grouping pages into subfolders turns their links into relative paths that climb out
    # and back in; every navigation must still resolve — the index into a subfolder, a
    # transition back up to its states, a state's screenshot and destination, and the nav.
    Given a captured screenshot for state "home"
    When I render the wiki for "https://shop.example"
    Then the index links to the state page for "home" under "states/"
    And the transition page links up to the state page for "home"
    And the transition page links up to the state page for "menu"
    And the state page for "home" references its screenshot one level up
    And the destination link on the "home" state page points into "transitions/"
    And the state page for "home" links up to the index page
    And the state page for "home" links up to the help page
