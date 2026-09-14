# Exploration actuation verdict: is this element reachable, covered, or gone? — ROADMAP.md §2e.
#
# Slice 7a's pure-logic core. A live diagnostic showed the explorer's skips on a real
# SPA were not overlay interception but a *relocation* failure: discovery reads an
# element from the CDP accessibility tree, while the old `perform` re-found it through
# a different name engine, so a visible, uncovered element could not be clicked. 7a
# fixes actuation to stay in one engine end to end and to click by verified
# coordinates, and it must tell three outcomes apart honestly:
#
#   * ACTUATE     — the element is located and the point we would click resolves to it
#                   (or a descendant), so a real click will land on it.
#   * COVERED     — the element is located, but the point resolves to a *different*
#                   element on top of it; clicking the coordinate would hit the wrong
#                   thing. This is the precise, generic signal that a layer is in the
#                   way — the hand-off to layer recovery (7c) — never a mute skip.
#   * NOT LOCATED — no element matching the discovered role and name is present; the
#                   element is genuinely gone, not covered, so recovery cannot help.
#
# This is the pure decision, taken from what sits at the element's click point; the
# real CDP relocation, coordinate click, and elementFromPoint verification that feed
# it live are 7a's second half (exploration_actuation_live.feature). Nothing here is
# site-specific (§0): the verdict is the same for every target's every element.

Feature: The explorer classifies whether a discovered element can be actuated
  As the exploration engine acting on a real, dynamic page
  I want to know whether a click will land on the element, hit a layer, or find nothing
  So that a reachable element is clicked, a covered one is handed to recovery, and a
  gone one is flagged — each honestly, never a click fired blind at a coordinate

  Scenario Outline: The verdict follows from what sits at the element's click point
    Given a target element "<role>" named "<name>"
    When the element at its click point is "<observed>"
    Then the actuation verdict is "<verdict>"

    Examples:
      | role   | name    | observed                    | verdict     |
      | button | Save    | the target itself           | actuate     |
      | button | Save    | a descendant of the target  | actuate     |
      | button | Save    | a different element on top  | covered     |
      | button | Missing | nothing — no matching node  | not located |

  Scenario: A covered verdict names the layer's role and text, for recovery to use
    # The covered signal is not just "blocked": it carries what is on top (its role and
    # visible text) so layer recovery (7c) can decide how to deal with it, and so the
    # flag a user reads says what got in the way rather than a bare "could not click".
    Given a target element "button" named "Checkout"
    When the element at its click point is a "link" reading "Accept and continue"
    Then the actuation verdict is "covered"
    And the covering element is reported as a "link" reading "Accept and continue"
