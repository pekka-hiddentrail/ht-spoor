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
| `extraction_robustness.feature` | Graceful degradation on empty / non-HTML / malformed / deep / non-ASCII pages — extract what's there, never crash | §2a | `spoor/core` | 1 |
| `operational.feature` | Politeness & rate limiting | §2d | `spoor/operational` | 1 |
| `output.feature` | Output pipeline (pluggable sinks) | §2d | `spoor/operational` | 1 / 3.5 |
| `interaction.feature` | Interaction execution (native/jittered) | §2 | `spoor/core` | 2 |
| `api_discovery.feature` | API surface discovery (spec + GraphQL introspection) | §2b | `spoor/api_discovery` | 2.5 |
| `capture.feature` | Raw network capture (HAR) to local-only cache | §2b/§2c/§2h | `spoor/core`, `spoor/security` | 2.5 |
| `signals.feature`, `accessibility.feature`, `response_headers.feature`, `storage_state.feature` | Client-side signals catalog (console, a11y tree, response headers, storage state) | §2c | `spoor/signals` | 2.5 |
| `redaction.feature` | Data handling: secret redaction before shared output (sandbox registry later) | §2h | `spoor/security` | 2.5 |
| `session.feature` | Bring-your-own-session: authenticate a run with a supplied browser storage state (cookies + localStorage); Spoor runs no login flow itself | §2h | `spoor/security`, `spoor/core` | 2.5 |
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
| `serving.feature` | Read-only serving of a captured map over a REST API (records + observed API surface, with freshness) | §2f | `spoor/serving` | 4 / 5 |
| `serving_mcp.feature` | Read-only serving of the same map over an MCP server (agent-facing tools; exploration-graph serving later) | §2f | `spoor/serving` | 4 / 5 |
| `exploration_safety.feature` | Exploration safety gate: destructive actions are sandbox-only, non-configurable | §2e | `spoor/exploration`, `spoor/security` | 5 |
| `exploration_state.feature` | Exploration state abstraction: normalize + hash the DOM so equivalent screens share one state id | §2e | `spoor/exploration` | 5 |
| `exploration_discovery.feature` | Exploration element discovery: pull the interactive elements from the accessibility tree as candidate actions | §2e | `spoor/exploration` | 5 |
| `exploration_control.feature` | Exploration run-level controls: hard budget (states/requests/wall-clock) + manual kill switch | §2e | `spoor/exploration` | 5 |
| `exploration_loop.feature` | Exploration explorer loop: the state-action graph orchestrator tying together discovery, safety, state abstraction, and run controls | §2e | `spoor/exploration` | 5 |
| `exploration_browser.feature` | Exploration in a real browser: the `spoor explore` command drives the whole stack against a live site via a headless-Chromium driver | §2e | `spoor/exploration`, CLI | 5 |
| `testgen.feature` | Test-automation run generation | §2g | `spoor/testgen` | 6 |

The prose below describes what each feature file covers, in the present tense —
the machine-readable table above carries any planned-vs-built distinction via its
Phase column. `extraction.feature` (§2a) covers declarative extraction, including
an infinite-scroll scenario that runs a real headless browser (tier 2) against a
live loopback fixture server. `extraction_robustness.feature` (§2a) is its
adversarial counterpart — empty, non-HTML, unclosed/malformed, pathologically deep,
and non-ASCII pages must degrade gracefully (extract what's there, leave the rest
null) rather than crash the run. `operational.feature` (§2d) covers politeness —
respecting `robots.txt` (default on) and honoring the crawl-delay. `output.feature`
(§2d) covers the output pipeline — schema-validated JSON/JSON Lines/CSV sinks with
format chosen by extension or `--format`, and — because an output file is a shared
surface — secret redaction (§2h) of record values before any write, on by default
(SQLite/Parquet sinks and the remaining Phase-3.5 item — change detection — are
specified for later turns; see the Phase column). `retry.feature` (§2d) covers the tier-1 retry/error-classification
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
covers challenge detection: a page matching a known anti-bot fingerprint
(a reCAPTCHA/hCaptcha widget, a Cloudflare interstitial) is flagged loudly on the
run summary rather than scraped as data — whether it arrives in a 2xx response or
*behind* an error status (a 403/503 interstitial), where the run is both
dead-lettered and reported as a challenge. Detection only, never a bypass attempt.
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
secret-redaction pipeline (`redaction.feature`) backs that storage-state
surfacing, and the same `redact_records` guard now runs on the primary
extracted-record path too — the §2d output pipeline's files and the §2f serving
API's responses (both pin a scenario that a bearer token leaves as `[REDACTED]`).
`session.feature` (§2h) is the input counterpart of that storage-state signal:
it authenticates a run with a browser session the user captured once themselves —
the static tier sends the session's cookies, the browser tier loads the whole
storage state (cookies + localStorage), and a target gated behind a localStorage
token naturally escalates from the static tier to the browser. A missing or
malformed session file fails the run loudly rather than scraping anonymously, and
the supplied secret-bearing state is never echoed to shared output. Spoor performs
no login/MFA/SSO flow itself (§2h, §0) — bring-your-own-session only.

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

