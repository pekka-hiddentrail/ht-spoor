# Tier-3 self-healing for listings: heal a field selector that breaks *within*
# repeating rows (§2, §2d). Companion to self_healing_runs.feature, which covers
# the single-record case.
#
# In a listing (a config with an `item` selector), each field's selector resolves
# relative to each matched row. When such a field's selector later matches nothing
# inside the rows — a class rename in a redesign — but the rows themselves still
# match, tier 3 re-resolves the field *per row* by scoring the candidate elements
# within that row's subtree against a fingerprint captured while the selector
# worked.
#
# Row text varies from row to row, so it cannot identify a field across a listing;
# item-mode fingerprints are therefore **text-agnostic** — they match on tag, id,
# class, other attributes, and structural position within the row, all of which
# are constant across a listing's structurally-identical rows. Reliability-first
# (§2, §1): a confident structural match fills that row's field; a sub-threshold
# best candidate is a flagged "uncertain match" and the field stays null — never a
# fabricated value. Healing matches only against **prior-run** fingerprints, never
# one remembered earlier in the same run, so a row that genuinely lacks an optional
# field is never filled in from its sibling rows.
#
# Scope of this slice (see the §2 tier-3 item-mode decision note): healing field
# selectors *within* rows the `item` selector still matches. Healing the `item`
# selector itself when the row container breaks (total data loss) needs a
# cross-row-invariant matching model plus group resolution and is a stated
# follow-on, as is cross-run re-anchoring and the perceptual-hash component. These
# scenarios drive real tier-1 runs against an in-memory transport, sharing one
# temp per-domain cache across runs.

Feature: A listing heals a field whose selector broke inside its rows
  As someone scraping a listing whose row markup churns
  I want a field that stops matching inside the rows re-resolved per row
  So that a redesign degrades to reviewable per-row heals, not lost columns

  Background:
    Given a listing config with item "li.product-card" extracting "name" from "a.name" and "price" from "span.price"

  Scenario: A field class renamed across every row is healed in each row
    Given a first run has recorded the rows' field fingerprints
    When the "price" field's class is renamed so "span.price" matches nothing in any row
    And I run the config again
    Then every row still has a "price" value
    And the run summary reports 3 confident heals

  Scenario: A row that genuinely lacks the field is not filled from its siblings
    Given a first run has recorded the rows' field fingerprints
    When the "price" field's class is renamed and one row drops its price element
    And I run the config again
    Then the rows that kept a price element still have a "price" value
    And the row missing its price element has a null "price"
    And the run summary reports 2 confident heals
    And the run summary reports 1 uncertain match

  Scenario: With no prior fingerprint a broken field in a listing simply yields null
    Given the rows do not match "span.price"
    When I run the config
    Then every row has a null "price"
    And the run summary reports no heals
