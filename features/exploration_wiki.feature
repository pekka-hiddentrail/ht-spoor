Feature: Exploration wiki generation — the browsable map (ROADMAP.md §2e, slice 6a)
  The explored state-action graph is §2e's real product only once it is browsable.
  This slice is the pure renderer: an ExplorationGraph becomes a set of static HTML
  pages — an index with a graph overview and run counts, one page per state showing
  the free-signal bundle captured there, and one page per transition showing what its
  action changed. Because the wiki is a shared-output surface, every captured value it
  renders (console messages, storage keys, network URLs, action labels) is redacted
  before rendering (§2h). Screenshots are reported as a hash / changed-or-not for now,
  not embedded as images.

  Background:
    Given an explored graph of a small app:
      | state | ax_nodes | console     | storage        | network            |
      | home  | 3        | home ready  | session        | /home.js           |
      | menu  | 6        | menu opened | session; token | /home.js; /menu.js |
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
