# `features/` — BDD specifications (one `.feature` per capability)

Spoor is developed **BDD-first** (ROADMAP.md §4a, CLAUDE.md). For every named
capability the order is always: write/extend the `.feature` file here →
add/update `pytest-bdd` step definitions in `tests/` → implement → run the full
local gate. These Gherkin scenarios define what "done" means in plain,
reviewable language *before* any code is written. They sit **above** — never
instead of — the property-based/mutation tests (§5.3) and golden-master
diffing (§5.4).

## Planned inventory

Each capability maps to a `spoor/` subpackage and a ROADMAP phase (§4). Files
are authored when their phase begins, not up front.

| Feature file | Capability | ROADMAP | Package | Phase |
|---|---|---|---|---|
| `extraction.feature` | Declarative extraction configs | §2a | `spoor/core`, CLI | 1 |
| `operational.feature` | Operational essentials | §2d | `spoor/operational` | 1 / 3.5 |
| `interaction.feature` | Interaction execution (native/jittered) | §2 | `spoor/core` | 2 |
| `api_discovery.feature` | API surface discovery | §2b | `spoor/api_discovery` | 2.5 |
| `signals.feature` | Client-side signals catalog | §2c | `spoor/signals` | 2.5 |
| `security.feature` | Data handling, redaction, sandbox registry | §2h | `spoor/security` | 2.5 |
| `resolution.feature` | Tier-3 resolution / self-healing | §2 | `spoor/core` | 3 |
| `serving.feature` | MCP server & REST API (read-only) | §2f | `spoor/serving` | 5 |
| `exploration.feature` | Exploration mode + safety | §2e | `spoor/exploration` | 6 |
| `testgen.feature` | Test-automation run generation | §2g | `spoor/testgen` | 6 |

No `.feature` files exist yet — Phase 0 is scaffold only. The first to author is
`extraction.feature` when Phase 1 starts.
