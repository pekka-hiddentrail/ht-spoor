# API surface discovery — layer 1, official spec discovery (ROADMAP.md §2b).
#
# The cheapest, most-certain layer, shipping first on its own: alongside every
# run, probe a short fixed list of conventional spec paths against the target's
# origin (/openapi.json, /swagger.json, /api-docs, /.well-known/openapi.json). A
# 200 carrying an `openapi` or `swagger` version key is a discovered spec; a 404,
# non-JSON, or a JSON body with no version key (a SPA's /api-docs HTML shell) is
# not — probes must never produce a false positive. Probing respects robots.txt
# (§6: never work around a disallow to find a spec) and reports what it observed,
# never a claim of a complete API. HTML/JS-bundle scanning, GraphQL introspection,
# and spec synthesis from captured traffic are later §2b slices.

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
