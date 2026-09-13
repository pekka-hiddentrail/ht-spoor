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
| `retry.feature` | Retry transient fetch failures with backoff (Retry-After honored), dead-letter the unrecoverable | §2d | `spoor/operational` | 3.5 |
| `browser_retry.feature` | Retry transient browser navigations (same classification/backoff) so a failed `page.goto` is dead-lettered, not a crash | §2d | `spoor/operational`, `spoor/core` | 3.5 |
| `anti_bot.feature` | Detect anti-bot/CAPTCHA challenges (reCAPTCHA/hCaptcha/Cloudflare) and fail loudly — detection, never bypass | §2d | `spoor/operational` | 3.5 |
| `change_detection.feature` | Skip re-extracting pages unchanged since the last run (conditional `ETag`/`Last-Modified` request, content-hash fallback), opt-in | §2d | `spoor/operational` | 3.5 |
| `resolution.feature` | Tier dispatcher / escalation, then tier-3 self-healing | §2 | `spoor/core` | 1 / 3 |
| `self_healing.feature` | Tier-3 self-healing: scored element matching, no model call | §2 / §5.3 | `spoor/core` | 3 |
| `self_healing_runs.feature` | Tier-3 wired into a live run: persist fingerprints, heal across runs, surface counts | §2 / §2d | `spoor/core` | 3 |
| `self_healing_items.feature` | Tier-3 in a listing: heal a field selector that breaks *within* rows, per row | §2 / §2d | `spoor/core` | 3 |
| `self_healing_reanchor.feature` | Tier-3 cross-run re-anchoring: a confident heal becomes the new anchor | §2 / §2d | `spoor/core` | 3 |
| `self_healing_container.feature` | Tier-3 heals a broken row *container* (`item` selector), with a repeating-group gate + ambiguity refusal | §2 / §2d | `spoor/core` | 3 |
| `self_healing_visual.feature` | Tier-3 perceptual-hash visual signal: a cropped-screenshot difference hash heals a low-text element whose markup churns | §2 / §2d | `spoor/core` | 3 |
| `serving.feature` | MCP server & REST API (read-only) | §2f | `spoor/serving` | 5 |
| `exploration.feature` | Exploration mode + safety | §2e | `spoor/exploration` | 6 |
| `testgen.feature` | Test-automation run generation | §2g | `spoor/testgen` | 6 |

The prose below describes what each feature file covers, in the present tense —
the machine-readable table above carries any planned-vs-built distinction via its
Phase column. `extraction.feature` (§2a) covers declarative extraction, including
an infinite-scroll scenario that runs a real headless browser (tier 2) against a
live loopback fixture server. `operational.feature` (§2d) covers politeness —
respecting `robots.txt` (default on) and honoring the crawl-delay. `output.feature`
(§2d) covers the output pipeline — schema-validated JSON/JSON Lines/CSV sinks with
format chosen by extension or `--format` (SQLite/Parquet sinks and the remaining
Phase-3.5 item — change detection — are specified for later turns; see the Phase
column). `retry.feature` (§2d) covers the tier-1 retry/error-classification
slice: a transient fetch failure (timeout, dropped connection, 5xx, 429) is
retried with backoff — honoring a server-sent `Retry-After` — while a permanent
one (other 4xx) is not, and a URL that can't be fetched lands in a dead-letter
log on the run summary instead of crashing the run. `browser_retry.feature` (§2d)
covers the same reliability at the browser tier: a `page.goto` that meets a
transient failure (a 5xx/429, or a navigation timeout / dropped connection) is
retried with the same policy and backoff, and a page it ultimately cannot load is
dead-lettered rather than crashing the run on an uncaught Playwright error — the
scenarios drive a real browser against a scripted flaky loopback server.
`anti_bot.feature` (§2d)
covers challenge detection: a fetched page matching a known anti-bot fingerprint
(a reCAPTCHA/hCaptcha widget, a Cloudflare interstitial) is flagged loudly on the
run summary rather than scraped as data — detection only, never a bypass attempt.
`change_detection.feature` (§2d) covers the opt-in monitoring optimization: with
`change_detection: true`, a re-run replays the `ETag`/`Last-Modified` a prior run
recorded as a conditional request and, on a 304 (or a body whose content hash
matches), records the page as unchanged and skips re-extracting it — off by
default, since skipping extraction is a behavior change a one-shot scrape
shouldn't get by surprise. `resolution.feature` (§2) covers the escalation seam that picks a resolution tier
and, for a browser-only capability (infinite scroll), routes past the static tier 1
to the browser-backed tier 2, then tier-3 self-healing. `observability.feature`
(§2d) covers the structured, operator-facing run summary.

`api_discovery.feature` (§2b) covers published-spec
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
secret-redaction pipeline (`redaction.feature`) backs that storage-state surfacing.

Tier-3 self-healing (§2, §5.3) spans several feature files. `self_healing.feature`
covers the scoring core — capture an element's fingerprint while its selector
works, and when the
selector later breaks, re-resolve by scoring every candidate (tag, id, class,
attribute, inner-text, structural, and descendant-composition similarity, no
model call), flagging a
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
§2h). `self_healing_items.feature` (§2, §2d) then extends that wiring to
**listings**: a field whose selector breaks *inside* the rows is healed per row,
scoring the candidates within each row against a text-agnostic fingerprint (a
listing's rows share structure but differ in text) — and, because healing only
matches a fingerprint a *prior* run recorded, a row that genuinely lacks an
optional field is left null, never filled from a sibling row. `self_healing_reanchor.feature`
(§2, §2d) then adds **cross-run re-anchoring**: when tier 3 heals a field
confidently, it rewrites the stored fingerprint to the healed element's current
shape, so a later redesign heals from the most recent shape rather than only the
first — drift is absorbed one healable step at a time, while an uncertain match
never overwrites the good anchor. The fingerprint was then enriched with
a **descendant-composition** signal (the multiset of tags an element contains) —
inert for leaf fields but the stable identity a *container* keeps when its own
class is renamed; a scoring-core change with no user-observable behavior on its own
(so no `.feature`, covered by unit tests + the mutation corpus), landed as
groundwork for the next feature. `self_healing_container.feature` (§2, §2d) uses it
to heal the **row-container (`item`) selector itself** when a redesign breaks it
and no rows match at all: rather than pick a single best element, it re-resolves a
coherent sibling group (same parent + tag) of two or more members, and is
reliability-first about refusing to fabricate — a lone look-alike is never promoted
to a one-row listing (the ≥2-member gate), and two distinct groups both matching
confidently are refused rather than guessed between (ambiguity refusal); either
refusal yields zero records surfaced as an uncertain match. Finally,
`self_healing_visual.feature` (§2, §2d) lands the last tier-3 component — the
**perceptual-hash visual signal**. Riding with the browser tier (a screenshot
needs a rendered page), it blends a difference hash of an element's cropped
screenshot into the same weighted score, applicable only when both the stored
print and the candidate carry one. Its scenarios drive the real browser tier
against a live loopback server over two runs sharing one temp cache: a low-text
logo whose class/attributes churn and which gains a wrapper drops below the
DOM-only bar, and the visual signal lifts it back to a confident heal only when it
still renders the same — a genuinely changed appearance leaves the match uncertain
and the field null (a corroborator, never a blanket boost). Together these six
feature files make up tier-3 self-healing.

`serving.feature` (§2f), `exploration.feature` (§2e), and `testgen.feature` (§2g),
along with the sandbox registry (§2e/§2h), are listed in the table above ahead of
implementation; their feature files are authored when their phase begins (see the
Phase column).
