# Tier-3 cross-run re-anchoring (§2, §2d). Companion to self_healing_runs.feature
# (single-record wiring) and self_healing_items.feature (per-row healing).
#
# Fingerprints are captured on a successful resolve and persisted per domain, so a
# later run can heal a selector that broke. But markup drifts over *many* redesigns,
# not just one: if tier 3 only ever healed against the *first* shape it recorded, a
# second redesign that moved the element further from that original shape would
# eventually fall below the confidence threshold and stop healing — even though each
# individual redesign was a small, healable step.
#
# Re-anchoring closes that gap. When tier 3 heals a field *confidently*, it rewrites
# the stored fingerprint to the healed element's *current* shape. So the next
# redesign heals from the most recent shape, not the original — drift is absorbed
# one healable step at a time. Reliability-first (§2, §1): only a **confident** heal
# re-anchors; an uncertain match never overwrites the good anchor with a guess. This
# is always-on and independent of the capture opt-in, like fingerprint persistence
# itself. These scenarios drive real tier-1 runs against an in-memory transport,
# sharing one temp per-domain cache across runs.

Feature: Tier 3 re-anchors a healed field to its most recent shape
  As someone scraping a target whose markup drifts across successive redesigns
  I want each confident heal to become the new anchor
  So that a later redesign heals from the most recent shape, not only the first

  Background:
    Given a config extracting a "name" field with selector "h2.title"

  Scenario: A confident heal re-anchors so a later redesign still heals
    Given a first run has recorded the field's original fingerprint
    When the markup is redesigned once so "h2.title" matches nothing
    And I run the config again
    Then the "name" field value is present
    And the run summary reports 1 confident heal
    When the markup is redesigned a second time, further from the original
    And I run the config again
    Then the "name" field value is present
    And the run summary reports 1 confident heal

  Scenario: Without the intermediate heal the second redesign is only uncertain
    Given a first run has recorded the field's original fingerprint
    When the markup is redesigned straight to the second shape
    And I run the config again
    Then the "name" field is null
    And the run summary reports 1 uncertain match

  Scenario: An uncertain match does not re-anchor the good fingerprint
    Given a first run has recorded the field's original fingerprint
    When the page is replaced with unrelated markup
    And I run the config again
    Then the "name" field is null
    And the run summary reports 1 uncertain match
    When the markup is redesigned once so "h2.title" matches nothing
    And I run the config again
    Then the "name" field value is present
    And the run summary reports 1 confident heal
