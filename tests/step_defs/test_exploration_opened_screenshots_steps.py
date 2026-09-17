"""Step definitions for features/exploration_opened_screenshots.feature (§2e, 8e).

Exercised in-process like the 8d element-clip steps: a tiny deterministic fake screen
exposing a few actionable elements, a fake driver that hands back a distinct fake
"opened" capture per element, the real explorer streaming each image to disk as it
is captured and keeping only a filename reference (§2e slice 8f), and the real
`render_wiki` embedding references in each element's Actions row. No browser and no
real PNGs — the bytes need to be distinct and to round-trip to disk; the live opened
capture (click, settle, shot, Escape-restore) is proven by the integration test. Two
driver flavours prove the granular protocol: one that can open disclosure elements, one
that can only clip and leaves every `opened` None. Element names double as the friendly
key.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.actuation import ActuationVerdict, Verdict
from spoor.exploration.capture import StateSignals
from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.explorer import ElementShot, explore
from spoor.exploration.screenshot_store import ImageRef
from spoor.exploration.state import state_id
from spoor.exploration.wiki import render_wiki

scenarios("exploration_opened_screenshots.feature")

_SANDBOX_TARGET = "http://localhost:8000/"
_REAL_TARGET = "https://shop.example.com/"


class _FakeApp:
    """One screen exposing a set of actionable elements, each with distinct captures."""

    def __init__(self) -> None:
        self.root = "home"
        self._elements: list[ActionableElement] = []

    def add_element(self, role: str, name: str) -> None:
        node_id = len(self._elements) + 1
        self._elements.append(
            ActionableElement(role=role, name=name, backend_node_id=node_id)
        )

    def element_names(self) -> list[str]:
        return [el.name for el in self._elements]

    def html(self, name: str) -> str:
        return f"<html><body><h1>{name}</h1></body></html>"

    def ax_nodes(self, name: str) -> list[dict[str, object]]:
        return [
            {
                "role": {"value": el.role},
                "name": {"value": el.name},
                "ignored": False,
                "backendDOMNodeId": el.backend_node_id,
            }
            for el in self._elements
        ]

    def clip_of(self, name: str) -> bytes:
        return f"CLIP-of-{name}".encode()

    def opened_of(self, name: str) -> bytes:
        return f"OPENED-of-{name}".encode()

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _ClipOnlyDriver:
    """A BrowserDriver that can clip elements but cannot open them (8d capability)."""

    def __init__(self, app: _FakeApp) -> None:
        self._app = app
        self._current = app.root

    def reset(self) -> None:
        self._current = self._app.root

    def state_html(self) -> str:
        return self._app.html(self._current)

    def ax_nodes(self) -> Sequence[Mapping[str, object]]:
        return self._app.ax_nodes(self._current)

    def probe(self, action: ActionableElement) -> ActuationVerdict:
        return ActuationVerdict(Verdict.ACTUATE)

    def perform(self, action: ActionableElement) -> None:
        # Single-screen app: activating anything changes nothing, so no transitions.
        return None

    def capture_signals(self) -> StateSignals:
        return StateSignals(ax_node_count=1, title=self._current)

    def element_screenshot(self, action: ActionableElement) -> bytes | None:
        return self._app.clip_of(action.name)


class _OpeningDriver(_ClipOnlyDriver):
    """Also opens a disclosure element and captures what it reveals (8e capability)."""

    def opened_screenshot(self, action: ActionableElement) -> bytes | None:
        return self._app.opened_of(action.name)


@pytest.fixture
def context() -> dict[str, Any]:
    app = _FakeApp()
    app.add_element("combobox", "Currency")
    app.add_element("button", "Delete")
    return {
        "app": app,
        "driver_cls": _OpeningDriver,
        "sandbox": True,
        "target": _SANDBOX_TARGET,
    }


def _explore(context: dict[str, Any], tmp_path: Path, *, capture: bool) -> None:
    app: _FakeApp = context["app"]
    # The wiki directory is fixed up front and doubles as the screenshot directory: the
    # explorer streams each opened image straight into it as it is captured (§2e 8f).
    out = tmp_path / "wiki"
    context["out_dir"] = out
    sink: dict[str, list[ElementShot]] | None = {} if capture else None
    context["element_shots"] = sink
    context["graph"] = explore(
        context["driver_cls"](app),
        target=context["target"],
        controller=RunController(RunBudget()),
        declared_sandbox=context["sandbox"],
        element_screenshots=sink,
        screenshot_dir=out,
    )


# --- Given ---------------------------------------------------------------


# The Background line is fixed by the feature's wording; the elements it names are added
# by the `context` fixture, so this step only asserts the screen is set up as described.
@given(
    parsers.parse(
        'a sandbox screen with a "{dropdown}" dropdown and a "{button}" button'
    )
)
def screen_with_elements(context: dict[str, Any], dropdown: str, button: str) -> None:
    names = context["app"].element_names()
    assert dropdown in names and button in names


@given(parsers.parse('a "{name}" dropdown on the screen'))
def add_dropdown(context: dict[str, Any], name: str) -> None:
    context["app"].add_element("combobox", name)


@given("the target is a real site, not a sandbox")
def real_target(context: dict[str, Any]) -> None:
    context["sandbox"] = False
    context["target"] = _REAL_TARGET


@given("the driver can clip elements but cannot open them")
def clip_only_driver(context: dict[str, Any]) -> None:
    context["driver_cls"] = _ClipOnlyDriver


@given("I explored it with opened-contents capture on")
def explored_on(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=True)


@given("I explored it with opened-contents capture off")
def explored_off(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=False)


# --- When ----------------------------------------------------------------


@when("I explore it with opened-contents capture on")
def explore_on(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=True)


@when("I explore it with opened-contents capture off")
def explore_off(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=False)


@when("I render the wiki to disk")
def render_to_disk(context: dict[str, Any]) -> None:
    render_wiki(
        context["graph"],
        context["out_dir"],
        target=context["target"],
        element_screenshots=context.get("element_shots"),
    )


# --- helpers -------------------------------------------------------------


def _element_index(context: dict[str, Any], name: str) -> int:
    home_id = context["app"].state_id_of("home")
    actions = context["graph"].node(home_id).actions
    return [a.name for a in actions].index(name)


def _home_page(context: dict[str, Any]) -> str:
    return (
        context["out_dir"] / "states" / "state-0.html"
    ).read_text(encoding="utf-8")


# --- Then: capture sink --------------------------------------------------


@then(parsers.parse('an opened-contents screenshot was captured for "{name}"'))
def opened_captured_for(context: dict[str, Any], name: str) -> None:
    app: _FakeApp = context["app"]
    sink = context["element_shots"]
    assert sink is not None
    shots = sink[app.state_id_of("home")]
    index = _element_index(context, name)
    # The shot holds a filename reference; the image was streamed to disk under it
    # as it was captured (§2e slice 8f), so the bytes live on disk, not in memory.
    ref = shots[index].opened
    assert ref == ImageRef(f"screenshots/state-0-el-{index}-opened.png"), (
        f"no opened capture for {name}"
    )
    assert (context["out_dir"] / ref.src).read_bytes() == app.opened_of(name)


@then(parsers.parse('no opened-contents screenshot was captured for "{name}"'))
def no_opened_for(context: dict[str, Any], name: str) -> None:
    app: _FakeApp = context["app"]
    sink = context["element_shots"]
    assert sink is not None
    shots = sink[app.state_id_of("home")]
    index = _element_index(context, name)
    assert shots[index].opened is None, f"unexpected opened capture for {name}"


@then("no opened-contents screenshots were captured")
def none_opened(context: dict[str, Any]) -> None:
    sink = context["element_shots"]
    if sink is None:
        return  # capture was off — nothing was captured at all
    assert all(
        shot.opened is None for shots in sink.values() for shot in shots
    ), "an opened capture was taken"


# --- Then: written wiki --------------------------------------------------


@then(
    parsers.parse('the Actions row for "{name}" embeds its opened-contents screenshot')
)
def row_embeds_opened(context: dict[str, Any], name: str) -> None:
    index = _element_index(context, name)
    # A state page sits in states/, so its opened-clip src climbs one level (slice 6g).
    src = f'src="../screenshots/state-0-el-{index}-opened.png"'
    assert src in _home_page(context), f"{name} row does not embed {src}"


@then(parsers.parse('every element image sits under the "{sub}" subfolder'))
def images_in_subfolder(context: dict[str, Any], sub: str) -> None:
    images = list(context["out_dir"].rglob("*.png"))
    assert images, "expected at least one element image"
    assert all(p.parent.name == sub for p in images), f"not all under {sub}/: {images}"
    assert not list(context["out_dir"].glob("*.png")), "an image sits flat in the root"


@then("no wiki page embeds an opened-contents screenshot")
def no_page_embeds_opened(context: dict[str, Any]) -> None:
    for path in context["out_dir"].glob("*.html"):
        assert "-opened.png" not in path.read_text(encoding="utf-8"), (
            f"opened image embedded in {path.name}"
        )
    assert not list(context["out_dir"].rglob("*-opened.png")), "opened images written"
