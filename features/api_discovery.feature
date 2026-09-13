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
# lead is never reported.
#
# Layer 4 (spec synthesis) is the last section: when a run captured a HAR, cluster
# the API requests it recorded into templated endpoints (/users/1, /users/2 -> the
# one endpoint /users/{id}) and synthesize an OpenAPI document from them. This is
# reimplemented directly over the captured HAR (no mitmproxy2swagger dependency;
# see the §2b layer-4 decision note). It reads only the local HAR — no network —
# and is a bounded, inference-from-observed-traffic claim, never "the complete API".
# The synthesized document is written to the local-only cache; only counts reach
# shared output (§2h). Layer 5 (action-to-endpoint correlation) is still to come.

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

  # --- Layer 4: spec synthesis from a captured HAR -------------------------

  Scenario: Repeated ID paths in a captured HAR synthesize one templated endpoint
    Given a captured HAR with GET JSON requests to "/api/users/1", "/api/users/2", "/api/users/3"
    When I synthesize an API spec from the captured HAR
    Then the synthesized spec has a "GET" endpoint for "/api/users/{id}"
    And the synthesized spec clustered 3 requests into 1 endpoint
    And the run summary reports the synthesized endpoint count, not the paths
    And a synthesized OpenAPI document is written to the local-only cache

  Scenario: Distinct methods and paths stay distinct endpoints
    Given a captured HAR with a "GET" JSON request to "/api/products/10"
    And the captured HAR also has a "POST" JSON request to "/api/orders"
    When I synthesize an API spec from the captured HAR
    Then the synthesized spec has a "GET" endpoint for "/api/products/{id}"
    And the synthesized spec has a "POST" endpoint for "/api/orders"

  Scenario: Non-JSON responses are not treated as API endpoints
    Given a captured HAR whose only requests return HTML, not JSON
    When I synthesize an API spec from the captured HAR
    Then no API spec is synthesized

  Scenario: A cross-origin request in the HAR is not clustered into the surface
    Given a captured HAR with a same-origin JSON request to "/api/me"
    And the captured HAR also has a cross-origin JSON request
    When I synthesize an API spec from the captured HAR
    Then the synthesized spec has a "GET" endpoint for "/api/me"
    And the synthesized spec clustered 1 request into 1 endpoint

  Scenario: A run with no captured HAR synthesizes nothing
    Given a run that captured no HAR
    When I synthesize an API spec from the captured HAR
    Then no API spec is synthesized
