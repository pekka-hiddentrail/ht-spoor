# CLAUDE.md — Spoor

Instructions for any Claude Code session working in this repository. This file is the *how to work here* counterpart to `docs/ROADMAP.md`, which is the *what and why* — the single source of truth for design decisions. Cite ROADMAP.md by section (e.g. "§2e") rather than restating its content here. If this file and ROADMAP.md ever conflict, ROADMAP.md wins — flag the conflict instead of silently picking one.

## Hard rule: §0 — never site-tailored

Nothing in `spoor/core/` may hardcode knowledge of a specific website: no `if domain == "..."` branches, no selectors or endpoint paths written against one named site, no logic that only makes sense for one target. The only allowed exceptions:

- The per-domain cache — fine, because it's runtime-*learned* behavior, discovered the same generic way for every target.
- The pluggable, opt-in "platform recognizers" table (e.g. Shopify conventions) — fine as a swappable table in `spoor/recognizers/`, never as logic baked into the escalation path itself.

`scripts/check_genericity.py` scans core source for hardcoded hostnames/domain strings outside the recognizers/fixtures config and fails CI if it finds any. If a fixture (OWASP Juice Shop, Sauce Demo, the self-hosted ERP, the Netflix-clone) only passes with a special case added for it, that's a bug in the general mechanism to fix — never a reason to add the special case.

## Non-negotiables

Never weaken any of these without an explicit human decision recorded in `docs/ROADMAP.md` — not a config flag, not a "just for this test," not because it would make a feature easier to ship:

- **Destructive actions during exploration mode (§2e) are sandbox-only and non-configurable.** Only against a registry match (`localhost`/`127.0.0.1`, or `sandbox: true`) may the engine interact with actions flagged as destructive/irreversible. Against anything else, those actions are always skipped and logged as skipped. No flag relaxes this for a non-sandbox target.
- **The MCP/API serving layer (§2f/§2h) is read-only, always.** It may answer questions about a captured map and trigger new read/observation runs. It must never expose a tool letting an agent cause a destructive or state-changing action on a target.
- **Secret redaction on shared output is on by default (§2h).** Known secret patterns (bearer tokens, session-cookie shapes, common API-key formats) are redacted before anything reaches the output pipeline, the wiki, or an MCP/API response. Raw, unredacted captures (full HAR, full storage state) stay in the local-only cache; nothing bypasses redaction on its way to shared output without an explicit user opt-in to export the raw cache.
- **The tier-3 mutation-corpus success rate must stay ≥95% (§5.3).** This is a merge-blocking number for any change touching tier 3, not an advisory metric.

## Feature development: BDD first

Every named capability in ROADMAP.md (§2a extraction, §2d operational essentials, §2e exploration safety, §2f MCP/API serving, §2h data handling, etc.) is developed in this order — never implementation-first with tests added afterward:

1. Write or extend the capability's `.feature` file under `features/` (Gherkin: `Given` / `When` / `Then`). This defines what "done" means in plain, reviewable language before any code is written.
2. Add or update step definitions (`pytest-bdd`).
3. Implement.
4. Run the full local gate (below) before considering the feature done.
5. Self-review the diff before opening a PR — see "Self-review" below. This is not optional and not something to wait to be asked for; a green gate is necessary but not sufficient.

BDD scenarios sit *above* the rest of the test pyramid, not instead of it. Property-based/mutation testing (`hypothesis`, §5.3) and golden-master diffing (§5.4) stay in place for tier 3's internals and regression safety — those validate "generate hundreds of variants and check a statistical property," which isn't a shape Gherkin scenarios are suited for.

## Self-review — before every PR, not only when asked

A passing gate proves the happy paths run; it does not prove the code is correct, honest, or free of regressions. After the gate is green and before opening the PR, read your own diff end to end as if reviewing someone else's work — adversarially, trying to *break* it, not to confirm it works. Hunt specifically for:

- **Edge cases and boundaries** — empty / `None` / zero / negative / very large inputs, off-by-one, unicode and whitespace, duplicate or cyclic data, the first and last iteration. Probe the new logic with concrete values (a throwaway script is fine), don't just eyeball it.
- **Regressions from a "fix"** — did the change narrow, widen, or alter existing behavior as a side effect? Re-check it against the scenarios that already exercised that path. (A real example: a coercion fix whose lookbehind also silently rejected a previously-handled input.)
- **Naming and contract honesty** — does every name mean what the thing does? A predicate that returns `True` on a path that always raises, a `get_` that mutates, a docstring describing behavior that no longer exists — each is a defect, not a nitpick.
- **Error and cleanup paths** — exceptions, early returns, resource release (files, clients, locks) on both success and failure.
- **Docs and text in step with code** — docstrings, `README.md`, `docs/ROADMAP.md` decision notes, and `.feature` comments must describe what actually shipped. Stale scaffolding language ("raises NotImplementedError until…") is a reportable finding, not cosmetic.
- **§0 and the non-negotiables** — nothing site-specific leaked into `spoor/core/`, and no non-negotiable above was weakened without a recorded ROADMAP decision.

