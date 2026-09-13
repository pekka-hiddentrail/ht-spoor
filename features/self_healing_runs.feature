# Tier 3 wired into a live run: capture on success, heal on failure (§2, §2d).
#
# The tier-3 scoring core (features/self_healing.feature) becomes useful when a
# run uses it end to end (§2's "fingerprint capture on first success, scored
# matching on failure"): while a field's selector resolves, the run fingerprints
# the element and remembers it in a per-domain cache that persists across runs
# (the §0-sanctioned runtime-learned cache); on a later run, if that selector
# matches nothing but a fingerprint was remembered, tier 3 re-resolves the field
# by scoring the page's candidates against it.
#
# Reliability-first (§2, §1): a confident heal fills the field and is reported in
# the run summary (§2d); a best candidate below the confidence threshold is a
# flagged "uncertain match" — the field stays null (never silently filled) and
# the summary surfaces the count for review. Only field name + confidence reach
# the summary, never the matched text (§2h). With no remembered fingerprint,
# a broken selector behaves exactly as before — a null field, no heal.
#
# Scope of this slice (see the §2 tier-3 wiring decision note): single-record
# configs (no `item`), where each field selector maps to at most one element, so
# fingerprint-and-heal is an unambiguous 1:1. `item`-mode healing (many rows
# sharing a selector, needing a per-row strategy) is a stated follow-on, as is
# the perceptual-hash-on-screenshot component. These scenarios drive real runs
# (tier 1, static fetch) against an in-memory transport, sharing one temp cache.

Feature: A run heals a field whose selector broke since it was last seen
  As someone whose scrape must survive a site's markup churn
  I want a field that stops matching to be re-resolved from what I saw before
  So that a redesign degrades to a reviewable heal, not a silently-lost field

  Scenario: A field whose selector breaks between runs is healed on the next run
    Given a config extracting a "name" field with selector "h2.title"
    And a first run has recorded that field's fingerprint
    When the page markup changes so "h2.title" matches nothing
    And I run the config again
    Then the "name" field value is present
    And the run summary reports 1 confident heal

  Scenario: A heal too weak to trust is flagged uncertain and the field stays empty
    Given a config extracting a "name" field with selector "h2.title"
    And a first run has recorded that field's fingerprint
    When the page is replaced with unrelated markup
    And I run the config again
    Then the "name" field is null
    And the run summary reports 1 uncertain match

  Scenario: With no remembered fingerprint a broken selector simply yields null
    Given a config extracting a "name" field with selector "h2.title"
    And the page markup does not match "h2.title"
    When I run the config
    Then the "name" field is null
    And the run summary reports no heals
