# Tier-3 self-healing for a broken row *container* (§2, §2d). Companion to
# self_healing_items.feature, which heals a field selector that breaks *inside*
# rows the `item` selector still matches. This one heals the `item` selector
# itself — the case where a redesign breaks the row container, so no rows match at
# all and the listing suffers total data loss.
#
# The hard part is not re-finding row-like elements; it is not *fabricating* a
# listing. A listing is by nature a **repeating group** of structurally-identical
# siblings, so healing here does not pick a single best element — it looks for a
# coherent sibling group (same parent, same tag) of at least two members that all
# score confidently against the container fingerprint a prior run recorded. Two
# guards keep it honest, reliability-first (§2, §1):
#
#   - The **>=2-member gate**: a lone stray element that resembles a row is never
#     promoted into a one-row listing — with no repeating group there is nothing a
#     listing's shape can be confirmed against, so the heal is refused.
#   - **Ambiguity refusal**: if two *distinct* coherent groups both match
#     confidently (a product list and a look-alike group both survive the
#     redesign), tier 3 cannot know which the config meant, so it refuses rather
#     than guess — better zero records than a confidently-wrong listing.
#
# Both refusals leave zero records and are surfaced in the run summary as an
# uncertain match (flagged for review), never a silent empty result. The container
# fingerprint is captured text-agnostic and healed only against a **prior-run**
# print (the same fabrication guard the item-field slice established). This is what
# the descendant-composition signal was landed for: a leaf-oriented fingerprint
# could not tell a product row from a nav item once the container's own class was
# renamed, but "what it contains" can.
#
# These scenarios drive real tier-1 runs against an in-memory transport, sharing
# one temp per-domain cache across runs; the dispatcher is pinned to tier 1 so a
# deliberate zero-record refusal is observed here, not escalated to the browser.

Feature: A listing heals its row-container selector when the container breaks
  As someone scraping a listing whose row-container markup churns
  I want the repeating row group re-resolved when the item selector breaks
  So that a container redesign degrades to a reviewable heal, not total data loss

  Background:
    Given a listing config with item "ul.products > li" extracting "name" from "a.name" and "price" from "span.price"

  Scenario: The row group is healed when only the container selector breaks
    Given a first run has recorded the row-container fingerprint
    When the container's class is renamed so "ul.products > li" matches no rows
    And I run the config again
    Then every row is extracted again
    And the run summary reports 1 confident heal

  Scenario: Two look-alike row groups are refused rather than guessed
    Given a first run has recorded the row-container fingerprint, with a second identical listing also present
    When the container's class is renamed so two identical row groups both match
    And I run the config again
    Then no records are extracted
    And the run summary reports 1 uncertain match

  Scenario: A single stray look-alike is not fabricated into a listing
    Given a first run has recorded the row-container fingerprint
    When the listing collapses so only a single row-like element remains
    And I run the config again
    Then no records are extracted
    And the run summary reports 1 uncertain match

  Scenario: With no prior fingerprint a broken container simply yields nothing
    Given the container never matched in a prior run
    When I run the config
    Then no records are extracted
    And the run summary reports no heals
