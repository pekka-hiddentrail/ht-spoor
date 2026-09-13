"""Unit boundaries for `_coerce_number` (ROADMAP.md §2a).

The `.feature` scenario proves the end-to-end case (a huge numeral yields null);
these probe the coercion boundary directly at the grain Gherkin isn't suited for:
that both +inf and -inf overflow results are refused (not just the positive one),
and that an ordinary large-but-finite value still parses — so the finiteness guard
rejects the unrepresentable without narrowing normal coercion.
"""

from __future__ import annotations

import math

import pytest

from spoor.core.extract import _coerce_number


@pytest.mark.parametrize("text", ["9" * 400, "£" + "9" * 320])
def test_a_numeral_beyond_float_range_yields_none(text: str) -> None:
    # Would overflow to +inf, which is not valid JSON — must be treated as null.
    assert _coerce_number(text) is None


def test_a_negative_numeral_beyond_float_range_yields_none() -> None:
    # The -inf side of the same overflow, reachable via a genuine leading minus.
    assert _coerce_number("-" + "9" * 400) is None


def test_a_large_but_finite_value_still_parses() -> None:
    # The guard rejects only non-finite results; a big representable number is kept.
    value = _coerce_number("1" + "0" * 100)
    assert value is not None
    assert math.isfinite(value)
    assert value == float("1" + "0" * 100)
