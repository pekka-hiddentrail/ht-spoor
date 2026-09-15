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
| `serving.feature` | Read-only serving of a captured map over a REST API (records + observed API surface + exploration graph, with freshness) | §2f | `spoor/serving` | 4 / 5 |
| `serving_mcp.feature` | Read-only serving of the same map over an MCP server (agent-facing tools; records, API surface, and exploration graph) | §2f | `spoor/serving` | 4 / 5 |
| `exploration_safety.feature` | Exploration safety gate: destructive actions are sandbox-only, non-configurable | §2e | `spoor/exploration`, `spoor/security` | 5 |
| `exploration_state.feature` | Exploration state abstraction: normalize + hash the DOM so equivalent screens share one state id | §2e | `spoor/exploration` | 5 |
| `exploration_discovery.feature` | Exploration element discovery: pull the interactive elements from the accessibility tree as candidate actions | §2e | `spoor/exploration` | 5 |
| `exploration_control.feature` | Exploration run-level controls: hard budget (states/requests/wall-clock) + manual kill switch | §2e | `spoor/exploration` | 5 |
| `exploration_loop.feature` | Exploration explorer loop: the state-action graph orchestrator tying together discovery, safety, state abstraction, and run controls | §2e | `spoor/exploration` | 5 |
| `exploration_browser.feature` | Exploration in a real browser: the `spoor explore` command drives the whole stack against a live site via a headless-Chromium driver, renders a wiki, and persists the graph for serving | §2e / §2f | `spoor/exploration`, `spoor/serving`, CLI | 5 |
| `exploration_signals.feature` | Exploration per-transition signal capture: a free-signal bundle per state and a before/after diff (a11y, console, storage, network, screenshot) per transition | §2e | `spoor/exploration` | 5 |
| `exploration_signals_live.feature` | Live per-transition signal capture: the real driver reads console, storage, network, a11y, and a screenshot hash from an actual Chromium page; a reset scopes the console/network buffers to the current visit (6d) | §2e | `spoor/exploration` | 5 |
| `exploration_wiki.feature` | Exploration wiki generation: render the state-action graph into a browsable static HTML site (index + Mermaid overview, one page per state/transition), with captured values redacted before rendering; state pages labelled by page title and repeated console/network lines collapsed with a count (6c), network requests grouped by kind (6d), and each state page leading with an Actions table of its elements (Label / Type / Screen capture / Destination) before the signals (6e), plus a help/glossary page linked from every page defining the terms used (6f), and a per-state full-page screenshot embedded as an image when opted in — pixel-free by default (8a) | §2e | `spoor/exploration` | 5 |
| `exploration_screenshots.feature` | Opt-in full-page screenshot capture and writing: the explorer stores a full-page image per discovered state into a caller-provided sink, and the wiki writer places each image under a `screenshots/` subfolder and embeds it; a default run captures no pixels and the wiki stays pixel-free, because pixels cannot be secret-redacted the way text is (§2h) — capture and embedding turn on only via the `spoor explore --screenshots` flag, which requires `--wiki` (8b) | §2e | `spoor/exploration`, CLI | 5 |
| `exploration_element_screenshots.feature` | Opt-in per-element screenshot capture and writing: the explorer clips one image per discovered actionable element (the "Next" button, the "Currency" dropdown) into a caller-provided sink, aligned by discovery position, and the wiki writer places each clip under the `screenshots/` subfolder and embeds it in that element's Actions-table row; a default run clips nothing and the wiki stays pixel-free, for the same §2h reason (pixels cannot be secret-redacted) (8d) | §2e | `spoor/exploration` | 5 |
| `exploration_actuation.feature` | Robust actuation, pure verdict: classify a discovered element's click point as ACTUATE / COVERED / NOT LOCATED (sub-slice 7a) | §2e | `spoor/exploration` | 5 |
| `exploration_actuation_live.feature` | Robust actuation, live driver: relocate via the CDP tree and click by a verified coordinate; detect a covered element without mis-clicking (sub-slice 7a) | §2e | `spoor/exploration` | 5 |
| `exploration_settling.feature` | State settling, pure quiescence policy: settle when DOM mutations go quiet for a window, report unsettled at a bounded timeout — under a fake clock (sub-slice 7b) | §2e | `spoor/exploration` | 5 |
| `exploration_settling_live.feature` | Settling + reset fidelity, live driver: reset clears cookies+storage for a true first visit, reads wait for real DOM quiescence, a never-quiet page is flagged unsettled not fatal (sub-slice 7b) | §2e | `spoor/exploration` | 5 |
| `exploration_recovery.feature` | Layer recovery: deal with a blocking layer as its own state and interact past it, safety-gated and progress-bounded, flagging when unresolved (sub-slice 7c) | §2e | `spoor/exploration` | 5 |
| `exploration_replay.feature` | Replay resilience: verify each reset-and-replay against the state ids it first reached and retry a transient bad render, flagging a persistently unreachable or divergent step honestly (sub-slice 7d) | §2e | `spoor/exploration` | 5 |
| `exploration_settling_network.feature` | Settling also waits for the network: treat the page as busy while a request is in flight so a late response can't render a different page after a read, bounded so a never-ending request is flagged unsettled not hung (sub-slice 7e) | §2e | `spoor/exploration` | 5 |
| `testgen.feature` | Test-automation run generation: the pure generator turns a §2e exploration graph into a pytest suite (one Playwright-driven regression test per mapped transition) — replay the path, fire the action, assert the recorded signals, with every captured value and the live observations redacted like-for-like (sub-slice 2g-i) | §2g | `spoor/testgen`, `spoor/security` | 6 |

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
never served. Both surfaces now also serve the **exploration graph**: `spoor explore`
records its state-action graph into the same map (`shareable_exploration_map` projects
it to §2h-shareable facts — per-state action inventory and signal *counts*, per-transition
what the action *changed*), a new `MapEntry.exploration` field carries it, and the one
`views.map_view` line that redacts it surfaces it on both `/map` and `get_map` — so an
agent can consult "what happens when I click X" as data, not just read the static wiki.

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
node, skipping-vs-firing a destructive action by sandbox status, stopping on a
state budget or a thrown kill switch, and — for robustness against a live, dynamic
target — recording a discovered action the driver **can't actuate** (a `perform`
that raises `ActionError`: the element is gone/hidden/covered by replay time) as a
skip and carrying on with the rest of the map rather than aborting the run. The
browser sits behind a `BrowserDriver` protocol so the loop runs in-process against a
fake; **sub-slice 5b** (`exploration_browser.feature`) supplies the real one.

