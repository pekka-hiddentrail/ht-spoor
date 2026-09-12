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
| `operational.feature` | Politeness & rate limiting | §2d | `spoor/operational` | 1 |
| `output.feature` | Output pipeline (pluggable sinks) | §2d | `spoor/operational` | 1 / 3.5 |
| `interaction.feature` | Interaction execution (native/jittered) | §2 | `spoor/core` | 2 |
| `api_discovery.feature` | API surface discovery | §2b | `spoor/api_discovery` | 2.5 |
| `signals.feature` | Client-side signals catalog | §2c | `spoor/signals` | 2.5 |
| `security.feature` | Data handling, redaction, sandbox registry | §2h | `spoor/security` | 2.5 |
| `resolution.feature` | Tier dispatcher / escalation, then tier-3 self-healing | §2 | `spoor/core` | 1 / 3 |
| `serving.feature` | MCP server & REST API (read-only) | §2f | `spoor/serving` | 5 |
| `exploration.feature` | Exploration mode + safety | §2e | `spoor/exploration` | 6 |
| `testgen.feature` | Test-automation run generation | §2g | `spoor/testgen` | 6 |

Status: `extraction.feature` (§2a) is authored and its tier-1 scenarios are
implemented and green; its infinite-scroll scenario is tagged `@tier2` and
skipped until tier-2 browser rendering lands. `operational.feature` (§2d) has
its Phase-1 politeness slice authored and green — respect `robots.txt` (default
on) and honor the crawl-delay. `output.feature` (§2d) has its Phase-1 output
pipeline authored and green — schema-validated JSON/JSON Lines/CSV sinks with
format chosen by extension or `--format`; SQLite/Parquet sinks and the Phase-3.5
items (retry/error classification, CAPTCHA detection, change detection, run
observability) are authored when those turns come. `resolution.feature` (§2)
has its Phase-1 dispatcher slice authored and green — the escalation seam that
picks a resolution tier and, for a browser-only capability, escalates from the
implemented tier 1 to a declared-but-stubbed tier 2 that fails with a clear
"not yet available"; tier-2 rendering and tier-3 self-healing behaviour are
authored when those tiers are built. The remaining feature files are authored
when their phase begins.
