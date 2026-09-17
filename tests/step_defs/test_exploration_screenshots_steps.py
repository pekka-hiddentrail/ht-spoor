"""Step definitions for features/exploration_screenshots.feature (§2e, slice 8b).

Exercised in-process: a tiny deterministic fake app, a fake driver that can hand back a
distinct fake "screenshot" per screen, the real explorer streaming each image to disk as
it is captured and keeping only a filename reference (§2e slice 8f), and the real
`render_wiki` embedding those references. No browser and no real PNGs — the bytes only
need to be distinct and to round-trip to disk, which is all the contract
requires; the live capture is proven by the integration test. State names double
as the friendly key; the graph is keyed by the abstract id.
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
from spoor.exploration.explorer import explore
from spoor.exploration.screenshot_store import ImageRef
from spoor.exploration.state import state_id
from spoor.exploration.wiki import render_wiki

scenarios("exploration_screenshots.feature")


class _FakeApp:
    """Two screens linked by one action; each screen has a distinct fake screenshot."""

    def __init__(self) -> None:
        self.root = ""
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, ActionableElement], str] = {}

    def link(self, frm: str, label: str, to: str) -> None:
        action = ActionableElement(role="button", name=label, backend_node_id=1)
        self._actions.setdefault(frm, []).append(action)
        self._actions.setdefault(to, [])
        self._transitions[(frm, action)] = to

    def html(self, name: str) -> str:
        return f"<html><body><h1>{name}</h1></body></html>"

    def ax_nodes(self, name: str) -> list[dict[str, object]]:
        return [
            {
                "role": {"value": a.role},
                "name": {"value": a.name},
                "ignored": False,
                "backendDOMNodeId": a.backend_node_id,
            }
            for a in self._actions.get(name, [])
        ]

    def next_state(self, name: str, action: ActionableElement) -> str:
        return self._transitions[(name, action)]

    def screenshot_of(self, name: str) -> bytes:
        return f"PNG-of-{name}".encode()

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _FakeDriver:
    """A screenshot-capable BrowserDriver over a _FakeApp."""

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
        self._current = self._app.next_state(self._current, action)

    def capture_signals(self) -> StateSignals:
        return StateSignals(ax_node_count=1, title=self._current)

    def screenshot(self) -> bytes | None:
        return self._app.screenshot_of(self._current)


@pytest.fixture
def context() -> dict[str, Any]:
    return {"app": _FakeApp()}


def _explore(context: dict[str, Any], tmp_path: Path, *, capture: bool) -> None:
    app: _FakeApp = context["app"]
    # The wiki directory is fixed up front and doubles as the screenshot directory: the
    # explorer streams each image straight into it as it is captured (§2e slice 8f), and
    # the wiki is later rendered into the same dir so the references resolve.
    out = tmp_path / "wiki"
    context["out_dir"] = out
    sink: dict[str, ImageRef] | None = {} if capture else None
    context["shots"] = sink
    context["graph"] = explore(
        _FakeDriver(app),
        target="http://localhost:8000/",
        controller=RunController(RunBudget()),
        declared_sandbox=True,
        screenshots=sink,
        screenshot_dir=out,
    )


# --- Given ---------------------------------------------------------------


@given(
    parsers.parse(
        'a sandbox app with screens "{home}" and "{menu}" linked by "{label}"'
    )
)
def app_two_screens(context: dict[str, Any], home: str, menu: str, label: str) -> None:
    app: _FakeApp = context["app"]
    app.root = home
    app.link(home, label, menu)


@given("I explored it with screenshot capture on")
def explored_on(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=True)


@given("I explored it with screenshot capture off")
def explored_off(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=False)


# --- When ----------------------------------------------------------------


@when("I explore it with screenshot capture on")
def explore_on(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=True)


@when("I explore it with screenshot capture off")
def explore_off(context: dict[str, Any], tmp_path: Path) -> None:
    _explore(context, tmp_path, capture=False)


@when("I render the wiki to disk")
def render_to_disk(context: dict[str, Any]) -> None:
    render_wiki(
        context["graph"],
        context["out_dir"],
        target="http://localhost:8000/",
        screenshots=context.get("shots"),
    )


# --- helpers -------------------------------------------------------------


def _state_index(context: dict[str, Any], name: str) -> int:
    return context["graph"].states.index(context["app"].state_id_of(name))


def _state_page(context: dict[str, Any], name: str) -> str:
    path = context["out_dir"] / "states" / f"state-{_state_index(context, name)}.html"
    return path.read_text(encoding="utf-8")


# --- Then: capture sink --------------------------------------------------


@then(parsers.parse('a screenshot was captured for "{name}"'))
def captured_for(context: dict[str, Any], name: str) -> None:
    app: _FakeApp = context["app"]
    shots = context["shots"]
    assert shots is not None
    sid = app.state_id_of(name)
    assert sid in shots, f"no screenshot captured for {name}"
    # The sink holds a filename reference; the image was streamed to disk under it as
    # it was captured (§2e slice 8f) — the bytes live on disk, not in memory.
    index = context["graph"].states.index(sid)
    ref = shots[sid]
    assert ref == ImageRef(f"screenshots/state-{index}.png")
    assert (context["out_dir"] / ref.src).read_bytes() == app.screenshot_of(name)


@then("no screenshots were captured")
def none_captured(context: dict[str, Any]) -> None:
    assert context["shots"] is None


@then("the screenshot sink holds a file reference for each screen, not image bytes")
def sink_holds_references(context: dict[str, Any]) -> None:
    shots = context["shots"]
    assert shots, "expected at least one captured screenshot reference"
    for value in shots.values():
        assert isinstance(value, ImageRef), f"sink holds {type(value)!r}, not a ref"
        assert value.src.endswith(".png"), f"ref {value!r} is not an image filename"


@then("each referenced screenshot file already exists on disk")
def referenced_files_exist(context: dict[str, Any]) -> None:
    out_dir: Path = context["out_dir"]
    for value in context["shots"].values():
        assert (out_dir / value.src).is_file(), f"streamed image {value} is not on disk"


# --- Then: written wiki --------------------------------------------------


@then(parsers.parse('the wiki directory contains a screenshot image for "{name}"'))
def dir_has_image(context: dict[str, Any], name: str) -> None:
    path = _image_path(context, name)
    assert path.is_file(), f"no image file for {name}"
    assert path.read_bytes() == context["app"].screenshot_of(name)


@then("the wiki directory contains no screenshot images")
def dir_has_no_images(context: dict[str, Any]) -> None:
    pngs = list(context["out_dir"].rglob("*.png"))
    assert pngs == [], f"unexpected image files: {pngs}"


@then(parsers.parse('the state page for "{name}" embeds its screenshot image'))
def page_embeds(context: dict[str, Any], name: str) -> None:
    index = _state_index(context, name)
    # A state page sits in states/, so its screenshot src climbs one level (slice 6g).
    assert f'src="../screenshots/state-{index}.png"' in _state_page(context, name)


@then("no wiki page embeds a screenshot image")
def no_page_embeds(context: dict[str, Any]) -> None:
    # Pages live in subfolders now (slice 6g), so walk the tree, not just the root.
    for path in context["out_dir"].rglob("*.html"):
        assert "<img" not in path.read_text(encoding="utf-8"), f"image in {path.name}"


# --- Then: images grouped in their own subfolder -------------------------


def _image_path(context: dict[str, Any], name: str) -> Path:
    index = _state_index(context, name)
    return context["out_dir"] / "screenshots" / f"state-{index}.png"


@then(parsers.parse('the screenshot image for "{name}" is under the "{sub}" subfolder'))
def image_in_subfolder(context: dict[str, Any], name: str, sub: str) -> None:
    path = _image_path(context, name)
    assert path.parent.name == sub, f"expected image under {sub}/, got {path.parent}"
    assert path.is_file(), f"no image under {sub}/ for {name}"


@then("no screenshot image sits flat in the wiki root")
def no_flat_image(context: dict[str, Any]) -> None:
    flat = list(context["out_dir"].glob("*.png"))
    assert flat == [], f"images should live in the subfolder, found flat: {flat}"
