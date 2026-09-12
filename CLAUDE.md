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

BDD scenarios sit *above* the rest of the test pyramid, not instead of it. Property-based/mutation testing (`hypothesis`, §5.3) and golden-master diffing (§5.4) stay in place for tier 3's internals and regression safety — those validate "generate hundreds of variants and check a statistical property," which isn't a shape Gherkin scenarios are suited for.

## Local gate — run all of this before calling a feature done

```
ruff check .
mypy .                        # or pyright
pytest                        # unit tests, .feature scenarios, golden-master regression
pytest -m mutation            # tier-3 mutation corpus — must be >= 95% (see §5.3)
python scripts/check_genericity.py
```

A change that touches tier 3 must report the mutation-corpus success rate in the PR description.

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