`exploration_browser.feature` (§2e) is **sub-slice 5b**: the real Playwright
`BrowserDriver` (`spoor/exploration/driver.py`) and the `spoor explore <url>`
command that drives the whole exploration stack in a headless Chromium against a
live site. The driver keeps one page open for the run, reads the accessibility tree
over CDP for discovery, and — because reset-and-replay reloads the page and every
DOM/accessibility node id changes — `perform` **re-locates** each element in the live
CDP accessibility tree (robust actuation, sub-slice 7a, below) rather than by the
captured backend node id, which is only meaningful within the snapshot it was
discovered in. `spoor explore` bounds the run with the same `RunBudget`
options as the loop, throws the kill switch on Ctrl-C (restoring the prior handler
afterwards), and prints a summary of states discovered / transitions / actions
skipped. The first scenario drives real Chromium against a two-page loopback fixture
(Home ⇄ Next) and asserts the summary reports two states, two transitions, and zero
skips. A second scenario (**sub-slice 6b**) reruns the same live crawl with
`--wiki <dir>` and asserts the command reports where the wiki was written and
produces a complete browsable site — an index plus a page per state and per
transition — whose overview counts match the run. When `perform` re-locates an
element that's no longer actuatable it raises `ActionError`, which the loop records
as a skip so one dead element never crashes the run. Nothing in the driver is
site-specific (§0). Per-transition signal capture (screenshot / a11y / storage / HAR
/ console diffs) is sub-slice 5c.

