# Exploration state abstraction: recognizing equivalent states — ROADMAP.md §2e.
#
# The second slice of exploration mode (§2e), still pure logic (no browser). Ported
# from Crawljax's core idea: normalize a page's DOM — strip the volatile parts
# (timestamps, session tokens, counters, whitespace/attribute-order noise) — and
# hash it into a stable state identifier. Two visits to the *same* screen collapse
# to one state instead of exploding into infinite near-duplicates, while genuinely
# different screens stay distinct. This is what lets the (later) explorer loop build
# a finite `state --action--> state` graph.
#
# First cut, deliberately PR-tunable (§2e "state-abstraction tuning takes real
# iteration"): identity is the page's tag structure plus a small allowlist of
# stable, state-bearing attributes (role/type and disabled/checked/expanded…), plus
# its visible text with volatile spans masked. Attribute values outside that
# allowlist and all volatile text are ignored, so session tokens and clocks never
# fork a state.

Feature: Exploration collapses equivalent states and separates distinct ones
  As the explorer that must build a finite state graph
  I want equivalent renderings of a screen to share one state identifier
  So that revisiting a screen is recognized instead of exploding into duplicates

  Scenario Outline: Renderings that differ only in volatile detail share a state id
    Given the page "<a>"
    And the page "<b>"
    Then the two pages have the same state id

    Examples:
      | a           | b                      |
      | orders_base | orders_identical       |
      | orders_base | orders_diff_timestamp  |
      | orders_base | orders_diff_session    |
      | orders_base | orders_diff_counter    |
      | orders_base | orders_diff_whitespace |
      | orders_base | orders_diff_attr_order |
      | orders_base | orders_diff_script     |

  Scenario Outline: Genuinely different states get different ids
    Given the page "<a>"
    And the page "<b>"
    Then the two pages have different state ids

    Examples:
      | a               | b                |
      | orders_base     | maintenance_base |
      | orders_base     | orders_extra_row |
      | button_enabled  | button_disabled  |

  Scenario: A state id is a deterministic hex digest
    Given the page "orders_base"
    Then its state id is a 64-character hex string
    And computing its state id again gives the same value
