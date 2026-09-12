"""Pluggable platform-convention recognizers (ROADMAP.md §0, §2).

The one place site/platform-specific strings are allowed: an opt-in, swappable
table of known platform conventions (e.g. "looks like Shopify -> try
`/products.json`") that generalise across every store on that platform, never
logic baked into the escalation path. This package is excluded from the §0
genericity check for exactly that reason.
"""
