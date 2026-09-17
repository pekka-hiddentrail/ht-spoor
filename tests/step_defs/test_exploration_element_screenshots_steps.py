"""Step definitions for features/exploration_element_screenshots.feature (§2e, 8d).

Exercised in-process, like the full-page screenshot steps: a tiny deterministic fake
screen exposing two actionable elements, a fake driver that hands back a distinct fake
"clip" per element, the real explorer streaming each clip to disk as it is captured and
keeping only a filename reference (§2e slice 8f), and the real `render_wiki` embedding
those references in each element's Actions row. No browser and no real PNGs — the bytes
only need to be distinct and to round-trip to disk, which is all the capture-and-write
contract requires; the live clip is proven by the integration test. Element names
double as the friendly key.
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

scenarios("exploration_element_screenshots.feature")


class _FakeApp:
    """One screen exposing a set of actionable elements, each with a distinct clip."""

    def __init__(self) -> None:
        self.root = "home"
        self._elements: list[ActionableElement] = []

    def add_element(self, role: str, name: str) -> None:
        node_id = len(self._elements) + 1
        self._elements.append(
            ActionableElement(role=role, name=name, backend_node_id=node_id)
        )

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

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _FakeDriver:
    """An element-screenshot-capable BrowserDriver over a _FakeApp."""

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
        # A single-screen app: activating an element changes nothing, so the walk
        # stays on "home" — enough to exercise per-element capture, no transitions.
        return None

    def capture_signals(self) -> StateSignals:
        return StateSignals(ax_node_count=1, title=self._current)

    def element_screenshot(self, action: ActionableElement) -> bytes | None:
        return self._app.clip_of(action.name)


@pytest.fixture
def context() -> dict[str, Any]:
    return {"app": _FakeApp()}


def _explore(context: dict[str, Any], tmp_path: Path, *, capture: bool) -> None:
    app: _FakeApp = context["app"]
    # The wiki directory is fixed up front and doubles as the screenshot directory: the
    # explorer streams each clip straight into it as it is captured (§2e slice 8f).
    out = tmp_path / "wiki"
    context["out_dir"] = out
    sink: dict[str, list[ElementShot]] | None = {} if capture else None
    context["element_shots"] = sink
    context["graph"] = explore(
        _FakeDriver(app),
        target="http://localhost:8000/",
        controller=RunController(RunBudget()),
        declared_sandbox=True,
        element_screenshots=sink,
        screenshot_dir=out,
    )


# --- Given ---------------------------------------------------------------


@given(
    parsers.parse(
        'a sandbox screen with a "{dropdown}" dropdown and a "{button}" button'
    )
)
def screen_with_elements(context: dict[str, Any], dropdown: str, button: str) -> None:
    app: _FakeApp = context["app"]
    app.add_element("combobox", dropdown)
    app.add_element("button", button)


@given("I explored it with element-screenshot capture on")
def explored_on(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=True)


@given("I explored it with element-screenshot capture off")
def explored_off(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=False)


# --- When ----------------------------------------------------------------


@when("I explore it with element-screenshot capture on")
def explore_on(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=True)


@when("I explore it with element-screenshot capture off")
def explore_off(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=False)


@when("I render the wiki to disk")
def render_to_disk(context: dict[str, Any]) -> None:
    render_wiki(
        context["graph"],
        context["out_dir"],
        target="http://localhost:8000/",
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


@then(parsers.parse('an element screenshot was captured for "{name}"'))
def captured_for(context: dict[str, Any], name: str) -> None:
    app: _FakeApp = context["app"]
    sink = context["element_shots"]
    assert sink is not None
    shots = sink[app.state_id_of("home")]
    index = _element_index(context, name)
    # The shot holds a filename reference; the clip was streamed to disk under it as it
    # was captured (§2e slice 8f), so the bytes live on disk, not in memory.
    ref = shots[index].clip
    assert ref == ImageRef(f"screenshots/state-0-el-{index}.png"), f"no clip for {name}"
    assert (context["out_dir"] / ref.src).read_bytes() == app.clip_of(name)


@then("no element screenshots were captured")
def none_captured(context: dict[str, Any]) -> None:
    assert context["element_shots"] is None


@then("each captured element clip is a file reference on disk, not image bytes")
def clips_are_references_on_disk(context: dict[str, Any]) -> None:
    sink = context["element_shots"]
    assert sink, "expected at least one captured element clip"
    out_dir: Path = context["out_dir"]
    seen_clip = False
    for shots in sink.values():
        for shot in shots:
            if shot.clip is None:
                continue
            seen_clip = True
            assert isinstance(shot.clip, ImageRef), "clip is not a reference"
            assert (out_dir / shot.clip.src).is_file(), f"clip {shot.clip} not on disk"
    assert seen_clip, "no element clip reference was captured"


# --- Then: written wiki --------------------------------------------------


@then(parsers.parse('the Actions row for "{name}" embeds its element screenshot'))
def row_embeds(context: dict[str, Any], name: str) -> None:
    index = _element_index(context, name)
    # A state page sits in states/, so its element clip src climbs one level (slice 6g).
    src = f'src="../screenshots/state-0-el-{index}.png"'
    assert src in _home_page(context), f"{name} row does not embed {src}"


@then(parsers.parse('every element image sits under the "{sub}" subfolder'))
def images_in_subfolder(context: dict[str, Any], sub: str) -> None:
    images = list(context["out_dir"].rglob("*.png"))
    assert images, "expected at least one element image"
    assert all(p.parent.name == sub for p in images), f"not all under {sub}/: {images}"
    assert not list(context["out_dir"].glob("*.png")), "an image sits flat in the root"


@then("no wiki page embeds an element screenshot")
def no_page_embeds(context: dict[str, Any]) -> None:
    for path in context["out_dir"].glob("*.html"):
        assert "<img" not in path.read_text(encoding="utf-8"), f"image in {path.name}"
    assert not list(context["out_dir"].rglob("*.png")), "images were written"
