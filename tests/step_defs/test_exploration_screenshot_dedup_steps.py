"""Step definitions for features/exploration_screenshot_dedup.feature (§2e, slice 8g).

Unlike the earlier screenshot slices (8b/8d/8e/8f), whose fakes hand back arbitrary
distinct byte strings, dedup and containment are *pixel* logic: the store decodes and
perceptually hashes each capture, and containment decodes the full-page picture to
search for a clip inside it. So these fakes render **real PNGs** with Pillow — a
deterministic gradient per screen, and an element clip that is an exact crop of its
page's full-page picture — so `content_key`, `perceptual_hash`, `decode` and
`find_subimage` all run for real. The explorer still streams each *new* picture to disk
and keeps only an `ImageRef`; the point here is which captures collapse to a shared file
or a crop reference and which get their own file. No browser: the live capture is proven
by the integration test. Screen names double as the friendly key.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when

from spoor.exploration.actuation import ActuationVerdict, Verdict
from spoor.exploration.capture import StateSignals
from spoor.exploration.control import RunBudget, RunController
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.explorer import ElementShot, explore
from spoor.exploration.screenshot_store import ImageRef
from spoor.exploration.state import state_id
from spoor.exploration.wiki import render_wiki

scenarios("exploration_screenshot_dedup.feature")

_TARGET = "http://localhost:8000/"

# The full-page picture is smaller than every gradient's repeat period in both axes
# (see `_gradient`), so each of its regions is unique — a crop of it appears in exactly
# one place, and `find_subimage` has a single deterministic answer.
_PAGE_W, _PAGE_H = 120, 90
# The element's rectangle inside the full-page picture (x, y, width, height), well
# within the page bounds so it is a genuine interior region, not the whole thing.
_CLIP_BOX = (30, 20, 40, 30)


def _png(pixels: np.ndarray) -> bytes:
    """Encode an ``(H, W, 3)`` uint8 RGB array as real PNG bytes (lossless)."""
    buf = io.BytesIO()
    Image.fromarray(pixels, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def _gradient(kind: str) -> np.ndarray:
    """A deterministic, non-flat RGB gradient — a real, decodable, hashable picture.

    Two distinct `kind`s differ in every channel's slope, so they are byte-different and
    perceptually far apart; within the page size each is non-periodic, so any crop of it
    is unique. Never flat (a flat image would hash to 0 and be excluded from perceptual
    matching), so the near-duplicate path is genuinely exercised.
    """
    ys, xs = np.mgrid[0:_PAGE_H, 0:_PAGE_W].astype(np.int64)
    if kind == "a":
        chans = ((xs * 2) % 256, (ys * 3) % 256, (xs + ys) % 256)
    elif kind == "b":
        chans = ((ys * 5 + 40) % 256, (xs * 7) % 256, (2 * xs + ys) % 256)
    else:  # "c" — the containment page: a third distinct, unique-region gradient.
        chans = ((xs + 2 * ys) % 256, (3 * xs) % 256, (xs * 2 + ys * 2 + 10) % 256)
    return np.stack(chans, axis=-1).astype(np.uint8)


def _near_variant(pixels: np.ndarray) -> np.ndarray:
    """`pixels` with only sub-threshold noise: byte-different, perceptually identical.

    A small patch is nudged by a few levels — enough to change the encoded bytes (so
    the byte-exact path does not fire) but far too little to move the coarse dHash past
    the store's tight bit threshold, so the two match perceptually and share a file.
    """
    near = pixels.copy()
    near[0:4, 0:4] = np.clip(near[0:4, 0:4].astype(np.int64) + 6, 0, 255).astype(
        np.uint8
    )
    return near


class _FakeApp:
    """Screens rendering real pictures, linked by actions; some screens hold an element.

    A screen's picture is real PNG bytes. An element on a screen carries its own clip
    bytes (also real PNG) and, optionally, an on-page box for the geometry path. The DOM
    (`html`) is keyed by screen name so two screens that render the *same* picture are
    still distinct states — dedup shares the image, never the state.
    """

    def __init__(self) -> None:
        self.root = "home"
        self._screens: dict[str, bytes] = {}
        self._actions: dict[str, list[ActionableElement]] = {}
        self._transitions: dict[tuple[str, ActionableElement], str] = {}
        self._clips: dict[tuple[str, str], bytes] = {}
        self._boxes: dict[tuple[str, str], tuple[int, int, int, int]] = {}
        self._next_node_id = 1

    def add_screen(self, name: str, picture: bytes) -> None:
        self._screens[name] = picture
        self._actions.setdefault(name, [])

    def _new_action(self, role: str, name: str) -> ActionableElement:
        action = ActionableElement(
            role=role, name=name, backend_node_id=self._next_node_id
        )
        self._next_node_id += 1
        return action

    def link(self, frm: str, label: str, to: str) -> None:
        action = self._new_action("button", label)
        self._actions.setdefault(frm, []).append(action)
        self._actions.setdefault(to, [])
        self._transitions[(frm, action)] = to

    def add_element(
        self,
        screen: str,
        name: str,
        clip: bytes,
        box: tuple[int, int, int, int] | None = None,
    ) -> None:
        action = self._new_action("button", name)
        self._actions.setdefault(screen, []).append(action)
        self._clips[(screen, name)] = clip
        if box is not None:
            self._boxes[(screen, name)] = box

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

    def next_state(self, name: str, action: ActionableElement) -> str | None:
        return self._transitions.get((name, action))

    def screenshot_of(self, name: str) -> bytes | None:
        return self._screens.get(name)

    def clip_of(self, screen: str, name: str) -> bytes | None:
        return self._clips.get((screen, name))

    def box_of(self, screen: str, name: str) -> tuple[int, int, int, int] | None:
        return self._boxes.get((screen, name))

    def state_id_of(self, name: str) -> str:
        return state_id(self.html(name))


class _Driver:
    """A screenshot- and clip-capable BrowserDriver that cannot report geometry."""

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
        to = self._app.next_state(self._current, action)
        if to is not None:
            self._current = to

    def capture_signals(self) -> StateSignals:
        return StateSignals(ax_node_count=1, title=self._current)

    def screenshot(self) -> bytes | None:
        return self._app.screenshot_of(self._current)

    def element_screenshot(self, action: ActionableElement) -> bytes | None:
        return self._app.clip_of(self._current, action.name)


class _GeometryDriver(_Driver):
    """Also reports each element's on-page box, so containment uses geometry (8g)."""

    def element_box(
        self, action: ActionableElement
    ) -> tuple[int, int, int, int] | None:
        return self._app.box_of(self._current, action.name)


