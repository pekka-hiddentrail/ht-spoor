"""Core resolution tiers, escalation dispatcher, interaction executor (ROADMAP.md §2).

HARD RULE (§0 / CLAUDE.md): nothing in this package may hardcode knowledge of a
specific website — no `if domain == "..."` branches, no site-specific selectors
or endpoint paths. Site-specific behaviour is either runtime-learned (the
per-domain cache) or lives in `spoor.recognizers`. Enforced by
`scripts/check_genericity.py` in CI.
"""
