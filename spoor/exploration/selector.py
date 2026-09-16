"""Resolve a state-selector to exactly one anchor state (ROADMAP.md §2e).

The pure core of anchor selection for the resume capability (§2e "v2" — see the
resume design note). A resume run begins from a state an earlier run mapped, and
because Spoor is config/CLI-driven the user names that anchor with a *selector*
rather than a raw SHA-256 state id. This module is the resolution decision alone:
given a set of candidate states and one or more constraints, return the single
state that satisfies all of them — or, honestly, that none or several do.

Four constraint kinds, combinable (all must hold): `IdPrefix` (a git-style
state-id prefix), `TitleIs` (the wiki's human-readable title, exact), `UrlIs` (the
route the state lives at, exact), and `PathIs` (the role+name action sequence that
reaches the state). `parse_selector` reads the flat `kind:value` form used on the
CLI for the three single-value kinds; a path constraint is built structurally
(from config), since an action name can contain the flat form's delimiters.

Resolution never guesses (parity with the serving layer's stance on an unmapped
URL): exactly one match resolves; zero is *unmatched*; several is *ambiguous* with
the candidates carried back so the caller can list them and the user can narrow.
`graph_candidates` builds the candidate set from an in-memory `ExplorationGraph`
(id, redacted title, and root-relative path; `url:` awaits a per-state-URL
decision — see the resume design note); building it from the persisted on-disk map
is a further slice. Nothing here is site-specific (§0): one grammar resolves for
every target.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from spoor.exploration.graph import ExplorationGraph, paths_from_root
from spoor.security.redaction import redact


class SelectorError(ValueError):
    """A selector string is malformed (no `kind:value` shape, or an unknown kind)."""


@dataclass(frozen=True)
class AnchorCandidate:
    """One state a selector may resolve to, with the facts a selector matches on.

    `state_id` is the canonical SHA-256 id (always known). `title` and `url` are
    optional because the persisted map does not carry them yet (§2e resume note);
    a constraint over a field a candidate lacks simply does not match it. `path` is
    the (role, name) action sequence from the root state that reaches this one
    (empty for the root), the same shape reset-and-replay drives.
    """

    state_id: str
    title: str | None = None
    url: str | None = None
    path: tuple[tuple[str, str], ...] = ()


class Constraint(Protocol):
    """One condition a candidate must satisfy; `matches` is the whole contract."""

    def matches(self, candidate: AnchorCandidate) -> bool: ...

    def describe(self) -> str: ...


@dataclass(frozen=True)
class IdPrefix:
    """Match candidates whose state id starts with this (non-empty) prefix."""

    prefix: str

    def matches(self, candidate: AnchorCandidate) -> bool:
        return candidate.state_id.startswith(self.prefix)

    def describe(self) -> str:
        return f"id:{self.prefix}"


@dataclass(frozen=True)
class TitleIs:
    """Match candidates whose title equals this text exactly (never the None case)."""

    title: str

    def matches(self, candidate: AnchorCandidate) -> bool:
        return candidate.title is not None and candidate.title == self.title

    def describe(self) -> str:
        return f"title:{self.title}"


@dataclass(frozen=True)
class UrlIs:
    """Match candidates whose route equals this url exactly (never the None case)."""

    url: str

    def matches(self, candidate: AnchorCandidate) -> bool:
        return candidate.url is not None and candidate.url == self.url

    def describe(self) -> str:
        return f"url:{self.url}"


@dataclass(frozen=True)
class PathIs:
    """Match the candidate reached by exactly this (role, name) action sequence."""

    steps: tuple[tuple[str, str], ...]

    def matches(self, candidate: AnchorCandidate) -> bool:
        return candidate.path == self.steps

    def describe(self) -> str:
        rendered = ">".join(f"{role}={name}" for role, name in self.steps)
        return f"path:{rendered}"


# The flat-form kinds `parse_selector` understands; path is built structurally.
_FLAT_KINDS = ("id", "title", "url")


def parse_selector(text: str) -> Constraint:
    """Parse one flat `kind:value` selector into a constraint.

    Splits on the first colon so a value may itself contain colons (a title or a
    url routinely does). Recognizes `id:`, `title:`, `url:`; a string with no colon,
    an empty value, or an unknown kind raises `SelectorError`. Path selectors are
    not a flat kind — an action name can hold `:`, `=`, and `>` — so they are
    constructed as `PathIs` from structured config rather than parsed from here.
    """
    kind, sep, value = text.partition(":")
    if not sep or not value:
        raise SelectorError(
            f"selector {text!r} is not of the form kind:value "
            f"(expected one of {', '.join(_FLAT_KINDS)})"
        )
    if kind == "id":
        return IdPrefix(value)
    if kind == "title":
        return TitleIs(value)
    if kind == "url":
        return UrlIs(value)
    raise SelectorError(
        f"unknown selector kind {kind!r} (expected one of {', '.join(_FLAT_KINDS)})"
    )


@dataclass(frozen=True)
class AnchorResolution:
    """The outcome of resolving constraints against candidates.

    `matches` holds every candidate satisfying *all* constraints, in the candidate
    order given (deterministic). Zero is unmatched, one resolves, more is ambiguous
    — the caller turns unmatched/ambiguous into an error listing `matches`, and only
    reads `state_id` when `is_resolved`.
    """

    matches: tuple[AnchorCandidate, ...] = field(default_factory=tuple)

    @property
    def is_resolved(self) -> bool:
        return len(self.matches) == 1

    @property
    def is_unmatched(self) -> bool:
        return len(self.matches) == 0

    @property
    def is_ambiguous(self) -> bool:
        return len(self.matches) > 1

    @property
    def state_id(self) -> str:
        """The resolved state id; valid only when `is_resolved`."""
        if not self.is_resolved:
            raise ValueError(
                f"selector did not resolve to one state (matched {len(self.matches)})"
            )
        return self.matches[0].state_id


def resolve_anchor(
    constraints: Sequence[Constraint],
    candidates: Sequence[AnchorCandidate],
) -> AnchorResolution:
    """Return the candidates satisfying every constraint (AND), in candidate order.

    At least one constraint is required — an empty constraint set would match every
    candidate and is a caller error, not an anchor — so it raises `SelectorError`.
    The result never guesses: the caller inspects `is_resolved`/`is_unmatched`/
    `is_ambiguous` and, when not resolved, reports the matched candidates so the
    user can narrow the selector.
    """
    if not constraints:
        raise SelectorError("an anchor selector needs at least one constraint")
    matched = tuple(
        candidate
        for candidate in candidates
        if all(constraint.matches(candidate) for constraint in constraints)
    )
    return AnchorResolution(matches=matched)


def graph_candidates(graph: ExplorationGraph) -> list[AnchorCandidate]:
    """Turn every state in an exploration graph into a resolvable anchor candidate.

    The adapter feeding `resolve_anchor` from a real run (§2e resume). One candidate
    per state, in the graph's state (insertion) order so the root comes first:

    - `state_id` is the state id (always present).
    - `title` is the state's captured page title, redacted with the same primitive
      the wiki uses before sharing anything (§2h) — so a token that leaked into a
      title never reaches a selector or an error listing. A state with no captured
      signals, or an empty title, yields `None` (anchorable by id or path only).
    - `path` is the shortest reset-and-replay action sequence from the root, as
      (role, name) steps (the root's is empty), via `paths_from_root`.
    - `url` is left `None`: a state is DOM-identity only and records no route, so
      `url:` cannot resolve against a graph. Populating it is a separate decision
      slice (see the resume design note), not a silent omission here.

    Nothing is site-specific (§0): every graph is read the same way.
    """
    paths = paths_from_root(graph)
    candidates: list[AnchorCandidate] = []
    for state_id in graph.states:
        node = graph.node(state_id)
        raw_title = node.signals.title if node.signals else ""
        title = redact(raw_title) if raw_title else None
        path = tuple(
            (action.role, action.name) for action in paths.get(state_id, [])
        )
        candidates.append(
            AnchorCandidate(state_id=state_id, title=title, url=None, path=path)
        )
    return candidates