@pytest.fixture
def context() -> dict[str, Any]:
    return {"app": _FakeApp(), "driver_cls": _Driver}


def _run(context: dict[str, Any], out: Path) -> None:
    """Explore once into `out` (streaming captures) and render the wiki into it."""
    app: _FakeApp = context["app"]
    shots: dict[str, ImageRef] = {}
    element_shots: dict[str, list[ElementShot]] = {}
    graph = explore(
        context["driver_cls"](app),
        target=_TARGET,
        controller=RunController(RunBudget()),
        declared_sandbox=True,
        screenshots=shots,
        element_screenshots=element_shots,
        screenshot_dir=out,
    )
    render_wiki(
        graph,
        out,
        target=_TARGET,
        screenshots=shots,
        element_screenshots=element_shots,
    )
    context["graph"] = graph
    context["shots"] = shots
    context["element_shots"] = element_shots
    context["out_dir"] = out


def _pngs(out: Path) -> list[Path]:
    return sorted((out / "screenshots").glob("*.png"))


def _page(context: dict[str, Any], name: str) -> str:
    index = context["graph"].states.index(context["app"].state_id_of(name))
    return (
        context["out_dir"] / "states" / f"state-{index}.html"
    ).read_text(encoding="utf-8")


# --- Given ---------------------------------------------------------------


@given("a sandbox app whose screens and elements render real pictures")
def real_pictures(context: dict[str, Any]) -> None:
    # The Background: the fakes render decodable PNGs (see module docstring). Each
    # scenario's Given builds the concrete screens/elements; nothing to do here.
    pass


@given(parsers.parse('screens "{home}" and "{other}" render the same picture'))
def same_picture(context: dict[str, Any], home: str, other: str) -> None:
    app: _FakeApp = context["app"]
    app.root = home
    picture = _png(_gradient("a"))
    app.add_screen(home, picture)
    app.add_screen(other, picture)  # byte-identical → the exact-match path
    app.link(home, "open", other)


@given(parsers.parse('screens "{home}" and "{other}" render near-identical pictures'))
def near_identical(context: dict[str, Any], home: str, other: str) -> None:
    app: _FakeApp = context["app"]
    app.root = home
    base = _gradient("a")
    app.add_screen(home, _png(base))
    app.add_screen(other, _png(_near_variant(base)))  # byte-different, dHash-close
    app.link(home, "open", other)


@given(
    parsers.parse('screens "{home}" and "{other}" render clearly different pictures')
)
def clearly_different(context: dict[str, Any], home: str, other: str) -> None:
    app: _FakeApp = context["app"]
    app.root = home
    app.add_screen(home, _png(_gradient("a")))
    app.add_screen(other, _png(_gradient("b")))  # far apart in every channel
    app.link(home, "open", other)


@given("the screen has an element that is part of the full-page picture")
def element_is_part_of_page(context: dict[str, Any]) -> None:
    app: _FakeApp = context["app"]
    app.root = "home"
    page = _gradient("c")
    app.add_screen("home", _png(page))
    x, y, w, h = _CLIP_BOX
    clip = _png(page[y : y + h, x : x + w])  # an exact interior crop of the page
    app.add_element("home", "Feature", clip, box=_CLIP_BOX)