Report what you find honestly — in the working summary and the PR description — and surface real issues rather than reassure. "Nothing found" is a valid outcome only after actually looking; say what you checked. Fixing a defect you found in your own diff before merge is the goal, not a failure.

## Local gate — run all of this before calling a feature done

```
ruff check .
mypy .                        # or pyright
pytest                        # FAST local tier: unit, fake-driver .feature scenarios, golden-master, mutation — seconds
pytest -m mutation            # tier-3 mutation corpus — must be >= 95% (see §5.3)
python scripts/check_genericity.py
```

**Test tiering (§5.1 decision).** A bare `pytest` runs only the fast in-process tier: `pyproject.toml`'s `addopts` deselects the two slow tiers — `browser` (launches a real Chromium) and `integration` (needs a live docker archetype). This keeps the local edit-run loop fast; **CI runs the full suite** via `pytest -m ""` (empty marker expression = everything), so the browser tier and, with the container up, the Juice Shop end-to-end still gate every PR. When your change touches a browser-tier or integration path, exercise it locally before the PR — the fast gate will *not* have run it:

```
pytest -m browser             # the real-Chromium scenarios (slow)
pytest -m integration         # docker-archetype end-to-end (needs the bench up; skips if not)
pytest -m ""                  # everything, exactly as CI runs it
```

The `browser` marker is applied per *scenario* via a Gherkin `@browser` tag on the browser-tier scenarios (most step files are mixed — a browser scenario beside network-free tier-1 ones), not as a file-level `pytestmark`. A change that touches tier 3 must report the mutation-corpus success rate in the PR description.

**Docs consistency is part of the gate, not just self-review.** Before calling a feature done, confirm the whole documentation set still describes what actually ships — the automated checks above cannot catch a stale sentence. At every gate, re-read and reconcile, for anything the change touched:

- `README.md` — the human-facing front door (hero sentence, quickstart, feature/capability claims). A capability that changed behavior, gained a flag, or shipped a new signal must not leave the README describing the old shape.
- `docs/ROADMAP.md` — the *what/why* source of truth: decision notes for the slice, `§9` backlog items marked delivered when delivered, and no claim the code now contradicts.
- `CLAUDE.md` — this file: if the workflow, layout, or non-negotiables actually changed, update it (and flag any conflict with ROADMAP.md, which wins).
- `.feature` files and `features/README.md`, docstrings, and any `CONTRIBUTING.md`/config comments the change reached.

Treat a doc that no longer matches the code as a gate failure to fix before the PR, exactly like a failing test — and say in the PR description what docs you checked and reconciled. "Docs unaffected" is a valid outcome only after actually looking.

### Audience matters: user-facing text vs internal text

Not every reader is a contributor. When you edit docs, help text, summaries, errors, or labels, decide first whether the audience is:

- a **user/operator** — someone writing a config and running Spoor; or
- a **contributor/maintainer** — someone working on the codebase itself.

For **user-facing surfaces** (`README.md`, CLI help/output, config comments users copy, operator-facing summaries/errors):

- Write so the text stands on its own; a user must not need `docs/ROADMAP.md` to decode it.
- Do **not** use unexplained section references like `§0`, `§2a`, `§2d`, etc. in the primary wording.
- Do **not** rely on roadmap-phase language (`Phase 1`, `Phase 3.5`, "layer 4") unless the user truly needs that distinction to operate the tool.
- Say the meaning directly in plain language ("config file", "browser rendering", "run summary", "observed API spec") rather than pointing at internal taxonomy.
- If a roadmap citation is genuinely useful, keep it secondary — after the plain-language explanation, not instead of it.

For **internal text** (`CLAUDE.md`, `docs/ROADMAP.md`, code comments, maintainer-facing docstrings, contributor docs), section citations like `§2e` are fine and often preferred because they tie behavior back to the source-of-truth decision record.

## Expected repo layout

```
spoor/
  core/            # resolution tiers, escalation dispatcher, interaction executor — §0 applies here
  recognizers/     # pluggable platform-convention table
  api_discovery/   # §2b
  signals/         # §2c
  operational/     # §2d
  exploration/     # §2e
  serving/         # §2f (mcp + api)
  testgen/         # §2g
  security/        # §2h — redaction, sandbox registry
features/          # .feature files, one per capability
tests/             # step definitions, unit tests, property-based tests, golden-master tests
fixtures/          # static HTML fixtures + docker-compose for the archetype apps (§5.1)
docs/
  ROADMAP.md
scripts/
  check_genericity.py
```

## When in doubt

Re-read the relevant ROADMAP.md section before guessing. If something a task asks for isn't covered by ROADMAP.md or would touch one of the non-negotiables above, stop and ask rather than deciding unilaterally — that document exists precisely so decisions like these don't get made ad hoc, one PR at a time.