`serving.feature` (§2f) has begun: its first slice is the **read-only REST API**
over a captured map. A run remembers its extracted records for a URL in a
persisted per-domain map (`spoor/serving/store.py`, under the local cache root),
and the API (`spoor/serving/api.py`, FastAPI) answers `GET` queries about it —
which domains are mapped, and a URL's records — plus the §2h-safe projection of
the API surface the run observed (any published spec/GraphQL endpoint served
whole; the synthesized spec and action correlation as counts only, so their
templated paths never leave the machine) — with a freshness age, never a
state-changing action on the target (the §2f read-only non-negotiable). It serves
the same records the output pipeline writes, never a raw local-only capture (§2h),
and both records and surface pass through the redaction guard on the way out.
`serving_mcp.feature` (§2f) is the second consumption mode: an MCP server
(`spoor/serving/mcp_server.py`, run by `spoor serve-mcp`) exposing the same map to
agents (`list_mapped_domains`, `get_map`). It shares the exact store and the
single `views.map_view` answer-builder with the REST surface — so freshness and
§2h redaction live in one place. A **force-recheck** seam now ships on both
surfaces, opt-in behind `--recheck` and **off by default**: a `POST /map/recheck`
route (REST) and a `recheck_map` tool (MCP) re-run a mapped URL's extraction — a
fresh read/observation of the target, never a change to it — and refresh the local
map (`spoor/serving/recheck.py`). Because a recheck observes but never changes a
target, the pinned guarantee is **"no route or tool changes a target"**, not "no
non-GET route": both files pin that a plain server stays GET-only / read-tools-only,
while a recheck-enabled server adds exactly the one seam — non-destructive, and (on
MCP) honestly marked non-read-only since it fetches and rewrites the local map. The
config needed to reproduce a run is persisted with each entry but stays local-only,
never served.

`exploration_safety.feature` (§2e) opens exploration mode with its **safety
foundation**, built before anything that can fire an action exists. Two pure-logic
pieces plus the gate that combines them: a **sandbox registry**
(`spoor/security/sandbox.py`) that recognizes a target as a sandbox only when its
host is loopback (`localhost` / `127.*` / `::1`) or the operator explicitly declared
it one; and a **destructive-action classifier** (`spoor/exploration/safety.py`) that
matches the §2e keyword list (delete, remove, buy, purchase, pay, confirm, send,
submit-payment, log out) as whole words in an action's label. The gate
(`evaluate_action`) permits a non-destructive action anywhere, permits a destructive
one only inside a sandbox, and otherwise skips it with a log-ready reason. The §2e
non-negotiable — destructive actions are sandbox-only and **non-configurable** — is
pinned both behaviorally (a destructive action on a real target is skipped) and
structurally (a scenario asserts the gate's parameters are exactly target/action,
so no bypass flag can exist).

`exploration_state.feature` (§2e) is the second slice — still pure logic — porting
Crawljax's **state abstraction**: `spoor/exploration/state.py:state_id(html)`
normalizes a page's DOM and hashes it to a stable id, so revisiting an equivalent
screen is recognized instead of exploding into near-duplicates (what lets the later
explorer build a *finite* state graph). Identity is the page's tag structure plus a
small allowlist of stable, state-bearing attributes (role/type and
disabled/checked/expanded…), plus its visible text with volatile spans (timestamps,
clock times, UUIDs/long tokens, digit runs) masked. Every other attribute value —
`id`/`class`/`href`/`value`/`nonce`/`data-*` — and all volatile text is ignored, so
a session token, a clock, or a cart-badge counter never forks a state, while a
"Maintenance" vs. "Orders" heading or a changed state-bearing attribute does. The
scenarios pin both directions (volatile-only edits collapse; genuine differences
separate) and that the id is a deterministic 64-char hex digest. This is a first,
PR-tunable cut (§2e notes state-abstraction tuning takes real iteration).

