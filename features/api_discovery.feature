# API surface discovery — layer 1, official spec discovery (ROADMAP.md §2b).
#
# The cheapest, most-certain layer, shipping first on its own: alongside every
# run, probe a short fixed list of conventional spec paths against the target's
# origin (/openapi.json, /swagger.json, /api-docs, /.well-known/openapi.json). A
# 200 carrying an `openapi` or `swagger` version key is a discovered spec; a 404,
# non-JSON, or a JSON body with no version key (a SPA's /api-docs HTML shell) is
# not — probes must never produce a false positive. Probing respects robots.txt
# (§6: never work around a disallow to find a spec) and reports what it observed,
# never a claim of a complete API.
#
# Layer 1's second half (below the conventional-path scenarios): when no
# conventional path serves a spec, scan for a reference to one — a Redoc
# `spec-url`, a Swagger-UI `url:`, or any link carrying the spec vocabulary
# (openapi/swagger/api-docs) — first in the landing page's HTML, then inside the
# same-origin JS bundles it loads (where SPAs usually keep that config). Every
# candidate is validated exactly as strictly as a conventional probe, so a false
# lead is never reported. Spec synthesis from captured traffic is a later §2b
# slice.

Feature: A run discovers an official API spec when the target serves one
  As someone mapping a product's API surface
  I want a run to notice an official spec the target already publishes
  So that I start from the authoritative document, not a reverse-engineered guess

  Scenario: An OpenAPI 3 document at a conventional path is discovered
    Given a target that serves an OpenAPI 3 document at "/openapi.json"
    When I run the config and capture the summary
    Then the run reports a discovered "openapi" spec at "/openapi.json"
    And the discovered spec version is "3.0.1"
    And the summary describes the API spec as observed, not complete

  Scenario: A Swagger 2.0 document at a conventional path is discovered
    Given a target that serves a Swagger 2.0 document at "/swagger.json"
    When I run the config and capture the summary
    Then the run reports a discovered "swagger" spec at "/swagger.json"
    And the discovered spec version is "2.0"

  Scenario: A target with no spec reports none, honestly
    Given a target that serves no spec at any conventional path
    When I run the config and capture the summary
    Then the run reports no discovered API spec
    And the summary says no API spec was discovered

  Scenario: A non-spec 200 at a conventional path is not a false positive
    Given a target whose "/api-docs" returns an HTML page, not a spec
    When I run the config and capture the summary
    Then the run reports no discovered API spec

  Scenario: A spec path disallowed by robots.txt is not probed
    Given a target that serves an OpenAPI 3 document at "/openapi.json"
    And a robots.txt that disallows "/openapi.json"
    When I run the config and capture the summary
    Then the run reports no discovered API spec

  # --- Layer 1, second half: spec references in the landing page HTML ------

  Scenario: A spec linked from the landing page HTML is discovered
    Given a target whose landing page references a spec at "/v3/api-docs"
    And a target that serves an OpenAPI 3 document at "/v3/api-docs"
    When I run the config and capture the summary
    Then the run reports a discovered "openapi" spec at "/v3/api-docs"
    And the discovered spec version is "3.0.1"

  Scenario: A Redoc spec-url pointing at a non-conventional path is discovered
    Given a target whose landing page has a Redoc spec-url of "/internal/spec"
    And a target that serves an OpenAPI 3 document at "/internal/spec"
    When I run the config and capture the summary
    Then the run reports a discovered "openapi" spec at "/internal/spec"

  Scenario: A landing-page reference that isn't a real spec is not a false positive
    Given a target whose landing page references a spec at "/swagger-ui.html"
    And a target whose "/swagger-ui.html" returns an HTML page, not a spec
    When I run the config and capture the summary
    Then the run reports no discovered API spec

  Scenario: A referenced spec path disallowed by robots.txt is not probed
    Given a target whose landing page references a spec at "/v3/api-docs"
    And a target that serves an OpenAPI 3 document at "/v3/api-docs"
    And a robots.txt that disallows "/v3/api-docs"
    When I run the config and capture the summary
    Then the run reports no discovered API spec

  Scenario: A spec referenced only inside a JS bundle is discovered
    Given a target whose landing page loads the script "/static/app.js"
    And the script "/static/app.js" references a spec at "/v3/api-docs"
    And a target that serves an OpenAPI 3 document at "/v3/api-docs"
    When I run the config and capture the summary
    Then the run reports a discovered "openapi" spec at "/v3/api-docs"

  Scenario: A JS bundle disallowed by robots.txt is not scanned
    Given a target whose landing page loads the script "/static/app.js"
    And the script "/static/app.js" references a spec at "/v3/api-docs"
    And a target that serves an OpenAPI 3 document at "/v3/api-docs"
    And a robots.txt that disallows "/static/app.js"
    When I run the config and capture the summary
    Then the run reports no discovered API spec

  # --- Layer 2: GraphQL introspection --------------------------------------

  Scenario: A GraphQL endpoint with introspection enabled is discovered
    Given a target with a GraphQL endpoint at "/graphql" answering introspection
    When I run the config and capture the summary
    Then the run reports a discovered GraphQL schema at "/graphql"
    And the discovered GraphQL schema reports at least one type
    And the summary describes the GraphQL schema as observed

  Scenario: A GraphQL endpoint with introspection disabled is not discovered
    Given a target with a "/graphql" endpoint that refuses introspection
    When I run the config and capture the summary
    Then the run reports no discovered GraphQL schema

  Scenario: A target with no GraphQL endpoint reports none
    Given a target that serves no spec at any conventional path
    When I run the config and capture the summary
    Then the run reports no discovered GraphQL schema
