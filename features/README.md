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
| `api_discovery.feature` | API surface discovery (spec + GraphQL introspection) | §2b | `spoor/api_discovery` | 2.5 |
| `capture.feature` | Raw network capture (HAR) to local-only cache | §2b/§2c/§2h | `spoor/core`, `spoor/security` | 2.5 |
| `signals.feature`, `accessibility.feature`, `response_headers.feature`, `storage_state.feature` | Client-side signals catalog (console, a11y tree, response headers, storage state) | §2c | `spoor/signals` | 2.5 |
| `redaction.feature` | Data handling: secret redaction before shared output (sandbox registry later) | §2h | `spoor/security` | 2.5 |
| `observability.feature` | Run summary / observability | §2d | `spoor/operational` | 1 |
| `resolution.feature` | Tier dispatcher / escalation, then tier-3 self-healing | §2 | `spoor/core` | 1 / 3 |
| `self_healing.feature` | Tier-3 self-healing: scored element matching, no model call | §2 / §5.3 | `spoor/core` | 3 |
| `self_healing_runs.feature` | Tier-3 wired into a live run: persist fingerprints, heal across runs, surface counts | §2 / §2d | `spoor/core` | 3 |
| `serving.feature` | MCP server & REST API (read-only) | §2f | `spoor/serving` | 5 |
| `exploration.feature` | Exploration mode + safety | §2e | `spoor/exploration` | 6 |
| `testgen.feature` | Test-automation run generation | §2g | `spoor/testgen` | 6 |

Status: `extraction.feature` (§2a) is authored and green, including its
infinite-scroll scenario, which now runs a real headless browser (tier 2)
against a live loopback fixture server. `operational.feature` (§2d) has
its Phase-1 politeness slice authored and green — respect `robots.txt` (default
on) and honor the crawl-delay. `output.feature` (§2d) has its Phase-1 output
pipeline authored and green — schema-validated JSON/JSON Lines/CSV sinks with
format chosen by extension or `--format`; SQLite/Parquet sinks and the Phase-3.5
items (retry/error classification, CAPTCHA detection, change detection, run
observability) are authored when those turns come. `resolution.feature` (§2)
has its Phase-1 dispatcher slice authored and green — the escalation seam that
picks a resolution tier and, for a browser-only capability (infinite scroll),
routes past the static tier 1 to the browser-backed tier 2; tier-3 self-healing
behaviour is authored when that tier is built. `observability.feature` (§2d) is
authored and green — a structured, operator-facing run summary.

Phase-2.5 is under way: `api_discovery.feature` (§2b) covers published-spec
discovery — conventional paths and references scanned from the landing page's
HTML and its same-origin JS bundles — GraphQL introspection, and spec synthesis
(layer 4): clustering a captured HAR's requests into templated endpoints and
writing a synthesized OpenAPI document to the local-only cache (counts only reach
shared output, §2h), and action-to-endpoint correlation (layer 5): marking a
checkpoint before each page load and scroll, then attributing each captured
request to the action whose time window it fell in — a time-window approximation,
never proven causation, with the per-action map kept local-only and only counts
shared (§2h); `capture.feature` records the browser
tier's HAR to a local-only, git-ignored cache (§2h); and the §2c signals catalog
is landing signal-by-signal — console output/JS errors, the accessibility tree,
response-header fingerprints, and client-side storage state — each opt-in,
browser-tier-only, with raw captures kept local-only and only safe/derived facts
(or, for storage state, redacted entries) surfaced to shared output. The §2h
secret-redaction pipeline (`redaction.feature`) is authored and green and backs
that storage-state surfacing.

Phase 3 has begun: `self_healing.feature` (§2, §5.3) authors the tier-3 scoring
core — capture an element's fingerprint while its selector works, and when the
selector later breaks, re-resolve by scoring every candidate (tag, id, class,
attribute, inner-text, and structural similarity, no model call), flagging a
low-confidence best candidate as an "uncertain match" rather than guessing and
always recording the winning score plus runners-up. It is backed below the
Gherkin layer by the §5.3 `hypothesis` mutation corpus (a statistical
success-rate property, not a shape Gherkin suits), which gates the merge-blocking
≥95% bar (currently ~99.8%). `self_healing_runs.feature` (§2, §2d) then wires that
engine into a live run: while a field's selector resolves, the run fingerprints
the element into a per-domain cache that persists across runs (the §0-sanctioned
runtime-learned cache, local-only per §2h); on a later run, if that selector
matches nothing but a fingerprint was remembered, tier 3 re-resolves the field by
scoring the page's candidates — a confident heal fills the field, a sub-threshold
best candidate is a flagged "uncertain match" that leaves the field null, and the
run summary (§2d) surfaces the confident/uncertain counts (never the matched text,
§2h). This slice threads healing through single-record configs only; `item`-mode
healing, cross-run re-anchoring, and the perceptual-hash-on-screenshot component
are follow-on slices (see the §2 tier-3 decision notes). The sandbox registry
(§2e/§2h) and the remaining feature files are authored when their phase begins.