`exploration_discovery.feature` (§2e) is the third slice — still pure logic —
answering "what can the explorer act on here?" without a new mechanism. It reuses
the §2c accessibility-tree signal, which already labels every node with a generic
ARIA role: `spoor/exploration/discovery.py:discover_actions` keeps the nodes whose
role is interactive (button/link/textbox/checkbox/menuitem/…) and that aren't
ignored, and reads each one's role, accessible name, and backend DOM node id into an
`ActionableElement`. The accessible name doubles as the label the safety gate (slice
1) classifies; the backend node id is the handle the later explorer loop uses to
locate the element. Document order and every interactive occurrence are preserved —
deduplication and driving the actions are the explorer loop's job, not this slice's.
An unnamed element (an icon-only button) is still a candidate, just with an empty
label. The role set is the same for every target (§0).

`exploration_control.feature` (§2e) is the fourth slice — still pure logic —
landing the **run-level controls** §2e treats as core safety, not optional
hardening: a run that can't be bounded or stopped is itself a reliability gap.
`spoor/exploration/control.py` holds a `RunBudget` (the user's hard bounds — max
states, max requests, max wall-clock seconds; each optional, each set bound
validated positive) and a `RunController` that tracks one run's consumption and
holds a thread-safe manual **kill switch**. `check()` returns a `StopDecision`
with a log-ready reason; the kill switch is checked before the budget, so a
stop-on-command is always reported as such, and each set budget dimension stops
the run the moment it's reached. Wall-clock time is read through an injectable
clock, so the time bound is exercised deterministically. The scenarios pin each
bound stopping the run at (and not before) its threshold, a within-bounds run
continuing, and — pinning the §2e non-negotiable that a run is always stoppable —
that the kill switch stops even an unbounded run and takes precedence over a
reached budget bound. The explorer loop that records progress and honours these
decisions is the next slice.

`exploration_loop.feature` (§2e) is the fifth slice — the **explorer loop** that
finally drives the gate, the state function, discovery, and the run controls
together — built logic-first in sub-slices (see the §2e decomposition note in
ROADMAP.md). This file covers **sub-slice 5a**: the pure-logic graph model
(`spoor/exploration/graph.py` — `ExplorationGraph`, nodes = states keyed by
`state_id` and carrying their discovered actions, edges = fired actions, plus a
separate record of gate-skipped actions) and the `explore` orchestrator
(`spoor/exploration/explorer.py`). `explore` walks a target depth-first with
**reset-and-replay** navigation (to revisit a state it resets the driver and
replays the path that first reached it, assuming no back button), discovering each
state's actions (slice 3), asking the safety gate which may be fired (slice 1),
recognising a revisited state by its `state_id` so the walk terminates instead of
looping (slice 2), and checking the run controller before every action so a budget
or the kill switch always stops it (slice 4). A destructive action on a non-sandbox
target is recorded as a skip and its state never reached — worst case "missed a
state", never "deleted real data". The browser sits behind a `BrowserDriver`
protocol, so the whole loop is exercised in-process against a fake deterministic
app; the scenarios pin mapping a two-state app, collapsing a revisited state to one
node, skipping-vs-firing a destructive action by sandbox status, and stopping on a
state budget or a thrown kill switch. The browser sits behind a `BrowserDriver`
protocol so the loop runs in-process against a fake; **sub-slice 5b**
(`exploration_browser.feature`) supplies the real one.

`exploration_browser.feature` (§2e) is **sub-slice 5b**: the real Playwright
`BrowserDriver` (`spoor/exploration/driver.py`) and the `spoor explore <url>`
command that drives the whole exploration stack in a headless Chromium against a
live site. The driver keeps one page open for the run, reads the accessibility tree
over CDP for discovery, and — because reset-and-replay reloads the page and every
DOM/accessibility node id changes — `perform` **re-locates** each element by its
accessibility role and name (Playwright's role locator, which auto-waits) rather
than by the captured backend node id, which is only meaningful within the snapshot
it was discovered in. `spoor explore` bounds the run with the same `RunBudget`
options as the loop, throws the kill switch on Ctrl-C (restoring the prior handler
afterwards), and prints a summary of states discovered / transitions / actions
skipped. The scenario drives real Chromium against a two-page loopback fixture
(Home ⇄ Next) and asserts the summary reports two states, two transitions, and zero
skips. Nothing in the driver is site-specific (§0). Per-transition signal capture
(screenshot / a11y / storage / HAR / console diffs) is sub-slice 5c.
`testgen.feature` (§2g) is listed in the table
above ahead of implementation; its feature file is authored when its phase begins
(see the Phase column).
