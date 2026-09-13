# Tier 3 self-healing — the scored-matching core (ROADMAP.md §2 tier table, §5.3).
#
# Per §1 the single highest-priority piece of engineering in the plan, and per §2
# built with "no model call": when a resolved element's selector later matches
# nothing, tier 3 re-finds the element by scoring every candidate on the page
# against a fingerprint captured while the selector still worked — DOM tag,
# id, classes, other attributes, inner text, and structural context (ancestor
# tag chain + sibling position). The highest-scoring candidate wins.
#
# Reliability-first (§2, §1): a win at or above a tunable confidence threshold is
# an auto-heal; a best candidate below the threshold but above zero is flagged an
# "uncertain match" for manual review, never silently used as if certain. Every
# resolution — confident or not — records its winning score and the runner-up
# candidates it considered, so "why did it heal here" is always answerable
# straight from the result, not a bolted-on feature (§2).
#
# This is the first slice of Phase 3: the pure scoring engine over static DOM (via
# parsel), plus the §5.3 hypothesis mutation corpus (≥95%, merge-blocking) that
# lives in tests/, not here — a statistical success-rate property is not a shape
# Gherkin suits (§4a/CLAUDE.md). Deferred to follow-on slices, and noted as such
# in the §2 tier-3 decision note: cross-run fingerprint persistence (a per-domain
# cache), wiring tier 3 into the escalation dispatcher and surfacing uncertain
# matches in the run summary (§2d), and the perceptual-hash-on-screenshot
# component (needs the browser tier). These scenarios drive the engine directly.

Feature: Tier 3 re-resolves an element after its markup changes
  As someone whose scrape must survive a site's markup churn
  I want a broken selector to heal to the same element it used to find
  So that a run keeps working across a redesign instead of silently losing a field

  Background:
    Given a page where the "Beta Gadget" heading was resolved and fingerprinted

  Scenario: A renamed class heals back to the same element
    When the heading's class is renamed so the original selector matches nothing
    And tier 3 heals against the stored fingerprint
    Then tier 3 resolves the "Beta Gadget" heading
    And the heal is confident

  Scenario: Shuffled attributes and an added wrapper still heal to the same element
    When the heading's attributes are shuffled and it is wrapped in a new element
    And tier 3 heals against the stored fingerprint
    Then tier 3 resolves the "Beta Gadget" heading
    And the heal is confident

  Scenario: A confident heal explains its score and the runners-up it considered
    When the heading's class is renamed so the original selector matches nothing
    And tier 3 heals against the stored fingerprint
    Then the heal records a winning confidence score
    And the heal records the runner-up candidates it considered

  Scenario: A weak match is flagged uncertain rather than used
    When the heading is changed beyond confident recognition
    And tier 3 heals against the stored fingerprint
    Then the heal is flagged as an uncertain match
    And the heal still records why it chose its best candidate

  Scenario: With no candidate elements there is nothing to heal
    When the page is replaced with one that has no candidate elements
    And tier 3 heals against the stored fingerprint
    Then tier 3 resolves nothing
