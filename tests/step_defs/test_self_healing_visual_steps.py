"""Step definitions for features/self_healing_visual.feature (§2, §2d).

The perceptual-hash companion to the other tier-3 slices. A screenshot needs a
rendered page, so — unlike the tier-1 healing scenarios that drive an in-memory
httpx MockTransport — these run the **real** browser tier against a live loopback
server (the `live_server` fixture), with the persistent per-domain fingerprint
cache under a per-scenario temp directory (`storage.CACHE_ROOT` monkeypatched) so
a first run's visual-enriched fingerprint survives into a second run.

The dispatcher is pinned to **tier 2** here: the visual signal is only ever
captured/compared when a screenshotter is bound to a live page, which is the
browser tier's job. A plain single-record config over static HTML would otherwise
be satisfied by tier 1 and never take a screenshot, so pinning tier 2 is what puts
the slice under test at all (the mirror of the container slice pinning tier 1).

Two runs target two pages on the *same* loopback host — the original, then a
redesign. Because the fingerprint cache keys by netloc (not path), the second run
heals against the first run's stored print. The redesign renames the logo's class,
bumps its attributes, changes its `src`, and wraps it in a `<div>`, dropping the
DOM-only heal below the confidence bar; the only thing that differs between the
`same` and `diff` redesigns is whether the image still renders identically
(logo-b.png is byte-identical to logo-a.png; logo-c.png is a different picture).
Assertions are against the extracted records, the loaded fingerprint's visual
hash, and the `RunSummary`'s heal counts — never any matched text (§2h).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.core import extract
from spoor.core.config import load_config
from spoor.core.fingerprint_cache import cache_for_target
from spoor.operational.observability import RunSummary
from spoor.security import storage

scenarios("self_healing_visual.feature")

_ORIGINAL = "logo_visual_original.html"
# Both redesigns apply the same DOM churn; they differ only in the rendered image.
_SAME = "logo_visual_same.html"   # logo-b.png == logo-a.png -> appearance unchanged
_DIFF = "logo_visual_diff.html"   # logo-c.png differs -> appearance changed


@pytest.fixture
def context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, live_server: str
) -> dict[str, Any]:
    """Per-scenario state: a live loopback server + a fresh fingerprint cache."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / "cache")
    return {"base": live_server}


def _run(context: dict[str, Any], page: str) -> None:
    url = f"{context['base']}/{page}"
    cfg = load_config(f"target: {url}\n{context['config_body']}")
    # Pin to tier 2: the visual signal only exists when the browser tier binds a
    # screenshotter to the live page (tier 1 would satisfy this config and never
    # take a screenshot, leaving the slice untested).
    result = extract.run_report(cfg, tiers=(extract.Tier2Resolver(),))
    context["target"] = url
    context["result"] = result
    context["summary"] = RunSummary.from_result(result)


# --- Given ----------------------------------------------------------------


@given(
    parsers.parse(
        'a single-record config reading the "{field}" image\'s "{attr}" from "{sel}"'
    )
)
def visual_config(context: dict[str, Any], field: str, attr: str, sel: str) -> None:
    context["field"] = field
    context["config_body"] = (
        f'fields:\n  {field}: {{ selector: "{sel}", attr: "{attr}" }}\n'
    )


@given("a first browser run has recorded the logo's fingerprint")
def first_browser_run(context: dict[str, Any]) -> None:
    _run(context, _ORIGINAL)
    # The original page's selector resolves directly, so the field is filled and no
    # heal fires — this run's only job is to persist the visual-enriched print.
    assert context["result"].records[0][context["field"]] is not None
    assert context["summary"].heal_confident == 0


# --- When -----------------------------------------------------------------


@when("the logo's class and attributes change but it renders the same")
def churn_same_look(context: dict[str, Any]) -> None:
    context["redesign"] = _SAME


@when("the logo's class and attributes change and it now renders differently")
def churn_different_look(context: dict[str, Any]) -> None:
    context["redesign"] = _DIFF


@when("the config is run against the original page in the browser")
def run_original(context: dict[str, Any]) -> None:
    _run(context, _ORIGINAL)


@when("the config is run against the redesigned page in the browser")
def run_redesigned(context: dict[str, Any]) -> None:
    _run(context, context["redesign"])


# --- Then -----------------------------------------------------------------


@then("the field is extracted")
@then("the field is extracted again")
def field_extracted(context: dict[str, Any]) -> None:
    records = context["result"].records
    assert len(records) == 1
    assert records[0][context["field"]] is not None


@then("the field is left null")
def field_null(context: dict[str, Any]) -> None:
    records = context["result"].records
    assert len(records) == 1
    assert records[0][context["field"]] is None


@then(parsers.parse('the stored fingerprint for "{field}" carries a visual hash'))
def stored_has_visual_hash(context: dict[str, Any], field: str) -> None:
    # Reload the persisted per-domain cache the run wrote and confirm the field's
    # print carries the perceptual hash (an int), not just its DOM signals.
    stored = cache_for_target(context["target"]).get_persisted(field)
    assert stored is not None
    assert isinstance(stored.visual_hash, int)


@then(parsers.parse("the run summary reports {count:d} confident heal"))
def summary_confident(context: dict[str, Any], count: int) -> None:
    assert context["summary"].heal_confident == count


@then(parsers.parse("the run summary reports {count:d} uncertain match"))
def summary_uncertain(context: dict[str, Any], count: int) -> None:
    assert context["summary"].heal_uncertain == count