`exploration_signals.feature` (§2e) is **sub-slice 5c** — per-transition signal
capture — built logic-first as **5c-i**. §2e records a free/near-free signal bundle
for every transition (the accessibility snapshot, console output, client-side
storage, the network/HAR trace, and a screenshot) so the map can answer "what
happens, on every signal level, when I press this button". This slice is the pure
model behind that: `spoor/exploration/capture.py` holds `StateSignals` (the bundle
captured at one state — a11y node count, console messages, storage keys, network
requests, screenshot hash) and `diff_signals`, which computes a `TransitionSignals`
before/after diff (what console/storage/network entries appeared, what storage was
removed, the signed a11y-node delta, and whether the screenshot changed). The graph
now carries a bundle on every state node and a diff on every transition, and the
`explore` orchestrator captures the bundle either side of each fired action through a
new `capture_signals()` seam on the `BrowserDriver` protocol. It runs in-process
against the fake driver; the scenarios pin the full diff of a signal-changing action,
an honest empty diff when an action changes nothing, storage keys removed as well as
added, and each state node carrying the bundle captured there. `exploration_signals_live.feature` (§2e)
is **sub-slice 5c-ii**: filling that bundle from a real page. `PlaywrightDriver`
now reads all five §2e free signals from live Chromium — the CDP accessibility-node
count, the console messages and network requests accumulated by page listeners
attached at launch (so a transition's diff is exactly the slice between its
before/after snapshots, correct even under reset-and-replay's reloads), the current
`localStorage`+`sessionStorage` keys, and a **perceptual (dHash) hash of a
screenshot**, reusing the tier-3 visual hasher (`spoor/core/visual.py`) so a
transition is flagged as changing the screenshot only on a real visual change, not
on anti-aliasing noise. Every signal is opportunistic — one that can't be read is
recorded empty rather than failing the run. Its scenarios drive the real driver
against a signal-rich loopback fixture (a page that logs, writes storage, fetches,
and navigates to a visually-distinct second page) and assert both the captured
bundle and a real click's diff. The signals attach to the graph on every `spoor
explore` run; rendering them per node and edge is the wiki (slice 6).

`exploration_wiki.feature` (§2e) is **slice 6a** — the pure wiki renderer that turns
the explored graph into §2e's real product: a browsable static site. `spoor/exploration/wiki.py`
renders an `ExplorationGraph` into a set of HTML pages — an index with run counts and
a **Mermaid** graph overview, one page per state showing the free-signal bundle
captured there (a11y node count, console messages, storage keys, network requests,
screenshot hash), and one page per transition showing what its action changed (the
before/after diff). It is a self-contained Jinja2 renderer chosen over reusing a full
site generator like MkDocs/Docusaurus (see the §2e slice-6a decision note); Mermaid is
loaded from a CDN by the index, so the pages themselves read offline and only the
overview *diagram* needs the network. Screenshots are hash-only for now — a transition
reports whether the screenshot *changed*, no images are embedded. Because the wiki is a
shared-output surface, every captured value it renders is passed through the §2h
redaction primitive before rendering, and every template autoescapes, so an injected
`<script>` becomes inert text; the scenarios pin the structure (index + a page per
state and per transition, links, overview), each page's bundle/diff, and that a
console-logged bearer token never appears raw. `build_pages(graph, target)` is pure
(no disk), with `render_wiki(...)` the thin writer around it. **Slice 6b** then wires
it to the CLI — `spoor explore --wiki <dir>` renders the mapped graph to a browsable
site after the crawl and reports its `index.html` — pinned live in
`exploration_browser.feature`, and proven against the real archetype bench by a
reliability integration test (`tests/test_integration_wiki.py`) that crawls Juice
Shop under a small budget and asserts a complete, internally
consistent wiki is produced every run (a page per state and per transition, index
counts and links matching the graph, well-formed HTML). Surfacing the live crawl's
un-actuatable elements as skips (the loop's `ActionError` path) rather than a crash
is what makes that reliability hold against a dynamic SPA.

**Slice 6c** then sharpens the state pages, after a live PrestaShop run showed them
barely readable: a state was labelled only by its opaque 64-char hash, and its console
and network signals repeated the same line many times over (one real page carried 105
identical console lines and thousands of repeated request URLs). So a state now carries
its captured **page title** as a human-readable label (on its own page, in the index
lists, and in the Mermaid overview), falling back to the short id when the page has no
title; and a state page **collapses repeated console/network lines** into one row with
an "× count". Transition pages already show a first-seen-deduplicated diff, so they are
unchanged. Embedding the screenshot image (rather than a hash) stays deferred: string
redaction can't scrub a secret that is *visible on the page*, so pasting a screenshot
into shared output would bypass the redaction every other signal goes through — that
needs its own treatment.

**Slice 6d** carries the same thread two steps further. A state page now **groups its
network requests by kind** — Documents, Scripts, Styles, Images, Fonts, Media, Data,
Other — with a per-group count, instead of one flat list, so a reader sees what the
page loaded at a glance. The kind is a URL-only heuristic (file extension, or an
`/api/` path for data): Spoor captures request URLs, not response content-types, so
it is best-effort but needs no new capture and stays generic across every target. And
the console/network buffers are now **scoped per visit** — the driver clears them on
each reset, so a state reflects only the walk that reached it, not the whole run's
cumulative output (6c's collapse hid that duplication; 6d removes its source). This is
safe for transition diffs, which straddle a single action with no reset between their
two captures. (A request *timeline* was considered but not built: ordering needs
per-request capture timestamps the bundle doesn't carry, so categorization shipped.)

**Slice 6e** rearranges the state page to lead with its **actionable elements**. The
old "Actions here" bullet list and the separate "Outgoing transitions" list are
replaced by a single **Actions table** — one row per discovered element, columns
*Label*, *Type*, *Screen capture*, and *Destination / target state* — placed
immediately after the state-identity block (label, id, settle) and ahead of the
captured-signal sections, so the thing a reader acts on comes first. The destination
cell folds in what the outgoing list carried: when an element was fired and produced a
transition it links to that transition page, labelled by the target state; otherwise it
reads "none". The screen-capture column reserved here reads "none" until slice 8d, which
fills it with a per-element clip when element screenshots are opted in (otherwise it
stays "none", honest about there being nothing to show). Purely a presentation change;
the graph and its §2h redaction are untouched, and it stays generic across every
target (§0).

**Slice 6f** adds a **help/glossary page** linked from every page's nav. It is a fixed,
target-independent glossary written in plain language for a reader who did not build
Spoor, defining every term the other pages use — state, transition, accessibility nodes,
console messages, storage keys (added/removed), network requests, screenshot hash, the
"did not settle" warning, skipped actions, and the `[REDACTED]` placeholder. It carries
no captured values, so nothing on it needs redaction, and being identical for every
target it holds nothing site-specific (§0). The scenarios pin that the page exists,
defines its terms as glossary entries, and is reachable from every page.

**Slice 8a** begins embedding **screenshots** in the wiki (the "Visual capture" backlog
item), staged and opt-in. The pure renderer learns to embed a per-state **full-page
screenshot** as an `<img>` referenced by the relative path `screenshots/state-{index}.png`,
leading the state page as its visual identity ahead of the Actions table, when
`build_pages` is told (via a `screenshots` set of state ids) that a state has one.
`screenshots` defaults to none, so a default wiki stays **pixel-free** — because a
screenshot is pixels, not text, it cannot be secret-redacted the way every other signal
is (§2h), so pixels are embedded only behind an explicit opt-in. Capturing the image
bytes and the CLI opt-in flag are slice 8b; the scenarios here pin that a marked
state embeds its image before the Actions table, an unmarked state embeds none, and a
default wiki embeds no screenshots at all.

`exploration_screenshots.feature` (§2e) is **slice 8b** — the capture-and-write half.
`PlaywrightDriver.screenshot()` returns a full-page PNG (`page.screenshot(full_page=True)`,
or `None` if it can't be captured); `explore(..., screenshots=<sink>)` stores one image
per discovered state into a caller-provided mapping, and `render_wiki(..., screenshots=
<state-id→bytes>)` writes each `screenshots/state-{index}.png` (grouped in its own
subfolder, not flat beside the pages — slice 8c) and hands the captured ids to
`build_pages` to embed them. Capture is opt-in by the *presence* of the sink,
gated behind a separate `@runtime_checkable` `_ScreenshotCapable` protocol so the core
`BrowserDriver` contract and every existing fake driver stay untouched; a default run
passes no sink and captures nothing. The `spoor explore --screenshots` flag turns both
capture and embedding on (off by default) and is rejected without `--wiki`, since there
is nowhere to put the images. The in-process scenarios pin capture-on/off and
write-and-embed/pixel-free with a fake app and fake PNG bytes; a live integration test
(`tests/test_integration_wiki.py`) proves real full-page PNG bytes and end-to-end
embedding against the bench, and that a default crawl leaves the wiki pixel-free.

**Slice 8c** groups the screenshot images into their own `screenshots/` subfolder
(`_screenshot_filename` → `screenshots/state-{index}.png`) instead of writing them flat
beside the HTML pages, so the wiki directory stays readable as the page set grows — the
first step of stage 4 of the slice-8 plan ("place all captures into the wiki in an
understandable layout"). The pages embed each image by that subfolder-relative path;
`exploration_screenshots.feature` gained a scenario pinning that the image lands under
`screenshots/` and that nothing sits flat in the root. A presentation-only change: the
opt-in, the redaction posture, and the capture path are untouched, and it stays generic
across every target (§0).

`exploration_element_screenshots.feature` (§2e) is **slice 8d** — per-element capture,
which finally fills the Actions table's long-reserved Screen-capture column (6e).
`explore(..., element_screenshots=<sink>)` clips one image per discovered element into a
caller-provided mapping (keyed by state id, one `ElementShot` per element in discovery
order), gated behind a new `_ElementScreenshotCapable` protocol exactly like 8b's
full-page sink, so a default run and every fake stay untouched.
`PlaywrightDriver.element_screenshot` re-locates the element through the same
`find_target` path actuation uses, reads its box over CDP, and crops it;
`render_wiki(..., element_screenshots=…)` writes each clip to
`screenshots/state-{i}-el-{e}.png` and embeds it in that element's row (or leaves
"none"). Pixel-free by default and opt-in for the same §2h reason as every screenshot.
The in-process scenarios pin capture on/off, per-row embedding, the subfolder, and
pixel-free-by-default; unit tests pin position-alignment with a `None` clip mid-list; a
live integration test clips real element PNGs against the bench. Capturing an element's
*opened contents* (open a dropdown, screenshot the overlay) is the follow-up, slice 8e.

`exploration_actuation.feature` + `exploration_actuation_live.feature` (§2e) are
**sub-slice 7a** — robust actuation. A live diagnostic showed the explorer's skips on
a real SPA were not overlay interception but a *relocation* failure: discovery reads an
element from the CDP accessibility tree, while the old `perform` re-found it through
Playwright's separate ARIA-name engine, so the two computed accessible names
differently and a visible, uncovered element could match nothing and be skipped. 7a
removes the divergence. `spoor/exploration/actuation.py` holds the pure verdict —
`classify` returns ACTUATE / COVERED / NOT LOCATED — and `find_target`, which relocates
by running `discover_actions` *itself*, so act-time and discovery-time matching cannot
drift. `PlaywrightDriver.perform` re-reads the live tree, resolves the node over CDP
(`DOM.resolveNode`), and runs scroll-into-view + box-centre + `elementFromPoint` in one
call (so the point it verifies is the point it clicks), then clicks by coordinate with
Playwright's trusted, CDP-backed mouse — identical headless or headed. COVERED raises
`ElementCovered(role, text)` (carrying the layer, for recovery in 7c) and NOT LOCATED
raises `ElementNotLocated`; both subclass `ActionError`, so the loop still records
either as a skip until 7c. The context runs at a pinned 1280×800 viewport (device-scale
1) so every computed coordinate is reproducible. The pure feature pins the verdict
browser-free; the live feature drives real Chromium against a loopback fixture — an
aria-label-only icon button is clicked, a below-the-fold button is scrolled into view
and clicked, a covered button is reported covered *without activating the overlay*, and
the viewport is fixed. First-cut limitations recorded honestly: duplicate role+name
acts on the first in document order, and an iframe-hosted element is out of the top
document's `elementFromPoint` reach. Nothing is site-specific (§0). Settling (7b, below)
and layer recovery (7c, `exploration_recovery.feature`) are the following sub-slices.

`exploration_settling.feature` + `exploration_settling_live.feature` (§2e) are
**sub-slice 7b** — state settling and reset fidelity, specifically the **DOM-quiescence
half** of the settling rule. The same diagnostic showed 7a's
robust actuation was necessary but not sufficient: the map stayed shallow because the
page discovered was not the page acted on. Two coupled defects. First, **no settling** —
discovery and actuation happened at different rendering instants, so on an asynchronously
rendered SPA an element present at discovery time was gone by click time. 7b waits for a
*real* rendering-stopped signal: `spoor/exploration/settling.py:wait_for_quiescence`
settles once a monotonic DOM-mutation count holds steady for a quiet window and reports
**unsettled** at a bounded safety timeout, driven by an injectable clock/sleep (the
`RunController` seam) so the pure feature exercises it with no browser. The live driver
feeds it a real `MutationObserver` counter (installed on every document via
`add_init_script`) and waits after each reset and each click, so reads and post-action
returns see the settled page; a page that never quiesces is captured with a
`settled=False` flag (shown in the wiki as "Did not settle") and the run proceeds on the
last snapshot rather than hanging or crashing. Second, **reset didn't reset the app** —
a persistent browser context carried cookies and storage across navigations, so replay
landed on a returning-visitor render. 7b's `reset` clears cookies and both web-storage
areas before navigating (one context kept; only per-origin state wiped) and waits on
quiescence instead of `networkidle` (removing a crash when that signal never arrived), so
every reset is a true first visit. The live feature pins all three 7b behaviours against
loopback fixtures (reset restores first-visit content, a timer-delayed DOM mutation is
discovered, and a forever-mutating page is flagged unsettled not fatal); the browser-free
driver tests pin the post-click settle poll and the cookie/storage clear under a fake
clock. Sub-slice 7e below layers the **network-in-flight** half on top of this same wait,
covering pages whose late render is driven by a request that is still outstanding even
while the DOM is briefly quiet. Nothing is site-specific (§0): one quiescence rule and
one reset for every target.

`exploration_recovery.feature` (§2e) is **sub-slice 7c** — layer recovery. The same
diagnostic that motivated 7a/7b showed the dominant coverage limiter was neither timing
nor relocation but *interception*: a welcome dialog or consent overlay sits over every
click, so the map collapses to the first screen. 7c teaches the explorer to treat a
blocking layer as its own state and interact past it. A new `BrowserDriver.probe` returns
the actuation verdict without clicking (in `PlaywrightDriver`, sharing one `_actuation`
computation with `perform`, so probe and click can't diverge); when `reach` probes
COVERED, it fires the layer's own on-top actions — the discovered actions that themselves
probe ACTUATE, gate-permitted, each tried once — re-probing the target until it clears,
advances, or uncovers, bounded by the finite action set so it never loops. Recovery runs
inside replay too, so a covered state stays reachable on every reset-and-replay. The §2e
non-negotiable holds: a layer whose only exit is destructive stays blocked outside a
sandbox (flagged `blocked by an unresolved layer`, the destructive action recorded as a
skip), and a genuinely missing element is flagged `not located`, never mistaken for a
blocker. Recovered edges are marked (`Transition.recovered_via`) and shown in the wiki.
The pure scenarios pin blocker-cleared, multi-step, destructive-only-exit, unresolvable,
and missing-vs-covered; the live scenario maps `fixtures/static/explore_gated.html` (a
full-viewport consent overlay) and asserts the site behind it is reached with ≥1 action
recovered. Coordinate-level brute-forcing of a layer with no discoverable clearing action
is deferred — such a layer is flagged blocked, not forced. Nothing is site-specific (§0).

`exploration_replay.feature` (§2e) is **sub-slice 7d** — replay resilience. A follow-on
diagnostic showed 7b's settling did not fully cure the nondeterminism: under load the same
reset still intermittently lands on a *degraded* render (Angular's "Force page reload"
fallback), so a step found on the first visit can be gone by the time reset-and-replay
returns to it — and because replay was all-or-nothing, one flaky step killed the whole
subtree behind it, with the skip mis-attributed to the leaf. 7d makes replay resilient and
honest. The replay path now carries the state id each step first reached, so every
reset-and-replay is *verified*: the post-reset page must be the start state and each
replayed step must land on the id it first mapped to, or the attempt is *retried* a bounded
number of times — a transient bad render usually clears on the next reset, regaining
coverage. When retries are exhausted the action is flagged with a reason that tells a step
that stayed unreachable (`replay could not reach …`) apart from one that *diverged* to
another state (`replay diverged: …`), never a mute skip and attributed to the replay step
that failed, not the leaf; a stably blocked layer (7c) is reported at once, not retried.
The pure scenarios pin a transient miss retried, a persistent miss flagged unreachable, a
divergence flagged, and a transient divergence retried; the live scenario drives the real
stack against a scripted server whose entry page is degraded on exactly one reset and
asserts the page behind it is still mapped. Nothing is site-specific (§0).

`exploration_settling_network.feature` (§2e) is **sub-slice 7e** — settling also waits
for the network. Running exploration against the server-rendered PrestaShop bench (§5.1)
exposed a gap 7b's DOM-only quiescence left: on a listing page a hydration lull longer
than the quiet window opens while an AJAX widget and lazy-loaded images are still in
flight, so DOM-quiet settles *too early* and a late burst of network responses then
mutates the DOM — two captures of the same screen hash to different state ids and 7d
flags a spurious divergence, skipping the action. The measured cost was 6 states, 32
transitions, and 17 skips, every skip a divergence on an ever-present menu link. 7e
widens the quiet signal: `wait_for_quiescence` gained an optional `busy` predicate, and
the page counts as quiet only while `busy()` is false *and* mutations have held steady
for the window, so a late response that will still mutate the DOM can't be settled past.
The live driver counts in-flight requests (up on `request`, down on
`requestfinished`/`requestfailed`, floored at zero and zeroed before each awaited
navigation/click) and passes `busy=lambda: self._inflight > 0`. The bound is unchanged
and symmetric with 7b: a request that never completes flags the page unsettled at the
timeout, never hangs. The pure scenarios pin an in-flight request holding the page
unsettled until it completes and a never-completing request reported unsettled at the
timeout; the live scenario serves a page that fetches a fragment the server delays past
the quiet window and asserts the fetched button is discovered (DOM-quiet alone would miss
it). Re-running against PrestaShop with 7e gave 7 states, 40 transitions, and 0 skips —
the 17 divergences gone and coverage up. Nothing is site-specific (§0).

`testgen.feature` (§2g) is **sub-slice 2g-i** — the pure test generator, built
logic-first like the wiki renderer (6a): `build_tests(graph, target)` maps a §2e
exploration graph to pytest test *sources* (filename → code) with no browser and no
disk, so it is fully specifiable in-process. Per mapped transition it emits a
`test_transition_N.py` that (via a shared `_spoor_testkit.py` and a `conftest.py`)
drives Playwright to replay the reset-and-replay path that reached the transition's
from-state — reconstructed by walking the recorded edges from the root — fire the
action, and assert the additive signals the transition was recorded to add (console
lines, storage keys, request URLs) still appear: a real regression test the consuming
team runs against the live product, not a check of the map's own consistency. Because a
generated test is a shared-output surface, §2h redaction is mandatory on every captured
value baked in; and — unique to test generation — the emitted suite redacts the *live*
values it observes with Spoor's own primitive before comparing, so both sides match
like-for-like and no raw secret is ever the expected literal (which is why running the
generated suite depends on `ht-spoor` and `playwright`). Only the additive string
signals are asserted; the a11y-node delta and screenshot hash are deferred, and a graph
with no transitions generates no tests. Nothing is site-specific (§0). Wiring the suite
to a command and proving it runs green against a live fixture is sub-slice 2g-ii (see
the Phase column).
