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
  64-char hash, so the index and the overview graph read as noise; and the console and
  network signals are whole-run running buffers, so a state reached late in the run
  dumped the entire session's output — a real page carried 105 identical console lines
  and thousands of repeated request URLs. So a state now carries its page title as a
  human-readable label (falling back to the short id when the page has no title), and a
  state page collapses repeated console/network lines into one row with an "× count".
  Transition pages already show a first-seen-deduplicated diff, so they are unchanged.

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
    # The console buffer accumulates for the whole run, so a chatty library logs the same
    # line many times. The state page shows that line once with an "× count", not 40 rows.
    Given a state "noisy" whose console logged "JQMIGRATE: Migrate is installed" 40 times
    When I render the wiki for "https://shop.example"
    Then the state page for "noisy" shows the console message "JQMIGRATE: Migrate is installed"
    And the state page for "noisy" shows that console message only once
    And the state page for "noisy" marks that console message "× 40"

  Scenario: Repeated network requests on a state page are collapsed with a count
    # The network buffer likewise accumulates, so a polled endpoint appears many times.
    # The state page collapses identical request URLs to one row carrying the hit count.
    Given a state "poller" that requested "/api/ping" 12 times
    When I render the wiki for "https://shop.example"
    Then the state page for "poller" shows the network request "/api/ping"
    And the state page for "poller" shows that network request only once
    And the state page for "poller" marks that network request "× 12"
