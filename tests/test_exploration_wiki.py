"""Unit tests for the pure wiki renderer (ROADMAP.md §2e, slice 6a).

These sit below `exploration_wiki.feature` in the pyramid, probing the boundaries the
Gherkin scenarios don't spell out: an empty graph, a state or transition with no
captured bundle, the screenshot-changed rendering, disk writing, and that a
script-injecting captured value is neutralized by autoescaping (defence beside §2h
redaction).
"""

from __future__ import annotations

from pathlib import Path

from spoor.exploration.capture import StateSignals, diff_signals
from spoor.exploration.discovery import ActionableElement
from spoor.exploration.graph import ExplorationGraph
from spoor.exploration.wiki import build_pages, render_wiki

_ID_A = "a" * 64
_ID_B = "b" * 64


def _two_state_graph() -> ExplorationGraph:
    graph = ExplorationGraph()
    before = StateSignals(ax_node_count=2, storage_keys=("session",))
    after = StateSignals(
        ax_node_count=5,
        storage_keys=("session", "cart"),
        screenshot_hash="123",
    )
    action = ActionableElement(role="button", name="Add", backend_node_id=1)
    graph.add_state(_ID_A, [action], before)
    graph.add_state(_ID_B, [], after)
    graph.add_transition(_ID_A, action, _ID_B, diff_signals(before, after))
    return graph


def test_empty_graph_renders_index_and_help() -> None:
    pages = build_pages(ExplorationGraph(), target="https://example.test")
    # Even an empty graph gets the index and the fixed help/glossary page (6f).
    assert set(pages) == {"index.html", "help.html"}
    index = pages["index.html"]
    assert "<strong>0</strong> states discovered" in index
    # A Mermaid header with no nodes/edges is still valid, so the overview holds.
    assert "graph LR" in index


def test_state_without_signals_reads_honestly() -> None:
    graph = ExplorationGraph()
    graph.add_state(_ID_A, [])  # signals default None
    page = build_pages(graph, target="t")["state-0.html"]
    assert "No signal bundle was captured" in page


def test_transition_screenshot_change_is_reported_both_ways() -> None:
    changed = diff_signals(
        StateSignals(screenshot_hash="1"), StateSignals(screenshot_hash="2")
    )
    unchanged = diff_signals(
        StateSignals(screenshot_hash="1"), StateSignals(screenshot_hash="1")
    )
    assert changed.screenshot_changed is True
    assert unchanged.screenshot_changed is False


def test_two_state_graph_links_are_navigable() -> None:
    pages = build_pages(_two_state_graph(), target="https://example.test")
    assert set(pages) == {
        "help.html",
        "index.html",
        "state-0.html",
        "state-1.html",
        "transition-0.html",
    }
    # The transition page links both endpoints, and the from-state links onward.
    transition = pages["transition-0.html"]
    assert 'href="state-0.html"' in transition
    assert 'href="state-1.html"' in transition
    assert 'href="transition-0.html"' in pages["state-0.html"]
    # The screenshot delta and node delta are surfaced.
    assert "Accessibility node delta: <strong>3</strong>" in transition
    assert "Screenshot changed: <strong>yes</strong>" in transition


def test_captured_html_is_escaped_not_executed() -> None:
    graph = ExplorationGraph()
    graph.add_state(
        _ID_A,
        [],
        StateSignals(console_messages=("<script>alert(1)</script>",)),
    )
    page = build_pages(graph, target="t")["state-0.html"]
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_render_wiki_writes_every_page(tmp_path: Path) -> None:
    written = render_wiki(_two_state_graph(), tmp_path, target="https://example.test")
    assert [p.name for p in written] == sorted(p.name for p in written)
    assert {p.name for p in written} == {
        "help.html",
        "index.html",
        "state-0.html",
        "state-1.html",
        "transition-0.html",
    }
    for path in written:
        assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_render_wiki_writes_and_embeds_only_captured_screenshots(
    tmp_path: Path,
) -> None:
    # The writer places a state-N.png only for a state it has bytes for, embeds exactly
    # those, and leaves an uncaptured state (and every other page) pixel-free (8b).
    graph = _two_state_graph()  # _ID_A is index 0, _ID_B is index 1
    written = render_wiki(
        graph, tmp_path, target="https://example.test", screenshots={_ID_A: b"\x89PNGa"}
    )
    names = {p.name for p in written}
    assert "state-0.png" in names
    assert "state-1.png" not in names
    assert (tmp_path / "state-0.png").read_bytes() == b"\x89PNGa"
    page_a = (tmp_path / "state-0.html").read_text(encoding="utf-8")
    page_b = (tmp_path / "state-1.html").read_text(encoding="utf-8")
    assert 'src="state-0.png"' in page_a
    assert "<img" not in page_b


def test_render_wiki_default_is_pixel_free(tmp_path: Path) -> None:
    written = render_wiki(_two_state_graph(), tmp_path, target="https://example.test")
    assert not [p for p in written if p.suffix == ".png"]
    for path in written:
        assert "<img" not in path.read_text(encoding="utf-8")
