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

```
python -m pip install -e ".[dev]"
```

The distribution name is `ht-spoor` (`pip install ht-spoor`, once published);
the import package and CLI are both `spoor`.

## Usage (Phase 1, in progress)

Describe what to extract in a declarative config — the schema is identical for
every target (§0), so a new site is a new config, never new code:

```yaml
# config.yaml
target: https://example.com/products
item: "li.product-card"          # optional: one output record per match
fields:
  title: { selector: "h2.title" }
  price: { selector: ".price", type: number }
pagination:
  next: "a.next-page"
politeness:                      # optional; robots.txt is respected by default
  delay: 1.0                     # min seconds between fetches (overrides crawl-delay)
```

```
spoor run config.yaml -o output.json
```

Spoor respects `robots.txt` and honors its crawl-delay by default (§2d, §6):
disallowed URLs are recorded and never fetched. Ignoring `robots.txt` is an
explicit, deliberate opt-out — `politeness: { respect_robots: false }` — never
the default.

**What works today:** tier-1 extraction (fast selectors over fetched HTML, no
browser) — single or repeating (`item`) records, `number` coercion, and
next-link pagination — behind a `robots.txt`/crawl-delay politeness gate. JS
rendering (tier 2), self-healing (tier 3), infinite-scroll, and the
API-surface/signals capture are still ahead on the roadmap.

## Contributing

Development is BDD-first and holds a hard "never site-tailored" rule (§0). See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CLAUDE.md`](CLAUDE.md).

## License

MIT — see [`LICENSE`](LICENSE).
