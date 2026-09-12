# Contributing to Spoor

Thanks for helping build Spoor. Before anything else, read `docs/ROADMAP.md`
(the source of truth for *what* and *why*) and `CLAUDE.md` (*how to work here*).
If a change would touch one of the non-negotiables below, or isn't covered by
ROADMAP.md, open an issue to discuss it first — those decisions are made
deliberately in ROADMAP.md, not ad hoc in a PR.

## The one hard rule: §0 — never site-tailored

Nothing in shipped core source may hardcode knowledge of a specific website.
Site/platform-specific strings live only in `spoor/recognizers/` (the pluggable
convention table) or `fixtures/`. This is enforced automatically by
`scripts/check_genericity.py` in CI — a hardcoded hostname/domain/public IP in
core fails the build.

## Non-negotiables (see CLAUDE.md / ROADMAP.md)

Do not weaken these without an explicit human decision recorded in ROADMAP.md:

- Destructive actions during exploration (§2e) are **sandbox-only and
  non-configurable**.
- The MCP/API serving layer (§2f/§2h) is **read-only, always**.
- Secret redaction on shared output is **on by default** (§2h).
- The tier-3 mutation-corpus success rate must stay **≥95%** (§5.3) — merge-blocking.

## Workflow: BDD-first

Every named capability is developed in this order (never implementation-first):

1. Write/extend the capability's `.feature` file under `features/` (Gherkin).
2. Add/update `pytest-bdd` step definitions in `tests/`.
3. Implement.
4. Run the full local gate below.

Work happens on branches off `main`, one per change, opened as a PR.

## Local development

```
python -m pip install -e ".[dev]"   # or: uv sync
```

## Local gate — run all of this before calling a feature done

```
ruff check .
mypy .
pytest
pytest -m mutation                    # tier-3 mutation corpus — must be >= 95% (§5.3)
python scripts/check_genericity.py
```

A change that touches tier 3 must report the mutation-corpus success rate in the
PR description.
