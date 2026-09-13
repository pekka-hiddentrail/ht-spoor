# Serving the map: read-only REST API over a captured run map — ROADMAP.md §2f.
#
# §2f turns "files on disk" into something an agent or script can consult without
# re-crawling. This first slice is the read-only REST API over a persisted
# per-domain map that a run populates: which URLs have been mapped, and the
# extracted records plus freshness for each.
#
# NON-NEGOTIABLE (§2f/§2h): the serving layer is READ-ONLY, always. It answers
# questions about a captured map and exposes no state-changing action on a target.
# Every answer carries the capture time and its age; v1 never auto-rechecks (the
# freshness policy is backlogged, §9) — it always shows the age and waits to be
# asked to re-verify. It serves the same extracted records the output pipeline
# already writes, plus the §2h-safe projection of the observed API surface (any
# published spec/GraphQL served whole; the synthesized spec and correlation as
# counts only — their templated paths stay local-only), never a raw local-only
# capture (HAR/storage state). Records and surface alike are redacted on the way
# out, honoring §2h.
#
# The MCP server mode (§2f) and a force-recheck endpoint are deliberately deferred
# to follow-on slices; both sit over this same store and service.

Feature: A read-only API serves a captured map with freshness
  As an agent or script that wants to reuse what Spoor already mapped
  I want to query a domain's mapped URLs and their records without re-crawling
  So that a known-good map is consulted instead of rediscovered every time

  Background:
    Given a served map containing:
      | url                         | title                    | captured_at          |
      | https://shop.example/p/1    | Widget                   | 2020-01-01T00:00:00Z |
      | https://shop.example/p/2    | Gadget                   | 2020-01-01T00:00:00Z |
      | https://other.example/about | About Us                 | 2020-01-01T00:00:00Z |
      | https://shop.example/leak   | Bearer abcdef1234567890x | 2020-01-01T00:00:00Z |

  Scenario: A mapped URL returns its records with a freshness age
    When I GET "/map?url=https://shop.example/p/1"
    Then the response status is 200
    And the first record's "title" equals "Widget"
    And the response carries a capture time and a non-negative age

  Scenario: A secret in a served record is redacted before it leaves
    # §2h names an API response as a shared surface: known secret shapes are
    # redacted on the way out even though the local store may hold them raw.
    When I GET "/map?url=https://shop.example/leak"
    Then the response status is 200
    And the first record's "title" equals "Bearer [REDACTED]"

  Scenario: A mapped URL's observed API surface is served alongside its records
    # §2h split: the published spec and GraphQL endpoint are served whole; the
    # synthesized spec and action correlation are counts only — their templated
    # paths (and the local-only doc path) never reach this shared surface.
    Given the map records an observed API surface for "https://shop.example/api-home"
    When I GET "/map?url=https://shop.example/api-home"
    Then the response status is 200
    And the API surface reports an "openapi" spec
    And the API surface reports a GraphQL endpoint with 42 types
    And the API surface reports 3 synthesized endpoints
    And the served API surface exposes no templated endpoint path

  Scenario: An unmapped URL is reported as not found, never fabricated
    When I GET "/map?url=https://shop.example/p/999"
    Then the response status is 404

  Scenario: The mapped domains can be listed
    When I GET "/domains"
    Then the response status is 200
    And the domains list contains "shop.example"
    And the domains list contains "other.example"

  Scenario: The serving app is read-only — every route exposes only GET
    Then every serving route is read-only

  Scenario: A health check reports the server is up
    When I GET "/healthz"
    Then the response status is 200
