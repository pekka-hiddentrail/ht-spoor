# Spoor

> **Give your agents a map of the web.**
> Spoor is a local-first crawler that escalates from selectors to browser
> rendering and visual/fingerprint healing only when needed.
>
> **Local-first. Config-driven.**

Spoor escalates through UI resolution tiers (fast selectors → JS-rendered
selectors → visual/fingerprint healing), only going as deep as a target needs.
Alongside extraction, it passively observes the target's API surface and a
catalog of client-side signals.

It reports **a map of what's been explored** — everything Spoor has actually
observed or been asked to look at — never a guaranteed-exhaustive census of a
target.

> **Spoor is a technical capability, not a legal opinion or a grant of
> permission.** Whether it's lawful or permitted to scrape or reverse-engineer a
> given target is a question only the person pointing Spoor at it can answer.
> Spoor respects `robots.txt` and rate limits by default.

## Status

Early development — see [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full plan
and current phase. Not yet published to PyPI.

## Install (from source)

### Prerequisites

- Python 3.11+
- For browser-tier features (for example infinite-scroll), install Chromium once
  after `pip install`:

  ```
  python -m playwright install chromium
  ```

### Install

```
python -m pip install -e ".[dev]"
```

The distribution name is `ht-spoor` (`pip install ht-spoor`, once published);
the import package and CLI are both `spoor`.

## Quickstart (taking Spoor into use)

1) Create a config file:

```yaml
# config.yaml
target: https://example.com/products
item: "li.product-card"  # optional: one output record per match
fields:
  title: { selector: "h2.title" }               # element text (default)
  url:   { selector: "h2.title a", attr: href } # or an attribute value
  price: { selector: ".price", type: number }
pagination:
  next: "a.next-page"
```

2) Run it:

```
spoor run config.yaml -o output.json
```

3) Check the results:

- `output.json` contains the extracted records
- the CLI prints a run summary (`items scraped`, `pages fetched`, `resolved by`, and so on)

Common output options:

```
spoor run config.yaml -o data.csv          # CSV; columns = your config fields
spoor run config.yaml -o out.dat -f jsonl  # force JSON Lines with --format
```

## Runtime behavior (important defaults)

- Output formats: JSON, JSON Lines, CSV (schema-validated before writing)
- Politeness: `robots.txt` respected by default; crawl-delay honored by default
- Retry: transient failures (timeouts, dropped connections, 5xx, 429) retry with backoff and `Retry-After`; other 4xx are dead-lettered. Browser-tier page navigations retry on the same policy, so a transient navigation failure is dead-lettered rather than crashing the run
- Anti-bot detection: a fetch landing on a known anti-bot wall (a reCAPTCHA/hCaptcha widget, a Cloudflare interstitial) is flagged loudly on the run summary rather than scraped as data — whether the wall arrives in a normal response or behind a 403/503 error status (where the run is both dead-lettered and reported as a challenge). Detection only, never a bypass attempt
- Change detection (opt-in, `change_detection: true`): a re-run sends the `ETag`/`Last-Modified` a prior run recorded as a conditional request and skips re-extracting a page the server reports unchanged (a 304, or a matching content hash) — cheap monitoring runs, off by default so a one-shot scrape still extracts everything
- Safety/data handling: raw captures stay local-only; known secret patterns are redacted before shared output

Ignoring `robots.txt` is an explicit opt-out (`politeness: { respect_robots: false }`), never the default.

## Authenticated targets (bring-your-own-session)

To scrape a login-gated site, authenticate once in your own browser, export the
session as a storage-state file (the JSON Playwright's `context.storage_state()`
writes — cookies plus per-origin `localStorage`), and point the config at it:

```yaml
target: https://example.com/account/orders
session: ./my-session.json   # a browser session you captured, kept out of git
fields:
  order: { selector: ".order-id" }
```

Spoor sends the session's cookies on the plain fetch and loads the whole state
(cookies + `localStorage`) into the browser when a page needs rendering, so a
target gated behind either is reachable. Spoor performs **no** login, MFA, or SSO
flow itself — you supply an already-authenticated session; for multiple roles,
run the same config once per session file. The session file is treated as a
secret: it is read locally and never written into your output or the run summary.
A missing or malformed session file fails the run loudly rather than quietly
scraping as an anonymous visitor.

## Exploring a site (no config)

When you don't have a config and just want to know what a site *does*, point
Spoor at a starting URL:

```bash
spoor explore https://example.com

# Bound the run so it always stops:
spoor explore https://example.com --max-states 200 --max-requests 1000 --max-seconds 300
```

Spoor opens the page in a real browser, discovers the interactive elements it can
find on each screen (buttons, links, form controls), waits for the page to finish
settling, tries each one, and records where it leads — building a graph of the
site's states and the transitions between them. "Settling" means both the DOM and
any in-flight page requests have been quiet for a short window, so Spoor reads the
fully-rendered screen rather than a mid-hydration snapshot. If the page never
reaches that quiet point before the safety timeout, Spoor records the state as
unsettled and continues on the last snapshot instead of hanging. It recognizes a
screen it has already seen, so it maps the site instead of looping forever, and
prints a summary of how many states and transitions it found. Press **Ctrl-C** to
stop early; it finishes the current step cleanly rather than aborting mid-click.
Spoor works outward layer by layer — it maps the start page, then everything one
click away, then the next layer, and so on — so a run that stops early still covers
the shallow, high-value pages (a shop's top categories, its cart) before descending
into deep product or variant pages. Within each layer it tries links that point to
top-level pages before ones that point deep into the site, so the highest-value
pages come first even when the run is capped tightly. Use `--max-states`,
`--max-requests`, and
`--max-seconds` to cap the run, and `--max-depth` to map only the first few layers
(`--max-depth 1` maps the start page and everything one click from it). If an
element it found can't actually be clicked (it disappeared, is hidden, or is
covered by the time Spoor gets to it), that one action is recorded as skipped and
the run keeps going — a single dead button never aborts the map.

