# Spoor — Project Plan

> **Give your agents a map of the web.**
> Spoor is a local-first crawler that escalates from selectors to browser and visual interaction only when needed — then exposes the discovered behavior through MCP or API.
>
> **Local-first. MCP-ready. LLM optional.**

*A local-first web scraping stack that escalates through four UI tiers — fast selectors, JS-rendered selectors, visual/fingerprint healing, and human-like interaction — while passively building a map of the target's underlying API surface and a broader catalog of client-side signals (storage, console, performance, real-time traffic, and more), using existing open-source components wherever possible and LLM calls only as an optional, off-by-default last resort. A second mode (§2e, v2) turns the same machinery outward: autonomously explore every interaction a product supports and generate a browsable wiki of what happens, on every signal level, for each one — served live to agents via §2f, not just written to static files.*

**Scope note:** Windows native apps, mobile emulators, and remote mobile device farms were considered and explicitly deferred (see the cost/complexity breakdown from planning discussion — each needs a genuinely different automation stack, roughly 2–4 extra weeks apiece, and remote device farms specifically require a whole separate Appium backend since they don't expose raw ADB). Current scope is **web UI + the API surface reachable from a browser session**, nothing else.

**On the words "map" (hero sentence) and "full picture" (§2b): both mean *as complete as what Spoor has actually observed or been asked to explore*, never a guaranteed-exhaustive census of the target.** GraphQL introspection can be disabled, official spec discovery can fail to find anything, and passive traffic capture only ever sees endpoints a run actually happened to exercise. This is a documentation commitment, not just an internal caveat — user-facing copy should say "a map of what's been explored," never imply completeness it can't back up. See §2b and §2e for exactly where the boundedness comes from.

## 0. Design principle: general-purpose, never site-tailored

Everything in this plan — the four tiers, API surface discovery, the signals catalog — has to work on a target the tool has never seen before, using only what it can observe or learn at runtime. Nothing in the core is allowed to hardcode knowledge of a specific website: no `if domain == "..."` branches, no selectors or endpoint paths written against one named site, no logic that only makes sense for one target.

Two things that look like exceptions but aren't:
- **The per-domain cache** (§2, "which tier worked last for this domain") is fine — it's runtime-*learned* behavior, discovered generically the same way for every target, not hardcoded knowledge of any one site.
- **Platform-convention recognizers** (e.g. "this looks like a Shopify store, so try `/products.json`") are fine *as a pluggable, opt-in table of known platform conventions* — they generalize across every store built on that platform, not one company's site. They should live as a separate, swappable "recognizers" list the core dispatcher consults, never as logic baked into the escalation path itself.

Test fixtures (§5) are the opposite of integrations: OWASP Juice Shop, Sauce Demo, a self-hosted ERPNext/Odoo, and a self-hosted Netflix-clone exist purely to prove the generic tiers hold up across different architectural shapes (security-flavored webshop, clean webshop, auth-gated internal business app, heavy media SPA). If a fixture only passes with a special-case added for it, that's a signal the general mechanism (a tier's threshold, a selector strategy, a validation schema) isn't general enough yet — not a reason to add an exception for that fixture.

## 1. Why this project, given the landscape

Crawl4AI, browser-use, and Skyvern already do a lot of "smart scraping," but all three are built LLM-first: the model is in the loop for most decisions, which means API cost, latency, non-determinism, and a hard dependency on a cloud provider (or a beefy local model) for basic runs.

The gap this project fills is a **local-first, deterministic-by-default** stack: it runs entirely on the user's machine with no API key required, uses classical techniques (DOM fingerprinting, perceptual-hash/template matching, scored similarity) for resilience instead of a model call, and only *optionally* lets someone wire in an LLM or local vision-language model (e.g. via Ollama) for the small residue of cases nothing else can resolve. That's a genuine, defensible niche rather than a re-run of what's already popular — worth stating explicitly in the README so it's clear this isn't "another Crawl4AI."

**Who this is actually for.** Two audiences, deliberately, not one at the expense of the other: Hidden Trail's own internal use (feeding a mapped product's behavior into HT's LLM/agent workflows via §2f, and generating test automation runs from a captured map — see §2g), and an open-source release for anyone else who wants to scrape a system or turn it into a wiki. The two aren't in tension as long as §0's no-tailoring rule holds — HT's own usage is just the first, most demanding user of the same generic tool everyone else gets, not a special internal fork.

**Not an "agent."** Deliberately avoiding that framing: Spoor doesn't decide on its own what's interesting enough to look at more closely, or make autonomous judgment calls about a target. It records exactly as much as it's told to — via config (§2a), via the signal-tier flags (§2c/§2d), via an explicit exploration request (§2e). Anywhere this plan previously described a "heuristic decides" or "flags as interesting" behavior, read that as "matches an explicit, user-set rule," not the system exercising independent judgment — see the correction in §2e.

**Reliability is the one thing this cannot compromise on.** The whole product lives or dies on not being flaky. A scraper that sometimes finds the button and sometimes doesn't is worse than useless — it's actively misleading, whether a human is reading the output or an agent is acting on it via §2f/§2g. This makes tier 3 (§2, self-healing) the highest-priority piece of engineering in the entire plan, not just "the hardest part" — see §5's expanded test bench, built specifically to hold this to an honest, measured standard rather than a marketing claim.

## 2. Architecture: resolving a target vs. executing an interaction

Two separable concerns were previously described as one four-step ladder, which blurs a real distinction worth splitting out explicitly:

