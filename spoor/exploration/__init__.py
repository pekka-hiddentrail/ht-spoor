"""Exploration mode: mapping the full interaction space (ROADMAP.md §2e, v2).

Autonomous state-graph discovery and wiki generation.

NON-NEGOTIABLE (§2e / CLAUDE.md): destructive/irreversible actions are
sandbox-only and non-configurable — permitted only against a registry match
(localhost / 127.0.0.1, or an explicit `sandbox: true`), always skipped and
logged as skipped against anything else. No flag relaxes this.
"""