Add `--wiki <dir>` to also write a **browsable wiki** of the map to that directory —
one HTML page per state and per transition, plus an overview page with a diagram of
the whole graph. States are labelled by their page title so the map reads at a glance,
and a page's console and network output is collapsed to one row per line with a count
rather than repeating it. Network requests are grouped by kind — scripts, styles,
images, fonts, media, data, and documents — so you can see what a page loaded at a
glance, and each state shows only the requests and console output from the path that
reached it. Open its `index.html` in a browser to read what Spoor found.
Any secrets captured along the way (tokens, session cookies) are redacted before they
reach the wiki.

```bash
spoor explore https://example.com --wiki ./site-map
# then open ./site-map/index.html
```

**The safety rule — read this before pointing it at anything real.** Some actions
are destructive: deleting a record, buying, paying, logging out, submitting a form.
On any normal site Spoor **always skips** those and tells you it skipped them — it
will never click "Delete" or "Buy" on a live site. The **only** way it will exercise
a destructive action is if you explicitly declare the target a sandbox you own with
`--sandbox`:

```bash
# ONLY for a local or throwaway test system you control:
spoor explore http://localhost:3000 --sandbox
```

Never pass `--sandbox` for a site you don't own or can't safely reset. This is a
hard rule, not a preference: there is no flag or config that makes Spoor perform a
destructive action on a target it doesn't recognize as a sandbox (a local address,
or one you declared with `--sandbox`).

## Current capabilities

### Available now

- Tier-1 extraction: single-record and listing (`item`) extraction, text/`attr` field values, `number` coercion, next-link pagination
- Tier-2 browser slice: escalation for infinite-scroll pages, then extraction from rendered DOM
- Run observability: structured run summary for each run
- API discovery: OpenAPI/Swagger discovery, GraphQL introspection, HAR-based synthesis, and action-to-endpoint correlation
- Tier-3 self-healing: scored matching, uncertain-match handling, cross-run fingerprint persistence, listing field/container healing, re-anchoring, and visual-signal corroboration
- Authenticated targets: supply a captured browser session (cookies + `localStorage`) via `session:` to scrape login-gated pages — "bring-your-own-session"; Spoor performs no login itself
- Exploration mode: point Spoor at a URL with no config and it maps the site in a real browser — `spoor explore <url>` discovers the interactive elements it can reach on each screen, waits for the page to settle before reading it, and records where each action leads as a graph of states and transitions (see "Exploring a site" below for the safety rule). When a welcome dialog or cookie-consent overlay sits over the page and intercepts clicks, Spoor interacts past it (dismissing the overlay the same way a visitor would) and maps the site behind it, instead of stopping at the overlay — while still refusing any interaction the safety rule forbids. If a page never fully settles before the safety timeout, the state is flagged as unsettled and the run continues on the last snapshot rather than hanging. Add `--wiki <dir>` to render the result as a browsable wiki — an overview diagram plus a page per state and transition, secrets redacted. Each exploration is also remembered in the local map, so the serving layer below can hand the graph back later without re-exploring
- Read-only map serving: each run remembers what it mapped for the target URL — extracted records, a safe summary of any API surface it observed (published spec/GraphQL endpoint, plus endpoint/request counts), and, for a URL that was explored, the exploration graph itself (the states discovered and, for each button or link, what clicking it changed). Two ways to consult it without re-crawling: `spoor serve` exposes a small read-only HTTP API, and `spoor serve-mcp` exposes the same data to agents as read-only MCP tools (list mapped domains; fetch a URL's records, observed API surface, and exploration graph with how long ago it was captured — so an agent can ask "what happens when I click X" instead of re-exploring). By default both only read the stored map. Neither ever changes a site: the strongest thing either can do is re-observe one — opt in with `--recheck` and they also accept a request to re-check a mapped URL, which re-runs that URL's extraction (a fresh read of the site) and refreshes the map. Secrets are redacted from everything they return. Install with `pip install 'ht-spoor[serve]'`

### Optional capture signals (browser tier)

- HAR
- console output / JS errors
- accessibility tree snapshots
- response-header fingerprints
- client-side storage state (with redaction on shared output)

Captured artifacts are written to a local-only, git-ignored cache.

### Still on the roadmap

- Default-on capture behavior (today capture remains opt-in)
- Automatic re-checking of a served map entry once it is "too old" (today the serving layer always shows how old an answer is and only re-fetches when a caller explicitly asks via `--recheck`, never on its own)

## Contributing

Development is BDD-first and holds a hard "never site-tailored" rule (§0). See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CLAUDE.md`](CLAUDE.md).

## License

MIT — see [`LICENSE`](LICENSE).
