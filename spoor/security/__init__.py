"""Data handling, secret redaction, sandbox registry (ROADMAP.md §2h, §2e).

NON-NEGOTIABLES (§2h / CLAUDE.md):
- Secret redaction on shared output is on by default. Known secret patterns are
  redacted before anything reaches the output pipeline, the wiki, or an MCP/API
  response. Raw, unredacted captures stay in the local-only cache; exporting
  them is a separate, explicit user action.
- The sandbox registry decides whether a target counts as sandbox (localhost /
  127.0.0.1, or explicit `sandbox: true`), gating §2e destructive actions.
"""
