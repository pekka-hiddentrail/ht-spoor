# Spoor

> **Give your agents a map of the web.**
> Spoor is a local-first crawler that escalates from selectors to browser and
> visual interaction only when needed — then exposes the discovered behavior
> through MCP or API.
>
> **Local-first. MCP-ready. LLM optional.**

Spoor escalates through UI resolution tiers (fast selectors → JS-rendered
selectors → visual/fingerprint healing) with human-like interaction on a
separate axis, only going as deep as a target needs. Alongside, it passively
builds a map of the target's API surface and a catalog of client-side signals —
using existing open-source components wherever possible, and LLM calls only as
an optional, off-by-default last resort.

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

1) Create a config file (same schema for every target, §0):

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

## Current capabilities

### Available now

- Tier-1 extraction: single-record and listing (`item`) extraction, text/`attr` field values, `number` coercion, next-link pagination
- Tier-2 browser slice: escalation for infinite-scroll pages, then extraction from rendered DOM
- Run observability: structured run summary for each run
- API discovery: OpenAPI/Swagger discovery, GraphQL introspection, HAR-based synthesis, and action-to-endpoint correlation
- Tier-3 self-healing: scored matching, uncertain-match handling, cross-run fingerprint persistence, listing field/container healing, re-anchoring, and visual-signal corroboration

### Optional capture signals (browser tier)

- HAR
- console output / JS errors
- accessibility tree snapshots
- response-header fingerprints
- client-side storage state (with redaction on shared output)

Captured artifacts are written to a local-only, git-ignored cache.

### Still on the roadmap

- Default-on capture behavior (today capture remains opt-in)
- MCP/API serving layer

## Contributing

Development is BDD-first and holds a hard "never site-tailored" rule (§0). See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CLAUDE.md`](CLAUDE.md).

## License

MIT — see [`LICENSE`](LICENSE).
