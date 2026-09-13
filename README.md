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
  title: { selector: "h2.title" }              # element text (default)
  url:   { selector: "h2.title a", attr: href } # or an attribute's value
  price: { selector: ".price", type: number }
pagination:
  next: "a.next-page"
politeness:                      # optional; robots.txt is respected by default
  delay: 1.0                     # min seconds between fetches (overrides crawl-delay)
```

```
spoor run config.yaml -o output.json      # format inferred from the extension
spoor run config.yaml -o data.csv          # → CSV, columns = your config fields
spoor run config.yaml -o out.dat -f jsonl  # or force it with --format
```

Output is written as JSON, JSON Lines, or CSV, and every record is validated
against your config's field schema before anything is written. Spoor respects
`robots.txt` and honors its crawl-delay by default (§2d, §6):
disallowed URLs are recorded and never fetched. Ignoring `robots.txt` is an
explicit, deliberate opt-out — `politeness: { respect_robots: false }` — never
the default.

**What works today:** tier-1 extraction (fast selectors over fetched HTML, no
browser) — single or repeating (`item`) records, element text or attribute
(`attr`) values, `number` coercion, and next-link pagination — behind a
`robots.txt`/crawl-delay politeness gate, with schema-validated JSON/JSON
Lines/CSV output. Tier 2 (JS rendering via headless Chromium) also works for
its first slice: the dispatcher escalates to it for infinite-scroll pages,
which it renders and scrolls to exhaustion before reusing the same extraction.
Every run also looks for a published API spec — probing conventional paths and
scanning the landing page's HTML and its same-origin JS bundles for a reference
to one — and an introspectable GraphQL endpoint (§2b), and reports a structured
run summary (§2d). When a run captures a HAR, it additionally synthesizes an API
spec by clustering the recorded requests into templated endpoints (`/users/1`,
`/users/2` → `/users/{id}`) and writes that OpenAPI document to the local-only
cache — a bounded, inference-from-observed-traffic map, never a complete-API
claim (§2b layer 4). It also correlates those requests back to the actions that
likely triggered them — marking a checkpoint before each page load and scroll,
then attributing each request to the action whose time window it fell in — a
time-window approximation, never proven causation (§2b layer 5); the per-action
map stays local-only, only counts reach the summary. The browser tier can
opt into capturing signals (§2c) — HAR, console output/JS errors, the
accessibility tree, response-header fingerprints, and client-side storage state
— written to a local-only, git-ignored cache; only safe derived facts reach
shared output, with known secrets redacted first (§2h). Tier-3 self-healing has
its scoring core (Phase 3): when a selector breaks, it re-resolves the element by
scoring every candidate against a fingerprint captured while the selector worked
— tag, id, class, attribute, inner-text, structural, and descendant-composition
similarity, no model call
(§2) — flagging a low-confidence best candidate as an "uncertain match" for review
rather than guessing, and always recording the winning score plus the runners-up
it considered. This scoring algorithm is written from scratch — Spoor takes no
dependency on Healenium and vendors none of its code; Healenium's published,
permissively-licensed core approach was a conceptual reference only. Its accuracy is guarded by the §5.3 `hypothesis` mutation corpus at
the merge-blocking ≥95% bar (currently ~99.8%). That core is now wired into a
live run: while a field's selector resolves, the run fingerprints the element into
a per-domain cache that persists across runs (local-only, §2h); on a later run, if
that selector breaks but a fingerprint was remembered, tier 3 re-resolves the
field — a confident heal fills it, an uncertain match leaves it null and is
flagged, and the run summary surfaces the confident/uncertain counts (never the
matched text, §2h). This works for both single-record configs and listings: in a
listing, a field whose selector breaks *inside* the rows is healed **per row**,
scoring the candidates within each row against a text-agnostic fingerprint (a
listing's rows share structure but differ in text) — and, because healing only
ever matches a fingerprint a *prior* run recorded, a row that genuinely lacks an
optional field is left null rather than filled in from its sibling rows. And a
confident heal **re-anchors**: it rewrites the stored fingerprint to the healed
element's current shape, so successive redesigns each heal from the most recent
shape rather than only the original — drift is absorbed one healable step at a
time (an uncertain match never re-anchors). The fingerprint now also captures an
element's **descendant composition** (the multiset of tags it contains) — inert
for leaf fields, but the identity a *container* keeps when its own class is
renamed — as the groundwork for healing the row-container (`item`) selector itself
when a whole row breaks, which, with the perceptual-hash-on-screenshot component,
are the next Phase-3 slices. Default-on capture and the MCP/API serving layer are
still ahead on the roadmap.

## Contributing

Development is BDD-first and holds a hard "never site-tailored" rule (§0). See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CLAUDE.md`](CLAUDE.md).

## License

MIT — see [`LICENSE`](LICENSE).
