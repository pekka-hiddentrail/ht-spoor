# Exploration anchor selection: resolving a state-selector to one state — §2e.
#
# The first slice of the anchored, depth-relative *resume* capability (§2e "v2",
# see the resume design note). A resume run must begin from a state the first run
# already reached, and — since Spoor is config/CLI-driven, not a GUI picker — the
# user names that anchor by a selector rather than a raw SHA-256 state id. This is
# the pure resolution core, no browser and no disk: given a set of candidate states
# and one or more constraints, pick the single state that satisfies all of them.
#
# Four constraint kinds, combinable (AND): `id:` (a git-style state-id prefix),
# `title:` (the wiki's human-readable state title, exact), `url:` (the route the
# state lives at, exact), and a path constraint (the action sequence — role+name
# steps — that reaches the state). Resolution is DETERMINISTIC and never guesses:
# exactly one match anchors there; zero matches is reported unmatched; several
# matches is reported ambiguous *with the candidates listed* so the user can narrow
# it — the same "never fabricate" stance the serving layer takes for an unmapped
# URL. The resolver matches over an in-memory candidate set here; wiring each kind
# to the persisted map is gated on that field being available there (`id:`/path
# today, `title:` after the projection carries the redacted title, `url:` after the
# per-state-URL decision — see the resume design note). Nothing here is
# site-specific (§0): one selector grammar resolves for every target.

Feature: A state-selector resolves to exactly one anchor state, or says why not
  As a user starting a resume run from a state an earlier run mapped
  I want to name that state by a selector instead of its raw hash
  So that I can anchor deterministically, and be told plainly when a selector
  matches nothing or several states rather than being handed a wrong one

  Background:
    Given a mapped graph with states:
      | id       | title       | url        | path                        |
      | aaa11100 | Login       | /#/login   |                             |
      | bbb22200 | Search      | /#/search  | link=Search                 |
      | bbb22999 | Results     | /#/search  | link=Search>button=Go       |
      | ccc33300 | Account     | /#/account | link=Account                |
      | ddd44400 | Account     | /#/orders  | link=Account>link=Orders    |

  Scenario: An id-prefix selector resolves to the one state it uniquely prefixes
    When I resolve the selector "id:aaa"
    Then it resolves to the state "aaa11100"

  Scenario: A title selector resolves to the state carrying that title
    When I resolve the selector "title:Login"
    Then it resolves to the state "aaa11100"

  Scenario: A url selector resolves to the state at that route
    When I resolve the selector "url:/#/account"
    Then it resolves to the state "ccc33300"

  Scenario: A path selector resolves to the state reached by that action sequence
    When I resolve the path selector "link=Account>link=Orders"
    Then it resolves to the state "ddd44400"

  Scenario: A selector matching no state is reported unmatched, never guessed
    When I resolve the selector "title:Checkout"
    Then it reports no matching state

  Scenario: An id prefix shared by several states is reported ambiguous
    When I resolve the selector "id:bbb"
    Then it reports the selector is ambiguous
    And the ambiguous candidates are "bbb22200" and "bbb22999"

  Scenario: A title shared by several states is reported ambiguous
    When I resolve the selector "title:Account"
    Then it reports the selector is ambiguous
    And the ambiguous candidates are "ccc33300" and "ddd44400"

  Scenario: Combined constraints narrow an otherwise-ambiguous selector to one state
    When I resolve the combined selector "title:Account" and "url:/#/orders"
    Then it resolves to the state "ddd44400"

  Scenario: A selector without a kind prefix is rejected
    When I resolve the selector "aaa11100"
    Then the selector is rejected as malformed

  Scenario: A selector with an unknown kind is rejected
    When I resolve the selector "role:button"
    Then the selector is rejected as malformed