- **Resolution (tiers 1–3, escalating): finding the right element or piece of data on the page.** One Playwright session per job carries a request through up to three resolution tiers. Each tier validates its result against a schema before deciding whether to escalate; a small local cache remembers which tier last worked for a given domain/page-template so routine runs skip straight to it.
- **Interaction execution (a separate axis, not a fourth resolution tier): once a target is resolved, how the click/scroll/drag/type actually gets carried out.** This is a two-way choice — native/instant (Playwright's default primitives) or human-like/jittered (the Bezier-curve wrapper) — picked per-run or per-target, not escalated through in sequence the way resolution is.
- **Tier 3.5 (optional AI fallback)** extends the *resolution* ladder only — it helps find the right element when tier 3 can't, and never decides how to act on it.

| Tier | Purpose | What to depend on (not build) | LLM involved? |
|---|---|---|---|
| 1 (resolution) | Fast selectors, no browser | `httpx` + `parsel` (or Crawlee's `HttpCrawler`) | No |
| 2 (resolution) | JS-rendered pages, same selectors | Crawlee for Python's `AdaptivePlaywrightCrawler` — already auto-detects when JS rendering is needed and learns per URL pattern | No |
| 3 (resolution) | Selector broke / needs resilience | Reimplement or adapt **Healenium's core scoring algorithm** (Apache-2.0, *not* the commercial "Pro" tier) — DOM fingerprint + attribute similarity + perceptual-hash on a cropped screenshot, no model call | No (by design) |
| 3.5 (resolution, optional) | Last resort when tier 3 truly can't resolve an element | Pluggable interface — user can wire in Claude/GPT vision **or** a local VLM via Ollama (e.g. Moondream) | Optional, disabled by default |
| Interaction execution | Carrying out the resolved action: click, scroll, drag, hover, type | Playwright's native mouse/keyboard primitives; optionally wrapped with a small Bezier-curve jitter layer (the published `ghost-cursor` algorithm is easy to port; no need for the original Node library) for human-like mode | No |

The only substantial code this project actually writes is the **escalation dispatcher** (tries resolution tiers in order, validates, caches the winner per domain), the **per-tier adapters** gluing the above libraries into one consistent interface, and the **interaction executor** — a separate, much smaller piece of code that just carries out an already-resolved action, natively or jittered. Keeping these as two clearly distinct pieces (rather than one four-step list) is also what makes §2e's exploration mode make sense: it barely touches the resolution machinery at all (it discovers actionable elements directly via the accessibility tree, not via selectors), but uses the interaction executor for every single step. That keeps the "reinvent everything" surface small even with all resolution tiers in v1.

**Tier 3's uncertain-match handling (reliability-first, per §1).** When tier 3's confidence score falls below a defined "safe to auto-resolve" threshold but above zero — it found *a* plausible candidate, just not a confident one — the default is to flag it for manual review rather than silently guessing, surfaced in the run summary (§2d) as an "uncertain match" the user can approve, reject, or correct. Every tier-3 resolution, confident or not, logs its winning candidate's confidence score plus the runner-up candidates it considered — so "why did it heal to this element" is always answerable from that log, as a direct corollary of scored matching rather than a separately bolted-on feature.

## 2a. The user-facing interface: declarative extraction configs

**Two distinct modes, not two more rungs on the same ladder.** §2a and §2e are easy to conflate — both walk pages, both mention "signals" — but they're different operating modes with very different cost profiles, not points on one escalation path. §2a (this section) is **cheap and targeted**: extract named fields from a target whose shape you already know; one run costs roughly what the resolution tiers cost per configured field. §2e is **heavy and exploratory**: discover and traverse a target's entire actionable surface with no prior config, capturing a full signal bundle at every step; a run's cost is proportional to the size of the whole state graph, not one field. Use §2a when you know what you want; use §2e when you want to find out what's there.

Everything so far is internals. There's a gap worth closing: how does someone actually *tell* the tool what to extract? The answer that keeps the "essential, not tailored" principle intact is a declarative config file, not per-target Python — the schema shape is identical for every target, so pointing the tool at a new site is writing a new config, never new code:

```yaml
target: https://example.com/products
fields:
  title: { selector: "h1.product-title" }
  price: { selector: ".price", type: number }
  availability: { selector: ".stock-status" }
pagination:
  next: "a.next-page"
```

Each field's `selector` is just the tier-1 starting point — the escalation dispatcher (§2) still walks it through tiers 2–4 automatically if tier 1 fails, so the config author never writes tier-specific logic. `pagination.next` (or an `infinite_scroll: true` flag) tells tier 4 when to keep going and, just as importantly, when to stop. A thin CLI (`spoor run config.yaml -o output.json`) is the whole product surface on top of this — config in, structured data out.

**Single record vs. repeating records (decided).** The example above extracts one record per page (the fields resolve against the whole document). The far more common scraping shape — a listing page with many rows — is expressed by one optional key, `item`, a root selector that matches each repeating record; when present, every field's `selector` is resolved *relative to* each matched `item` element, and the run emits one output record per match instead of one per page. When `item` is absent, behavior is exactly the single-record case above (fields resolved against the whole document), so existing single-record configs are unaffected. This composes with pagination the obvious way: for each page, extract all `item` matches, then follow `pagination.next`. The `item` selector is itself just a tier-1 starting point, escalated the same as any field selector — the config author still never writes tier-specific logic. Example:

```yaml
target: https://example.com/products
item: "li.product-card"          # one output record per match
fields:
  title: { selector: "h2.title" }      # resolved within each product-card
  price: { selector: ".price", type: number }
pagination:
  next: "a.next-page"
```

## 2b. API surface discovery (runs alongside the UI tiers, not a separate crawl)

The goal here isn't just "find some API calls" — it's building up, over time, as complete a picture as can honestly be observed of what a product's API surface is and how the UI actually uses it. **Bounded claim, stated plainly:** this is inference from what was exercised, not guaranteed-exhaustive discovery — official spec discovery (layer 1) is authoritative when it succeeds, but GraphQL introspection can be disabled, and layers 3–5 only ever see endpoints a run actually happened to trigger. Spoor's API surface report means "everything observed so far," not "everything that exists" — worth stating exactly that way in user-facing docs, never softened into "the entire API surface." That decomposes into four layers, ordered cheapest/most-certain first:

1. **Official spec discovery (near-free).** Before anything else, probe a short list of conventional paths (`/openapi.json`, `/swagger.json`, `/api-docs`, `/.well-known/openapi.json`) and scan page HTML/JS bundles for references to one. If a real OpenAPI/Swagger doc exists, use it directly — no reverse-engineering needed, and it's authoritative.
2. **GraphQL introspection (also near-free, when available).** If a `/graphql`-shaped endpoint turns up, a single standard introspection query returns the entire schema. Many production APIs disable introspection deliberately, so this is opportunistic, not guaranteed.
3. **Passive traffic capture as a side effect of every tier 1–2 run.** Since the whole stack already drives real browser sessions via Playwright, network capture is nearly free: Playwright can record a HAR file natively for any context (`record_har_path`), with no separate proxy or CA-certificate install needed (that hassle only matters for non-browser traffic, which is out of scope now). Every scraping run silently accumulates the real requests the UI actually made.
4. **Spec synthesis from accumulated captures — needs answering before Phase 2.5, see §9.** Plainly: once Spoor has recorded a pile of raw API calls (from step 3), something has to turn that pile into an actual readable API spec — recognizing that `/users/1`, `/users/2`, `/users/3` are really "the same endpoint, `/users/{id}`, with different IDs," and writing that out as an OpenAPI document. The open-source **mitmproxy2swagger** project already does exactly this clustering/inference. The open question is purely mechanical: mitmproxy2swagger expects its input in mitmproxy's own "flow" file format, not the HAR format Playwright natively produces (§2b step 3) — so it's unconfirmed whether HAR can be fed into it directly or converted cleanly (mitmproxy itself gained HAR support in version 10.1, which may bridge the two formats, but that hasn't been verified against this actual tool). This needs a short hands-on spike — try feeding it a real HAR file — before Phase 2.5 is scoped for real; if it doesn't work cleanly, the fallback is writing the same clustering logic directly against HAR, which is a well-understood, bounded piece of work either way.
5. **Action-to-endpoint correlation — the one genuinely custom piece.** None of the above tools tell you *which UI action triggered which API call*, and that's the "find the use of those APIs" part of the ask. This just needs a lightweight checkpoint log: before each simulated action (click, scroll, form submit), mark a timestamp; afterward, attribute any requests captured in that window to that action. Over many runs this turns a flat list of endpoints into "here's what this endpoint is *for*." **This is an approximation, not exact causal attribution** — background polling, prefetch requests, or analytics beacons that happen to fire inside the same window get attributed to the action too. Read any single correlation as "likely caused by," not proven; over many runs the noise mostly averages out, but the map should never claim exact click-to-call certainty.

None of this needs an LLM or a new dependency beyond mitmproxy2swagger (MIT-licensed) — it's a natural, nearly-free companion to tiers 1–2 rather than a fifth automation surface. **On relying on the synthesized spec:** treat it as a strong starting point for understanding a product's surface, not a guaranteed-accurate contract — always verify before building anything (a test, an integration) that depends on it being complete or correct.

## 2c. Additional signals catalog

Beyond DOM/selectors and the API surface, a Playwright session already sits in a position to observe a lot more about a product with little or no extra machinery. Grouped by cost, so it's clear what's "on by default" vs. opt-in:

**Free / near-free — capture these by default alongside the HAR file (Phase 2.5):**
- **Client-side storage**: `localStorage`, `sessionStorage`, IndexedDB, cookies via `context.storage_state()` — often reveals feature flags, cached responses, and auth tokens never visible in the DOM.
- **Console output & JS errors**: `page.on("console")` / `page.on("pageerror")` — developers leak surprisingly informative debug output and stack traces in production more often than expected.
- **Accessibility tree**: `page.accessibility.snapshot()` — a structural view independent of visual markup; doubles as a resilience signal for tiers 1/3, not just extra data.
- **Response headers**: CSP, CORS, server/infra headers — cheap fingerprint of backend tech and security posture, already flowing through the HAR capture.

**Cheap — a bit of CDP wiring, still no new dependency:**
- **WebSocket / SSE frames**: `page.on("websocket")` — HAR-based capture misses push-based traffic entirely (chat, live dashboards, trading UIs), so this matters a lot for real-time products.
- **Performance metrics**: CDP `Performance.getMetrics` — JS heap size, DOM node count, layout/recalc counts; useful for spotting unusually heavy pages or regressions across versions.
- **Service worker cache contents**: reveals what the app pre-caches, i.e. what it expects to need.
- **Third-party script inventory**: analytics/support/payment scripts loaded — a fingerprint of what vendors the product integrates with.
- **Computed styles**: sampled across elements, can reconstruct a design system (color/spacing/type tokens) when that's relevant.

**Expensive or invasive — opt-in flags, never part of a default run:**
- **Full session video recording** (`record_video_dir`) — great for human review or eval/training data, but storage-heavy; enable per-run, not per-default.
- **JS heap snapshots** (CDP `HeapProfiler`) — can surface in-memory app state (e.g. a Redux/Vuex store) that never gets serialized to the DOM or network, but it's slow and heavy; treat as an occasional deep-dive tool.
- **Media manifest / streaming capture**: `<video>`/`<audio>` element state (`currentTime`, `buffered`) plus HLS/DASH manifest requests — only relevant if the target is actually a media/streaming product.
- **Canvas/WebGL pixel capture**: the fallback of last resort for canvas-rendered UI (games, some dashboards) where there's no DOM/network signal underneath at all — lossy and only worth it when nothing else applies.

Same principle as the rest of the stack: default to what's already flowing through the session for free, and gate anything storage- or CPU-heavy behind an explicit flag so a routine scrape doesn't silently become a slow, disk-filling one.

## 2d. Operational essentials (the gap between "extracts data" and "usable tool")

These didn't come up earlier because they're not about *finding* an element — they're what makes the difference between a tiered-cascade demo and something people actually run unattended. All of them lean on existing libraries, same as everywhere else in the plan:

- **Politeness & rate limiting.** Crawlee's autoscaling pool already handles per-domain concurrency and backoff reasonably well for tiers 1–2, so most of this is configuration, not new code — but it should be a first-class `PolitenessPolicy` object (respects `robots.txt` crawl-delay, honors `Retry-After` headers, caps concurrent requests per domain) rather than just a README promise, since §6 already commits to respecting robots.txt by default.
- **Change detection.** Use `ETag`/`Last-Modified` headers or a content hash to skip re-processing pages that haven't changed since last run. This pairs directly with the per-domain cache already in §2 and is what makes monitoring-style use cases (price tracking, content-change alerts) cheap to run on a schedule instead of re-scraping everything every time.
- **CAPTCHA / anti-bot detection — detection, not bypass.** Recognize known challenge-page fingerprints (a Cloudflare interstitial's title text, a reCAPTCHA iframe) and fail loudly with a clear "blocked" result rather than looping forever or silently returning a challenge page as if it were data. An honest "hit a wall here" is itself a useful, expected output.
- **Retry and error classification.** Separate transient failures (timeout, 5xx, 429) from permanent ones (404, 410, confirmed block) — transients retry with backoff (the `tenacity` library, MIT-licensed, is a clean fit rather than hand-rolling this), permanents land in a dead-letter log for human review instead of vanishing silently.
- **Output pipeline.** Pluggable sinks downstream of extraction — JSON Lines, CSV, SQLite as the practical defaults (all stdlib or near enough), Parquet as an optional extra — with the field schema from §2a validated (via `pydantic`, already in the stack) before anything is written. Extraction without a usable output path isn't a finished tool.
- **Run observability.** A structured run summary — items scraped, how often each tier had to escalate, error counts, which fields fell back to tier 3/4 — so a user can tell whether a run actually went well without reading raw logs. This is the project's own signals-catalog thinking (§2c) turned inward on itself.
- **Proxy support hook.** A pluggable interface for user-supplied proxy lists/rotation (Playwright and httpx both accept per-request proxy config natively) — the project doesn't provide or endorse any proxy source, just a clean extension point, since real-world scraping at any scale usually needs one.

**Decision — Phase-1 politeness slice and where the knobs live.** The politeness policy is a first-class object (`spoor/core/config.py:PolitenessPolicy` for the declarative knobs, `spoor/operational/politeness.py` for the runtime gate), configured per target via an optional `politeness:` block on the §2a extraction config — consistent with §2a's "a new site is a new config, never new code." Its Phase-1 scope is **respect `robots.txt` (default on, per §6) and honor the crawl-delay** (from robots.txt, or a `delay:` override in seconds). Two parts of the §2d politeness bullet are deliberately deferred and are **not** a weakening of the commitment, only a phasing split: (1) *caps concurrent requests per domain* — the tier-1 crawl is sequential (one page, follow next-link), so a concurrency cap has nothing to bound until a request pool exists (tier-2 / Crawlee); (2) *honors `Retry-After` headers* — this only has meaning once there is a retry mechanism, and retry/error classification is explicitly Phase 3.5. Both slot into the same `PolitenessPolicy` when their surrounding machinery lands. Per §6, `respect_robots` may be set to `false`, but only as an explicit, deliberate opt-out — never the default.

## 2e. Exploration mode: mapping the full interaction space (post-v1 — see §4)

Everything so far assumes a config (§2a) tells the tool which fields/actions matter. This is a second, distinct mode: point it at a target with no config at all, and it autonomously discovers every actionable element, interacts with each one, captures the full signal bundle (§2c/§2d) before and after, and builds a graph of `state --action--> state`. The end product is a generated wiki — one page per state, one page per transition, browsable — that answers "what happens, on every signal level, when I press this button" for the entire product, not just the fields a user thought to ask about.

**Prior art worth building on, not depending on directly.** Crawljax (now maintained under the OWASP ZAP project, `zaproxy/crawljax`) solved the core research problem here years ago: systematically firing every user-triggerable event on an AJAX-heavy app and building a state-flow graph. It's Selenium-based, not Playwright, so the right move is porting its *algorithm* onto our existing Playwright base rather than adding it as a dependency — specifically its **state abstraction function**: normalize the DOM (strip timestamps, session IDs, counters, anything volatile) and hash it, so revisiting an equivalent state is recognized as such instead of exploding into infinite near-duplicates. Actionable-element discovery reuses the accessibility tree signal already planned in §2c (it already labels roles like button/link/textbox generically, no new mechanism needed).

**Destructive-action safety (per your decision): sandbox-only, non-configurable.** The engine maintains a registry of declared local/self-hosted targets (matches on `localhost`/`127.0.0.1`, or a target explicitly marked `sandbox: true`). Only against a registry match will it interact with actions a heuristic flags as destructive/irreversible (keyword/ARIA matching on delete, remove, buy, purchase, pay, confirm, send, submit-payment, log out — a maintainable, PR-extendable list, not a fixed set). Against anything else — any real external site — those actions are always skipped and logged as skipped; there is deliberately no flag or config option that relaxes this for a non-sandbox target. This is a hard boundary, stated plainly in the README, not a tunable default: the worst case for exploring a real, unvetted site is "missed a state," never "placed a real order" or "deleted real data."

**Run-level controls are core, not optional hardening.** Every exploration run has a hard, user-set budget — max states discovered, max wall-clock time, max requests — that auto-stops the run when hit, plus a manual kill switch to stop a running exploration on command. Both ship in the same phase as the rest of §2e's safety system (Phase 6), never as a follow-up: a run that can't be bounded or stopped is itself a reliability/safety gap under §1's stance and the "core architecture, not later hardening" principle, not a nice-to-have.

This registry is currently **self-declared** (a config sets `sandbox: true`), which is a known, accepted gap for the PoC, not something to solve now — see §9. The current guardrails plus running only against the dedicated test fixtures (§5) is the deliberately-chosen "safe enough for a PoC" posture; hardening the registry itself (e.g. restricting it to `localhost`/private IP ranges regardless of what a config claims) is real future work, tracked rather than blocking anything today.

**Signal capture during exploration reuses the existing cost tiers — and is request-driven, not judgment-driven.** Default to the free/near-free signals from §2c/§2d for every single transition (screenshot, accessibility snapshot, storage-state diff, HAR delta, console diff) — that's the bulk of the wiki's content. The expensive ones (full video, heap snapshots) are reserved for states matching an explicit rule the user configures (e.g. "always deep-capture states matching `/checkout/*`," or "deep-capture anything under this DOM subtree") — corrected from an earlier draft of this section, which described the system autonomously deciding a state looked "interesting." Per §1, Spoor doesn't make that judgment call itself: it records what it's told to, at the depth it's told to, nothing more.

**Wiki generation is comparatively cheap.** The graph (nodes = states with their captured signal bundle, edges = actions with their before/after diff) is just structured output; rendering it as a browsable site means reusing an existing static site generator (MkDocs or Docusaurus) for navigation/search, with a small templating layer turning each node/edge into a page, plus an embedded graph visualization (Mermaid works for smaller graphs; `vis.js`/`pyvis` for larger ones) for the overview. No custom wiki engine to build.

**This is the real test of §0's no-tailoring rule.** The four archetype fixtures (§5) stop being just tier-cascade validation and become the proof that the *exploration algorithm* itself is generic: if it can autonomously map Juice Shop's vulnerability-laced flows, Sauce Demo's checkout, a self-hosted ERP's CRUD-heavy forms, and a Netflix-clone's media/auth state — with the same unmodified state-abstraction and safety logic — that's the real evidence this isn't tailored to any one of them.

**Honest scope note.** This is a substantial second project riding on top of the v1 stack, not a small addition — realistically another **6–9 weeks** (state-abstraction tuning, the safety system with its own dedicated test coverage, graph storage, and wiki templating each take real iteration), most likely landing as v2 rather than folded into the v1 estimate in §4. It's written up in full here because the design is worth locking in now, even though building it comes after v1 ships.

## 2f. Serving the map: MCP server & API (the hero-sentence promise)

Everything in §2a–§2e produces a map — extracted fields, the API surface, the signals catalog, the exploration-mode state graph. §2f is what turns that from "files on disk" into something an *agent* can actually consult: "give your agents a map of the web," not just "give a person a wiki to read."

Two consumption modes, both thin layers over data structures the rest of the plan already produces — no new capture/analysis logic here, purely serving what's already been built:

- **MCP server mode.** Spoor runs as an MCP server (using Anthropic's official `mcp` Python SDK) exposing tools like "get the known state/behavior for this URL," "list the actions available from this state," "what does the API surface look like for this domain," "has this product's checkout flow been mapped already." An agent — Claude or otherwise — can consult Spoor's existing map instead of burning its own tokens re-discovering a site's behavior from scratch every session. This is the direct payoff of §2b/§2c/§2e: the whole point of capturing all that signal was so it doesn't have to be rediscovered live each time.
- **Plain API mode.** The same underlying data served as a conventional REST API (FastAPI is the natural fit — async-native, pairs cleanly with the rest of the async stack, MIT-licensed) for consumers that aren't MCP clients: scripts, dashboards, CI checks against a previously-mapped site.

**Freshness, explained plainly.** Say Spoor mapped a site's checkout flow on Monday. On Friday, an agent asks Spoor "what happens when I click checkout" — but the site may have changed its checkout page since Monday, and Spoor wouldn't know unless it re-checked. "Too old" is just: at what point should Spoor say "let me re-verify that" instead of confidently handing back Monday's answer as if it were still true right now? The per-domain cache (§2) already tracks when something was last confirmed, so the mechanical part (attaching that timestamp to every served answer, and giving the caller a way to force a re-check) is easy. **The actual policy — how old is "too old" before Spoor should recheck on its own rather than wait to be asked — isn't decided, and doesn't need to be right now.** Backlogged (see §9); a reasonable placeholder is "always show the age, never auto-recheck in v1," deciding the smarter policy once there's real usage to learn from.

**Sequencing.** This depends on §2a (extraction) and §2b (API surface) existing to have anything worth serving, but not on §2e (exploration mode) — an MCP/API layer over "the fields and API surface from a configured run" is useful on its own, well before the full autonomous exploration graph exists. Reasonable to build a first pass alongside Phase 5 (packaging) as v1 scope, with the richer "serve the full exploration graph" version arriving once §2e (v2) ships.

## 2g. Test automation run generation (HT's own primary use case)

This is the concrete shape of "test automation run creation" from HT's own stated needs: a captured map (a configured §2a run, or a full §2e exploration graph) is a **golden-master record of known-good behavior** — state X, action Y, produced signal bundle Z. That's already 90% of what a regression test asserts; §2g is the last-mile step of exporting it as one.

Two output shapes, both generated, never hand-written:
- **Assertion-style regression tests**: for each captured transition, emit a test (pytest, or a Playwright Test file if the consuming team is JS-based) that replays the action and asserts the resulting signal bundle still matches — the DOM state, the API calls fired, the console being clean, whatever the capture included. Re-running these against the real product later is exactly how drift gets caught: a failing generated test means the product's actual behavior no longer matches its last-known-good map.
- **Human-readable test plans**: the same transitions rendered as a plain-language run sheet (ties into the §2e wiki output) for teams that want a reviewable test case, not just executable code.

This depends on §2a/§2e existing (nothing to generate from otherwise) and is a natural companion to §2f rather than a separate subsystem — both are "consume the captured map," just for different audiences (an agent asking a question live, vs. a generated artifact a CI pipeline runs). Sequencing: a first pass makes sense alongside Phase 6 (§2e, v2), since the richest version needs the full exploration graph — a thinner version scoped to just a configured §2a run's captured transitions could ship earlier if HT's own test-automation need turns out to be more urgent than the v2 timeline implies (worth revisiting once Phase 1–3.5 are stable and this becomes concrete rather than aspirational).

## 2h. Data handling, security & auth (core architecture, not later hardening)

This section exists directly because of the bottom-line critique: destructive-action safety was already treated as core (§2e), but everything about *data* sensitivity — where captured cookies/tokens/HAR/screenshots live, whether secrets get redacted, what an MCP-connected agent is allowed to do, how login-gated targets are handled at all — was drifting toward "backlog" by omission. These are now decided, folded into the base design rather than appended after the fact.

**Storage & redaction (decided): local-only, auto-redact.** Every artifact §2c/§2d capture produces — cookies, tokens, full storage state, HAR files, screenshots, console output — stays on the user's machine under a per-run directory, never transmitted anywhere by default; this is the literal, concrete meaning of "local-first," not just a slogan. Before anything is written to a *shared* surface — the §2d output pipeline (JSONL/CSV/SQLite), the §2e wiki, or a §2f MCP/API response — Spoor scans for known secret patterns (bearer tokens, common auth-cookie shapes, API keys matching common vendor formats) and redacts them. The raw, unredacted capture (full HAR, full storage state) lives in a separate local cache directory that's never included in anything shared, exported, or served by default — exporting that raw cache is a separate, explicit user action. The actual redaction pattern list is a real Phase 2.5 deliverable, not a vague promise — tracked in §9 below rather than assumed to already exist.

**MCP/API permission boundary (decided): read-only, always.** The §2f serving layer only ever answers questions about a previously-captured map, or triggers a new *read/observation* run (a §2a config or a §2e exploration) — it never exposes a tool letting an agent directly cause a destructive or state-changing action on the target. This is a hard boundary on the MCP/API surface specifically, in addition to (not instead of) §2e's sandbox-only rule for destructive actions during exploration itself: an agent consulting Spoor can look, and can ask Spoor to go look again, but can never use Spoor as a channel to change anything on the target.

**Auth, login, MFA, SSO, multi-role (decided, deliberately scoped narrow for v1): bring-your-own-session.** Spoor does not implement login flows, MFA handling, or SSO redirect automation itself — that's a large, fragile, per-provider surface that would violate §0's no-tailoring principle almost by definition, since every SSO provider ends up being its own integration. Instead, the user authenticates manually once (in their own browser, or Spoor's) and supplies the resulting storage state (`context.storage_state()` — already a planned §2c capture) as an input to a run. Multi-role support is just running the same config once per supplied storage-state file, one per role. This keeps auth entirely outside Spoor's core surface while still making authenticated targets usable from day one.

## 3. License

**Decided: MIT.** Maximizes adoption ("for the masses"), and is compatible with Crawlee (Apache-2.0) and Playwright (Apache-2.0) as dependencies. Copyleft options (GPL, and especially AGPL) were rejected deliberately: AGPL in particular would bind HT's own future use, since it triggers on running a modified version as a network service — exactly what §2f's MCP/API serving layer is. Apache-2.0 was also considered (its explicit patent grant matters more for projects with heavier original patent-eligible contributions); MIT is the simpler, more universally recognized choice given Spoor's genuinely novel pieces are integration/porting work, not something that needs that extra protection. Avoid depending on anything AGPL/commercial-only; specifically, use Healenium's OSS core algorithm/approach rather than Healenium Pro (commercial, adds SaaS features this project doesn't need).

## 4. Phased roadmap

Scope is all four tiers for v1 per your call, but "all four tiers" doesn't have to mean "all four polished." Sequencing them so something real ships early is what keeps this from becoming a months-long black box:

**Phase 0 — Setup (few days)**
Repo scaffold, license, `pyproject.toml` (distribution name **`ht-spoor`** — the plain `spoor` name is taken on PyPI by an unrelated package; project/brand/CLI/repo name all stay **Spoor**, only the `pip install` name carries the prefix), CI (lint + test), contribution guidelines, issue templates.

**Phase 1 — Tiers 1–2, config format, and basic output (1.5–2.5 weeks)**
Wire up Crawlee's adaptive crawler almost as-is — highest-value, lowest-risk work, a thin wrapper around a mature library. Add the §2a declarative config parser and a first pass at the §2d output pipeline (JSON/CSV) and politeness policy in the same phase, since without these the tool has no real user-facing surface yet. Ship this alone as an early v0.1 if you want real feedback fast.

**Phase 2 — Tier 4, human interaction (3–5 days)**
Playwright's primitives plus the jitter/easing wrapper. No ML, no fragile heuristics — quick to build and test, and it's useful on its own (e.g. defeating simple bot checks) even before tier 3 exists.

**Phase 2.5 — API surface discovery + default signal capture (1–2 weeks, can run in parallel with Phase 2/3)**
Spec discovery + GraphQL introspection probes (days), wire in HAR recording on every Playwright context (near-free once Phase 1 exists), then the mitmproxy2swagger spike and, if it pans out, the action-correlation log. Bundle in the free/near-free signals from §2c (storage state, console/errors, accessibility tree, response headers) as default capture at the same time, since they piggyback on the same context. This only depends on Phase 1 existing, not on tiers 3–4, so it can be built alongside them rather than after.

**Phase 2.6 — Opt-in deep signals (3–5 days, only if/when needed)**
Video recording, heap snapshots, and media-manifest capture as explicit flags, not defaults — build these on demand rather than up front, since they're the least likely to be used on every run.

**Phase 3 — Tier 3, local self-healing (2–3 weeks, do not compress this phase — see §1)**
The most genuinely novel engineering here, and per §1 the single highest-priority phase in the whole plan: fingerprint capture on first success, scored matching on failure, a tunable confidence threshold, built alongside the §5.3 mutation-testing harness from the start rather than bolted on after. Expect this phase to need the most iteration and real-world testing against sites that change their markup — that's expected, not a sign something's wrong.

**Phase 3.5 — Reliability essentials (1–1.5 weeks)**
The rest of §2d: CAPTCHA/anti-bot detection (fail loudly, don't loop), retry/error classification with a dead-letter log, change detection (ETag/hash-based skip), and the run-summary observability output. Sits naturally after Phase 3 since it's the same "handle things going wrong gracefully" mindset as self-healing, just at the request/run level instead of the element level.

**Phase 4 — Optional AI fallback, off by default (3–5 days)**
A thin plugin interface (`resolver.set_ai_fallback(fn)`) so power users can point it at Claude, GPT, or a local Ollama model. No default provider shipped — keeps the core dependency-free.

**Phase 5 — "For the masses" packaging (1–2 weeks)**
PyPI publish as **`ht-spoor`** (`pip install ht-spoor`, imports/CLI still `spoor`), CLI polish, docs site fronted by the hero sentence, 3–5 worked example configs (§2a) against public scraping-practice sites, the proxy-hook extension point documented (not built — just the interface), a short "why not just use Crawl4AI" positioning note in the README, GitHub Discussions or Discord for community, and a first-pass §2f MCP/API server exposing whatever §2a/§2b have already captured (the fuller version, serving the §2e exploration graph, follows once v2 ships).

Realistic total: **9–13 weeks** of focused work for a genuinely usable v1 (four UI tiers, API surface discovery, the declarative config interface, and the operational essentials that make it a real tool rather than a library fragment). Phase 3 (tier-3 healing accuracy) is still the likeliest to run long; Phase 3.5 is the next-most-likely, since "graceful failure" only gets exercised properly against real, messy, occasionally-hostile sites.

**Phase 6 — Exploration mode + wiki generation (v2, ~6–9 weeks, starts after v1 ships)**
The full §2e system: state-abstraction tuning, the sandbox-only destructive-action safety system (with its own dedicated test suite proving it can't be bypassed against a non-sandbox target), graph storage, and wiki templating. Deliberately sequenced after v1 rather than folded into it — it depends on the tiers, signals, and action-correlation groundwork from Phases 1–3.5 already existing and being stable, and it's substantial enough on its own that bundling it into the v1 estimate would just make that number meaningless.

## 4a. Repository setup & development approach

**Feature development is BDD-first, layered on top of the existing test pyramid (§5), not a replacement for it.** Every named capability in this plan (§2a extraction, §2d operational essentials, §2e exploration safety, §2f MCP/API serving, §2h data handling) gets a `.feature` file written in Gherkin (Given/When/Then), using `pytest-bdd` so it plugs directly into the same `pytest`/`hypothesis`/`pytest-cov` stack already committed to in §7, rather than adding a second test runner. A feature's scenarios define what "done" means for that capability in plain, reviewable language; they sit above — never instead of — the property-based mutation testing (§5.3) and golden-master diffing (§5.4) that validate tier 3's internals, since "generate hundreds of variants and check a statistical property" isn't a shape Gherkin scenarios are suited for. Workflow for adding or changing a feature: extend/add the `.feature` file first, then step definitions, then implementation, then the full local gate (below) — in that order, not implementation-first with tests bolted on after.

**`CLAUDE.md` at the repo root is the agent-facing instruction file** — read automatically by any Claude Code session working in the repo, the counterpart to this document (which stays the source of truth for *what* and *why*; `CLAUDE.md` is *how to work here*). It points at this file rather than restating decisions, states §0 as a self-check with the genericity CI script named as the enforcement mechanism, spells out the BDD workflow above, and names the non-negotiables — sandbox-only destructive actions (§2e), the MCP/API read-only boundary (§2h), default secret redaction (§2h), and the ≥95% tier-3 mutation-corpus bar (§5.3) — as things no session may weaken without an explicit human decision recorded here.

**Initial document set (Phase 0):**
- `README.md` — hero sentence, elevator pitch, quickstart (human-facing front door)
- `CLAUDE.md` — agent-facing instructions, as above
- `docs/ROADMAP.md` — this document, moved into the repo as the living plan
- `LICENSE` — MIT (§3)
- `CONTRIBUTING.md`
- `pyproject.toml`
- `.github/workflows/` — CI: lint, test, the §0 genericity-check script, the §5.1 nightly drift job
- issue templates
- `features/` — one `.feature` file per named capability, as above

## 5. Testing strategy & test bench design

**Honest framing first, since reliability is now the top priority (§1): "100% accuracy" isn't a real target for a system that must generalize to arbitrary, unknown websites — no adaptive, heuristic-driven mechanism can be proven correct against input it's never seen.** What's achievable, and what this section actually designs for, is a *measured, tracked* accuracy standard: a known success rate against a large, growing corpus of realistic mutations, regressions caught automatically before they reach a user, and an honest published number rather than a marketing claim. §6 already says not to oversell tier 4's stealth in marketing copy — the same discipline applies here to tier 3's reliability.

### 5.1 The fixture layer

- **Static local fixture pages** (checked into the repo) for deterministic per-tier unit tests — hand-built HTML/JS pages that isolate one mechanism each (one page whose element class name changes every reload, to drive tier-3 healing tests deterministically; one that requires JS to render a field, to test tier-2 escalation; one with WebSocket traffic, to test §2c capture) — these exist because the archetype apps below are realistic but not fully controllable, and deterministic unit tests need fully controllable inputs.
- **Public scraping-practice sandboxes** (`books.toscrape.com`, `quotes.toscrape.com`) for basic integration tests and demos — legal, stable, and exactly what "the masses" will try the tool against first.
- **The archetype matrix, purely as validation fixtures (see §0 — never as integrations the core code knows about):** OWASP Juice Shop (security-flavored webshop + API, self-hosted via Docker), Sauce Demo/`saucedemo.com` (clean webshop: login/cart/checkout), a self-hosted ERPNext or Odoo instance (auth-gated internal app: heavy tables, forms, workflows), and a self-hosted open-source Netflix-clone (heavy client-rendered SPA + media state). If one archetype needs a special case to pass, that's a bug in the general mechanism, not a fixture to special-case around.
- **A `docker-compose.yml` test bench** bringing up all four fixtures at once, each declared `sandbox: true` (so §2e's exploration mode can exercise destructive actions safely against them) — what CI and local exploration-mode testing runs against.
- A small **nightly job** against a handful of real-world sites (permissive robots.txt) to catch drift before users hit it.

**Explicitly out of scope as a test target:** a real company's live production site (e.g. Netflix's actual service) — it teaches the suite nothing the self-hosted clone doesn't already cover, and ties CI health to a target nobody controls.

### 5.2 Test types, mapped to what each actually validates

| Test type | Tool | What it catches |
|---|---|---|
| Unit tests | `pytest` | Each tier's logic in isolation against static fixtures — fast, deterministic, run on every commit. |
| Property-based / mutation testing (tier 3 specifically) | `hypothesis` (MIT) | See §5.3 — this is the one that actually matters most given §1's reliability priority. |
| Golden-master regression | `pytest` + Spoor's own captured output | See §5.4 — using Spoor's own maps as the "did anything silently change" baseline, including §2g's generated assertions. |
| Chaos / fault injection | `toxiproxy` (Apache-2.0) | Network latency, dropped connections, slow responses, injected between Spoor and the fixtures — proves §2d's retry/backoff/error-classification actually handles real-world messiness instead of just the happy path. |
| Load / concurrency | `locust` (MIT) | Confirms the §2d politeness policy actually caps concurrency and backs off under load, not just in a single-request test. |
| Safety / sandbox-bypass (adversarial) | `pytest` | Deliberately tries to trick the §2e destructive-action guard (malformed sandbox declarations, edge-case URLs) and asserts it never fires against a non-sandbox target. Given the weight put on that guarantee, this needs its own dedicated suite, not incidental coverage. |
| MCP/API contract tests | `pytest` + schema validation | §2f's responses match their declared schema, and the freshness/staleness signal (§2f) is actually present and accurate on every response. |
| Genericity enforcement (§0) | A small custom script, in CI | Scans core source for hardcoded hostnames/domain strings outside the recognizers/fixtures config, fails the build if found — turns §0's "no site-tailoring" design principle into an automated, unbypassable check rather than a code-review hope. |
| End-to-end smoke | CLI run against each fixture | Cheap, fast pre-merge gate: did the whole pipeline actually run and produce non-empty, valid output. |
| Coverage tracking | `pytest-cov` | Baseline metric, tracked over time — not a target to game, but a signal if a whole code path has zero test contact. |

### 5.3 Tier 3 gets the most rigorous testing in the plan, on purpose

Given §1: this is the piece that can't be flaky. The design: a **mutation harness** takes a known-good fixture (one where tier 1/2 correctly finds an element) and applies a battery of realistic DOM mutations — class renames, attribute shuffles, element reordering, added wrapper elements, text changes, combinations of the above at increasing severity — then asserts tier 3 still resolves to the *correct* element above a defined confidence threshold. Using `hypothesis` to generate mutation variants (rather than hand-writing a fixed list) means the corpus grows and explores far more of the space automatically than example-based tests alone. The tracked output is a **success rate against this corpus**, published and monitored for regression on every change to tier 3 — that number, not a one-time claim, is what "reliable" actually means here.

**Concrete v1 target (decided): ≥95% correct-element resolution on the mutation corpus**, tracked per release and gating a Phase 3 "done" call — not just an open-ended measured number with no bar to clear. Anything below that threshold on a given mutation class is a known gap to fix before shipping, not a footnote.

### 5.4 Dogfooding: Spoor's own captured maps as regression tests

Once Spoor maps a fixture's behavior (via §2a or §2e), that map is a golden master: state X, action Y, signal bundle Z. Re-running Spoor against the same fixture later should reproduce a matching bundle — a diff-based test asserts nothing silently changed, in either the fixture *or* Spoor's own behavior, and this doubles as a concrete demonstration of exactly what §2g (generated test automation) produces for an end user. This is testing the tool with the tool, run on every CI pass against the docker-compose fixtures in §5.1.

**On exact reproducibility:** Spoor does not promise byte-identical output run-to-run against a real, live target — the target itself can change, tier 3 can legitimately heal to a different-but-equally-correct element, and async network timing varies. The golden-master/diff approach above *is* the reproducibility model: not "identical every time," but "any change gets surfaced and reviewed," which is the honest version of reproducibility a system like this can actually deliver.

## 6. Risks worth naming up front

- **Legal/ethical, and where responsibility actually sits**: default to respecting `robots.txt` and rate-limiting; make overriding it an explicit, documented opt-out, not the default. But say this plainly and prominently in the README, not buried here — **Spoor is a technical capability, not a legal opinion or a grant of permission.** Whether it's lawful or permitted to scrape or reverse-engineer a given target's API is a question only the person pointing Spoor at it can answer, for their own situation (the target's ToS, their jurisdiction, the target's own terms). The user, not Spoor, is legally responsible for how it's pointed and used.
- **Anti-bot arms race**: tier 4's "human-like" behavior raises the bar but won't defeat serious bot detection (e.g. Cloudflare's harder tiers) — don't oversell this in marketing copy.
- **Tier 3 accuracy**: self-healing locators are the hardest part to get right; budget real iteration time here, not just initial implementation time.
- **Maintenance load**: "for the masses" means issues and PRs from people scraping sites you've never seen — decide early how much support bandwidth you actually have, and say so in the README (e.g. "best-effort" vs. actively maintained).
- **API discovery is legally touchier than UI scraping**: reverse-engineering undocumented endpoints and calling them directly bypasses whatever rate-limiting/abuse controls the official UI enforces, and many ToS treat that distinction explicitly. Worth a clear README statement that captured/synthesized specs are for understanding a product's surface, not a license to hit endpoints outside normal usage patterns.

## 7. Complete tech stack reference

Everything named across this plan, in one place. "Depend" = a real runtime dependency; "Reference" = we're porting the algorithm/approach, not taking the project as a dependency (usually because it's a different language/runtime, like Crawljax's Java/Selenium base).

**Core crawling & browser control**
| Tool | Role | License | Use |
|---|---|---|---|
| Playwright (Python) | Browser control, tiers 2–4, HAR/video/WebSocket/CDP access | Apache-2.0 | Depend |
| Crawlee for Python | `AdaptivePlaywrightCrawler`, request queue, autoscaling/concurrency, `HttpCrawler` | Apache-2.0 | Depend |
| httpx | Async HTTP client for tier 1 (no browser) | BSD-3 | Depend |
| parsel | CSS/XPath selectors (Scrapy's selector engine, unbundled) | BSD-3 | Depend |

**Supported browsers/OSes: whatever Playwright (Python) supports, no separate matrix.** Target browser engines — Chromium, Firefox, WebKit. Host OS for running Spoor itself — Linux, macOS, Windows.

**Tier 3 — resilience / self-healing**
| Tool | Role | License | Use |
|---|---|---|---|
| Healenium (core, not "Pro") | DOM-fingerprint + similarity scoring approach for locator healing | Apache-2.0 | Reference |
| OpenCV (`opencv-python`) | Perceptual-hash / template matching on cropped screenshots | Apache-2.0 | Depend |

**Tier 4 — human-like interaction**
| Tool | Role | License | Use |
|---|---|---|---|
| Playwright mouse/keyboard API | Native scroll, drag, click, hover primitives | Apache-2.0 | Depend (already listed above) |
| `ghost-cursor` (algorithm) | Bezier-curve mouse-path jitter, ported to Python | MIT (original Node lib) | Reference |

**Optional AI fallback (off by default)**
| Tool | Role | License | Use |
|---|---|---|---|
| Anthropic/OpenAI API | Vision-based element grounding, last resort only | Commercial API | Optional, pluggable |
| Ollama + a local VLM (e.g. Moondream) | Same, fully local instead of cloud | MIT / model-dependent | Optional, pluggable |

**API surface discovery**
| Tool | Role | License | Use |
|---|---|---|---|
| Playwright `record_har_path` | Native HAR capture, no proxy needed | (covered above) | Depend |
| mitmproxy2swagger | Clusters captured traffic into an OpenAPI spec | MIT | Depend |
| mitmproxy | Only if a flow-format conversion step is needed to feed mitmproxy2swagger | MIT | Optional, spike-dependent |
| `gql` (or a raw POST) | GraphQL introspection query | MIT | Optional convenience |

**Signals catalog**
| Tool | Role | License | Use |
|---|---|---|---|
| Chrome DevTools Protocol (via Playwright's CDP session) | Performance metrics, HeapProfiler snapshots, low-level Network events | (browser-native, no separate package) | Depend |

No new libraries needed for storage state, console/error capture, or the accessibility tree — all native Playwright APIs already counted above.

**Operational essentials**
| Tool | Role | License | Use |
|---|---|---|---|
| `pydantic` | Config field validation, extracted-data schema validation | MIT | Depend |
| `tenacity` | Retry/backoff policy for transient failures | Apache-2.0 | Depend |
| stdlib `json`/`csv`/`sqlite3` | Default output sinks | PSF | Depend |
| `pyarrow` | Optional Parquet output | Apache-2.0 | Optional |

**Exploration mode + wiki (v2, §2e)**
| Tool | Role | License | Use |
|---|---|---|---|
| Crawljax (`zaproxy/crawljax`, under OWASP ZAP) | State-abstraction-function algorithm for dedup/exploration | Apache-2.0 | Reference |
| MkDocs (or Docusaurus) | Static site generator for the browsable wiki output | BSD-2 (MkDocs) / MIT (Docusaurus) | Depend |
| Mermaid / `pyvis` / `vis.js` | Graph visualization for the state/transition overview | MIT-family | Depend |

**Serving the map (§2f)**
| Tool | Role | License | Use |
|---|---|---|---|
| `mcp` (official Python SDK, `modelcontextprotocol/python-sdk`) | MCP server mode — exposes the map as tools an agent can call | MIT | Depend |
| FastAPI | Plain REST API mode for non-MCP consumers | MIT | Depend |

**Project tooling (not part of the shipped library, but part of building it)**
| Tool | Role | License | Use |
|---|---|---|---|
| `uv` (or Hatch) | Fast dependency management / packaging, replaces pip+venv juggling | MIT (uv) | Dev tooling |
| `ruff` | Linting + formatting in one tool | MIT | Dev tooling |
| `pytest` | Test runner for everything in §5 | MIT | Dev tooling |
| `hypothesis` | Property-based/mutation testing for tier 3 (§5.3) — the highest-priority test suite in the plan | MPL-2.0 | Dev tooling |
| `toxiproxy` | Network fault injection (latency, drops) for §5.2 chaos testing | Apache-2.0 | Dev tooling |
| `locust` | Load/concurrency testing for the §2d politeness policy | MIT | Dev tooling |
| `pytest-cov` | Coverage tracking | MIT | Dev tooling |
| `mypy` or `pyright` | Optional static type checking, pairs well with `pydantic` models | MIT | Optional dev tooling |
| `typer` (built on `click`) | CLI (`spoor run config.yaml`) | MIT | Depend |
| Docker / `docker-compose` | The §5 test bench (all four archetype fixtures) | Apache-2.0 | Dev/test tooling |
| GitHub Actions | CI (lint, test, the nightly drift job) | N/A (hosted) | Dev tooling |

One thing worth noticing across this whole table: apart from the two API-vendor options in the optional AI fallback row, **every single entry is open source and self-hostable**, and the large majority are permissively licensed (MIT/Apache-2.0/BSD) — consistent with §1's positioning and §3's license choice. Nothing here should force MIT-incompatible obligations onto the finished project.

## 8. Immediate next steps

1. ~~Pick a project name~~ — **Spoor**, confirmed. ~~Pick a PyPI distribution name~~ — **`ht-spoor`**, confirmed (plain `spoor` is taken). Confirm MIT license and register both the GitHub org/repo (`spoor`) and the PyPI name (`ht-spoor`).
2. Scaffold the repo (Phase 0) and get Crawlee's adaptive crawler running against one real site end-to-end, driven by a single §2a config file and writing JSON output (Phase 1) — this is the fastest path to something demoable.
3. Decide who else, if anyone, is working on this with you — affects how much process (CI, review) is worth setting up now vs. later.
4. Run the mitmproxy2swagger/HAR spike (§2b, item 4) before scoping Phase 2.5 for real — it's the one open technical unknown that could change that phase's approach.

## 9. Open questions & backlog

Tracked here so they don't get lost, sorted by whether they block anything:

**Needs answering before the relevant phase starts:**
- **mitmproxy2swagger + HAR compatibility** (§2b) — confirm via a short spike before Phase 2.5 is scoped for real. If it doesn't work cleanly, fall back to writing the clustering logic directly against HAR.
- **Concrete secret-redaction pattern list** (§2h) — the "auto-redact known secret patterns" policy needs an actual, maintained list (bearer token shapes, common session-cookie names, common vendor API-key formats) before Phase 2.5 ships default capture; decide/build this alongside Phase 2.5, not after.

**Deliberately deferred, not blocking anything now:**
- **Sandbox-registry hardening** (§2e) — self-declared `sandbox: true` is accepted as "safe enough for the PoC" given the current guardrails and dedicated test fixtures; revisit whether it needs a harder technical backstop (e.g. restricted to `localhost`/private IP ranges) once there's a dedicated test-environment setup to design around.
- **Freshness/staleness policy for §2f** — placeholder for v1 is "always show the answer's age, never auto-recheck." The real policy (when Spoor should proactively re-verify vs. wait to be asked) gets decided once there's real usage to learn from.
- **Whether a thinner §2g (test-automation generation) should ship before Phase 6**, if HT's own need for it turns out to be more urgent than the v2 timeline implies — revisit once Phases 1–3.5 are stable.

**Needs a decision eventually, but not urgent / not blocking Phase 0:**
- **CPU/memory/disk cost estimates** — none exist yet for any resolution tier or for exploration-mode runs. Real numbers depend on the §5.2 `locust` load-testing work; treat as a measured *output* of Phase 3.5/Phase 6, not something to guess at now.
- **Maintainer/bus-factor policy** — §6 names "maintenance load" as a risk but doesn't answer who actually handles it when a core dependency (Playwright, Crawlee, mitmproxy2swagger) has a breaking change, or what support-bandwidth promise (if any) goes in the README. Decide before or shortly after public release, not before Phase 0.

**Small, easy to close whenever:**
- ~~Formally confirm MIT~~ — **done**, see §3.
- Confirm the actual GitHub org/repo path is free (checked PyPI's `ht-spoor`; hasn't specifically checked the GitHub path you intend to use).
