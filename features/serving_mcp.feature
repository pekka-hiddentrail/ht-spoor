# Serving the map over MCP: the read-only MCP consumption mode — ROADMAP.md §2f.
#
# The second §2f serving mode beside the REST API: an MCP server so an agent can
# consult the map Spoor already captured as a tool, without re-crawling. It sits
# over the same store and answers with the same redaction-guarded view (§2h) as
# the REST surface.
#
# NON-NEGOTIABLE (§2f/§2h): the serving layer is READ-ONLY with respect to the
# TARGET, always — no tool changes a target. A plain server exposes only tools that
# read the captured map, each marked read-only and non-destructive (pinned below).
# The non-negotiable also permits triggering a new read/observation run, so an
# opt-in force-recheck tool re-runs a mapped URL's extraction (a read of the target,
# never a change to it) and refreshes the local map. That tool is honestly annotated
# NON-read-only (it writes the local map and fetches) but still NON-destructive — no
# tool on this server is ever destructive to a target.

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

  Scenario: A plain MCP server exposes only read-only tools
    Then the MCP tools are exactly "get_map" and "list_mapped_domains"
    And every MCP tool is marked read-only and non-destructive

  Scenario: A recheck-enabled MCP server also exposes a non-read recheck tool
    # The reframed guarantee: recheck_map is honestly not read-only (it fetches and
    # writes the local map) but is still non-destructive — nothing changes the target.
    Given the MCP server allows force-recheck
    Then the MCP tools are exactly "get_map", "list_mapped_domains" and "recheck_map"
    And every MCP tool is marked non-destructive
    And the "recheck_map" tool is not marked read-only

  Scenario: An MCP force-recheck re-runs a mapped URL and returns the fresh result
    Given the MCP server allows force-recheck
    When I call the MCP tool "recheck_map" with url "https://shop.example/p/1"
    Then the MCP result's first record "title" equals "Widget (rechecked)"
    And the MCP result carries a capture time and a non-negative age

  Scenario: An MCP force-recheck of an unmapped URL errors rather than fabricating
    Given the MCP server allows force-recheck
    When I call the MCP tool "recheck_map" with url "https://shop.example/nope"
    Then the MCP call fails with a not-mapped error

  Scenario: An MCP client fetches a mapped URL's records with freshness
    When I call the MCP tool "get_map" with url "https://shop.example/p/1"
    Then the MCP result's first record "title" equals "Widget"
    And the MCP result carries a capture time and a non-negative age

  Scenario: A secret in a served record is redacted before it leaves
    When I call the MCP tool "get_map" with url "https://shop.example/leak"
    Then the MCP result's first record "title" equals "Bearer [REDACTED]"

  Scenario: An MCP client fetches a mapped URL's exploration graph, redacted
    # The same state-action graph the REST surface serves, over the shared view —
    # so an agent can ask "what happens when I click X" as a tool. A secret captured
    # during exploration is redacted on the way out (§2h), like any served value.
    Given an explored graph is mapped for "https://shop.example/app"
    When I call the MCP tool "get_map" with url "https://shop.example/app"
    Then the MCP result's exploration graph has 2 states and 1 transition
    And the MCP result's exploration graph exposes no raw secret

  Scenario: An unmapped URL errors rather than being fabricated
    When I call the MCP tool "get_map" with url "https://shop.example/nope"
    Then the MCP call fails with a not-mapped error

  Scenario: The mapped domains can be listed over MCP
    When I call the MCP tool "list_mapped_domains"
    Then the MCP domains include "shop.example"
    And the MCP domains include "other.example"