@given("the driver reports element geometry")
def driver_reports_geometry(context: dict[str, Any]) -> None:
    context["driver_cls"] = _GeometryDriver


@given("the driver cannot report element geometry")
def driver_no_geometry(context: dict[str, Any]) -> None:
    context["driver_cls"] = _Driver  # plain driver: containment falls to pixel search


@given("the screen has an element whose picture is not part of any page")
def element_not_part_of_page(context: dict[str, Any]) -> None:
    app: _FakeApp = context["app"]
    app.root = "home"
    app.add_screen("home", _png(_gradient("c")))
    # A different gradient than the page, so it is in no bigger picture → own file.
    x, y, w, h = _CLIP_BOX
    clip = _png(_gradient("b")[y : y + h, x : x + w])
    app.add_element("home", "Feature", clip)


# --- When ----------------------------------------------------------------


@when("I explore it with screenshots on")
def explore_on(context: dict[str, Any], tmp_path: Path) -> None:
    _run(context, tmp_path / "wiki")


@when("I explore it with screenshots on twice")
def explore_twice(context: dict[str, Any], tmp_path: Path) -> None:
    context["files_a"] = _explore_files(context, tmp_path / "run-a")
    context["files_b"] = _explore_files(context, tmp_path / "run-b")


def _explore_files(context: dict[str, Any], out: Path) -> dict[str, bytes]:
    app: _FakeApp = context["app"]
    explore(
        context["driver_cls"](app),
        target=_TARGET,
        controller=RunController(RunBudget()),
        declared_sandbox=True,
        screenshots={},
        element_screenshots={},
        screenshot_dir=out,
    )
    return {
        str(p.relative_to(out)): p.read_bytes() for p in sorted(out.rglob("*.png"))
    }


# --- Then ----------------------------------------------------------------


@then("only one screenshot file is written for those two screens")
def one_file(context: dict[str, Any]) -> None:
    pngs = _pngs(context["out_dir"])
    assert len(pngs) == 1, f"expected one shared screenshot file, got {pngs}"


@then("both state pages embed the same screenshot reference")
def both_embed_same(context: dict[str, Any]) -> None:
    shots: dict[str, ImageRef] = context["shots"]
    app: _FakeApp = context["app"]
    refs = {shots[app.state_id_of(name)].src for name in ("home",)}
    # Every captured state shares the one written file's reference.
    srcs = {ref.src for ref in shots.values()}
    assert len(srcs) == 1, f"state pages reference different files: {srcs}"
    shared = next(iter(srcs))
    assert refs <= srcs
    for name in shots:
        index = context["graph"].states.index(name)
        page = (
            context["out_dir"] / "states" / f"state-{index}.html"
        ).read_text(encoding="utf-8")
        # A state page sits in states/, so its embedded src climbs one level (slice 6g).
        assert f'src="../{shared}"' in page, f"state-{index} does not embed {shared}"


@then("a separate screenshot file is written for each of the two screens")
def two_files(context: dict[str, Any]) -> None:
    pngs = _pngs(context["out_dir"])
    assert len(pngs) == 2, f"expected a distinct file per screen, got {pngs}"


@then("no separate clip file is written for that element")
def no_clip_file(context: dict[str, Any]) -> None:
    out: Path = context["out_dir"]
    assert not (out / "screenshots" / "state-0-el-0.png").exists(), (
        "a clip file was written for a contained element"
    )
    # Only the full-page picture was written — no per-element file at all.
    assert _pngs(out) == [out / "screenshots" / "state-0.png"], _pngs(out)


@then("the element's row embeds a crop of the full-page picture")
def row_embeds_crop(context: dict[str, Any]) -> None:
    page = _page(context, "home")
    assert "screenshot-crop" in page, "no crop reference on the page"
    # A state page sits in states/, so the crop background-image climbs a level (6g).
    assert "background-image:url('../screenshots/state-0.png')" in page, page


@then("a clip file is written for that element")
def clip_file_written(context: dict[str, Any]) -> None:
    out: Path = context["out_dir"]
    assert (out / "screenshots" / "state-0-el-0.png").is_file(), (
        "no own-file clip was written for the uncontained element"
    )


@then("both runs write the identical set of screenshot files")
def identical_file_sets(context: dict[str, Any]) -> None:
    a: dict[str, bytes] = context["files_a"]
    b: dict[str, bytes] = context["files_b"]
    assert a, "the run wrote no screenshot files"
    assert a == b, (
        f"re-run differs: names {sorted(a)} vs {sorted(b)}; "
        f"byte-equal={ {k: a[k] == b.get(k) for k in a} }"
    )
