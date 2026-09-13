# Tier-3 self-healing with a perceptual-hash visual signal (§2, §2d). The last
# tier-3 component from the §2 tier table: "DOM fingerprint + attribute similarity
# + perceptual-hash on a cropped screenshot, no model call". It rides with the
# browser tier, because a screenshot needs a rendered page.
#
# Why it matters, and where it earns its keep: a *leaf* element that carries almost
# no inner text — an icon, a logo, an image thumbnail — has a thin DOM identity
# (tag, a class or two, structural position), so a class rename plus an attribute
# churn in a redesign can drop its DOM-only heal score below the confidence bar,
# even though the element is re-rendered pixel-for-pixel the same. The perceptual
# hash of a cropped screenshot is exactly the identity that survives that churn.
# It is blended into the same weighted score as every other signal, applicable
# only when both the stored fingerprint and the candidate carry a visual hash — so
# a run that never took a screenshot (tier 1) behaves exactly as before.
#
# The value is isolated cleanly below: two runs apply the *same* DOM churn to the
# same field; the only difference is whether the element still looks the same.
# When it does, the visual signal lifts a DOM-only-uncertain match to a confident
# heal; when the appearance genuinely changed, the signal withholds — the match
# stays uncertain and the field is left null (reliability-first, §2, §1), so the
# signal is never a blanket confidence boost.
#
# These scenarios drive the *real* browser tier against a live loopback server
# (a perceptual hash needs actual rendered pixels), sharing one temp per-domain
# fingerprint cache across runs. The heal counts are read from the run summary;
# the matched text is never exposed (§2h).

Feature: A visual (perceptual-hash) signal heals a no-text element whose markup churns
  As someone scraping icon/image/logo fields whose surrounding markup churns
  I want a cropped-screenshot perceptual hash to corroborate a shaky DOM heal
  So that a low-text element re-renders the same is re-resolved, not lost

  Background:
    Given a single-record config reading the "logo" image's "src" from ".brand-logo"

  Scenario: A browser run records a visual hash alongside the DOM fingerprint
    When the config is run against the original page in the browser
    Then the field is extracted
    And the stored fingerprint for "logo" carries a visual hash

  Scenario: An unchanged appearance heals a DOM-only-uncertain match confidently
    Given a first browser run has recorded the logo's fingerprint
    When the logo's class and attributes change but it renders the same
    And the config is run against the redesigned page in the browser
    Then the field is extracted again
    And the run summary reports 1 confident heal

  Scenario: A changed appearance is not rescued by the visual signal
    Given a first browser run has recorded the logo's fingerprint
    When the logo's class and attributes change and it now renders differently
    And the config is run against the redesigned page in the browser
    Then the field is left null
    And the run summary reports 1 uncertain match
