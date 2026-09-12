"""Declarative extraction config model and loader (ROADMAP.md §2a).

The config schema shape is identical for every target (§0) — pointing Spoor at
a new site is a new config, never new code. The model is strict (`extra=forbid`)
so a typo'd key fails loudly rather than being silently ignored, and it carries
no tier-specific knobs: a field's `selector` is only the tier-1 starting point,
and escalation across tiers is entirely the dispatcher's concern (§2).
"""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

FieldType = Literal["string", "number"]


class FieldSpec(BaseModel):
    """One extracted field: a selector plus an optional value type."""

    model_config = ConfigDict(extra="forbid")

    selector: str
    type: FieldType = "string"


class Pagination(BaseModel):
    """How to advance past the first page — a next-link or infinite scroll."""

    model_config = ConfigDict(extra="forbid")

    next: str | None = None
    infinite_scroll: bool = False


class ExtractionConfig(BaseModel):
    """A whole extraction job: target, optional repeating `item`, fields."""

    model_config = ConfigDict(extra="forbid")

    target: str
    # When set, each field selector resolves *relative to* every matched
    # element and the run emits one record per match (ROADMAP.md §2a). When
    # absent, fields resolve against the whole document (one record per page).
    item: str | None = None
    fields: dict[str, FieldSpec]
    pagination: Pagination | None = None


def load_config(text: str) -> ExtractionConfig:
    """Parse YAML config text into a validated ExtractionConfig.

    Raises pydantic.ValidationError on a missing required field (e.g. `target`)
    or an unknown option, before anything is fetched.
    """
    data = yaml.safe_load(text)
    return ExtractionConfig.model_validate(data)
