# Serving the map over MCP: the read-only MCP consumption mode — ROADMAP.md §2f.
#
# The second §2f serving mode beside the REST API: an MCP server so an agent can
# consult the map Spoor already captured as a tool, without re-crawling. It sits
# over the same store and answers with the same redaction-guarded view (§2h) as
# the REST surface.
#
# NON-NEGOTIABLE (§2f/§2h): the serving layer is READ-ONLY, always. The MCP server
# exposes only tools that read the captured map — never a tool that changes a
# target or the stored map. This is pinned below by a scenario asserting the
# exposed tool set is exactly the read-only allowlist and every tool is marked
# read-only and non-destructive.

Feature: A read-only MCP server answers from a captured map
  As an agent that wants to reuse what Spoor already mapped
  I want to consult the map through read-only MCP tools
  So that a known-good map is available as a tool without re-crawling

  Background:
    Given an MCP server over a map containing:
      | url                       | title                    | captured_at          |
      | https://shop.example/p/1  | Widget                   | 2020-01-01T00:00:00Z |
      | https://other.example/x   | About                    | 2020-01-01T00:00:00Z |
      | https://shop.example/leak | Bearer abcdef1234567890x | 2020-01-01T00:00:00Z |

  Scenario: The MCP server exposes only read-only tools
    Then the MCP tools are exactly "get_map" and "list_mapped_domains"
    And every MCP tool is marked read-only and non-destructive

  Scenario: An MCP client fetches a mapped URL's records with freshness
    When I call the MCP tool "get_map" with url "https://shop.example/p/1"
    Then the MCP result's first record "title" equals "Widget"
    And the MCP result carries a capture time and a non-negative age

  Scenario: A secret in a served record is redacted before it leaves
    When I call the MCP tool "get_map" with url "https://shop.example/leak"
    Then the MCP result's first record "title" equals "Bearer [REDACTED]"

  Scenario: An unmapped URL errors rather than being fabricated
    When I call the MCP tool "get_map" with url "https://shop.example/nope"
    Then the MCP call fails with a not-mapped error

  Scenario: The mapped domains can be listed over MCP
    When I call the MCP tool "list_mapped_domains"
    Then the MCP domains include "shop.example"
    And the MCP domains include "other.example"
