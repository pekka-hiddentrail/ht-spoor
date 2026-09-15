"""Render an exploration graph into a browsable static wiki (ROADMAP.md §2e).

Sub-slice 6a of the sixth §2e slice — the pure renderer, no browser and no disk in
`build_pages`. §2e's end product is a *browsable* map: one page per state showing the
free-signal bundle captured there, one page per transition showing what its action
changed, and an index with a Mermaid overview of the whole state-action graph. This
module turns an `ExplorationGraph` (built by the explorer, slice 5) into that set of
static HTML pages.

Two scoping decisions (recorded in the §2e slice-6a decision note) shape it:

- **Self-contained Jinja2 renderer**, not a reused site generator (MkDocs/Docusaurus):
  a fixed, small page set rendered straight from templates, no build step. The graph
  overview is drawn by Mermaid, loaded from a CDN by the index — the pages themselves
  are static and readable offline; only the overview *diagram* needs the network.
- **Hash-plus-opt-in screenshots**: the captured screenshot signal is a perceptual hash
  (5c-ii), so a state page always shows its hash and a transition page reports whether
  the screenshot *changed* — a hash is a 64-bit int, safe to share unconditionally.
  Embedding the *image* is the deferred visual-capture work (§9), begun in slice 8a:
  `build_pages` accepts a `screenshots` mapping of state id → relative filename, and a
  state so marked embeds its full-page screenshot as an `<img>` referencing that
  filename, leading the page as the screen's visual identity. It is gated for a §2h
  reason: string redaction cannot scrub a secret that is *visible on the page* (a token
  shown in the DOM, PII), so a screenshot bypasses the redaction every other signal goes
  through. So pixels reach the shared wiki only behind an explicit opt-in — the default
  is no mapping, and a default run stays pixel-free. The image bytes are streamed to
  disk by the explorer as it captures them (§2e slice 8f); the renderer only knows
  *which* states have an image and *where* it sits, and writes the HTML referencing it.

Slice 6c makes the state pages readable after a live PrestaShop run showed them barely
usable. Two generic fixes (§0): a state is labelled by its captured **page title**
(`_state_label`) instead of only its opaque 64-char id — on its own page, in the index
lists, and in the overview graph — falling back to the short id when the page has no
title; and a state page **collapses repeated console/network lines** (`_tally`) into
one row with an "× count", because a chatty library or a polled endpoint still repeats
the same line many times within a single visit (across the visit's reloads). Transition
pages already show a first-seen-deduplicated diff (`capture.diff_signals`), so they keep
listing every distinct added line as before.

Slice 6d groups a state's network requests by **kind** (`_categorize_network`) instead
of showing one flat list: each request is bucketed by a URL-only heuristic
(`_request_category`) into a small fixed taxonomy — Documents, Scripts, Styles, Images,
Fonts, Media, Data, Other — so a reader sees at a glance what the page loaded, with a
per-group count. The kind is derived from the URL alone (the driver captures request
URLs, not response content-types), so it stays generic across every target (§0).

Slice 6e rearranges the state page to lead with its **actionable elements**. The old
"Actions here" bullet list (and the separate "Outgoing transitions" list) are replaced
by a single "Actions" *table* (`_elements`) — one row per discovered element, columns
Label, Type, Screen capture, and Destination / target state — placed immediately after
the state-identity block (label, id, settle), ahead of the captured-signal sections, so
the thing a reader acts on comes first. The destination cell folds in what the removed
outgoing-transitions list carried: when an element was fired and produced a transition,
it links to that transition page labelled by the target state; otherwise it reads
"none". The screen-capture column is a placeholder that reads "none" for every element
today — Spoor captures no per-element screenshot yet (the deferred visual-capture work
noted in §9), so the column is honest about there being nothing to show rather than
implying one exists. Purely a presentation change; the graph and its redaction are
untouched, and it stays generic across every target (§0).

Slice 6f adds a **help/glossary page** (`_HELP`, `help.html`) linked from every page's
nav. It is a fixed, target-independent glossary written in plain language for a reader
who did not build Spoor — defining every term the other pages use (state, transition,
accessibility nodes, storage keys added, network requests, screenshot hash, the
redaction placeholder, and so on). It carries no captured values, so nothing on it needs
redaction, and being identical for every target it holds nothing site-specific (§0).

(The console/network buffers are also now *scoped per visit*: the driver clears them on
each reset, so a state reached late in the run reflects only the walk that reached it,
not the whole session's cumulative output — see `driver.reset`. That is a capture-layer
change; the renderer here simply renders whatever bundle a state carries.)

The wiki is a **shared-output surface**, so §2h redaction is mandatory and applied two
ways, defensively overlapping: every captured value rendered (console messages,
storage keys, network URLs, action labels, the page title used as a state label, and
the operator-supplied target URL) is passed through `spoor.security.redaction.redact`
before rendering, and Jinja2 autoescaping — on for every template — independently
neutralizes any HTML/script a captured value might carry. Nothing here is
site-specific (§0): the same templates render every target's graph.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import DictLoader, Environment, select_autoescape

from spoor.exploration.capture import StateSignals
from spoor.exploration.explorer import ElementShot
from spoor.exploration.graph import ExplorationGraph, SkippedAction, Transition
from spoor.exploration.screenshot_store import ImageRef
from spoor.security.redaction import REDACTED, redact

# Length of the state-id prefix shown as a human-readable label. State ids are
# 64-char SHA-256 hex digests (slice 2); the full id stays on the state page, but a
# 12-char prefix is enough to tell states apart in links and the overview diagram.
_SHORT_ID = 12
_UNNAMED = "(unnamed)"


# Network-request categories (§2e slice 6d). A flat list of every request seen at a
# state is noise, so the state page collates requests under this small fixed taxonomy,
# derived from the URL alone — Spoor captures request URLs, not response content-types,
# so the kind is a *heuristic* on the URL's file extension (and an "/api/" path for
# data). It is deliberately conservative: an unrecognised extension falls to "Other" and
# an extensionless URL reads as a document (a page navigation) unless its path names an
# API. Generic to every target (§0): the same rule buckets every site's requests. The
# order here is the display order; empty categories are omitted from a page.
_DOCUMENTS, _SCRIPTS, _STYLES = "Documents", "Scripts", "Styles"
_IMAGES, _FONTS, _MEDIA, _DATA, _OTHER = "Images", "Fonts", "Media", "Data", "Other"
_CATEGORY_ORDER = [
    _DOCUMENTS,
    _SCRIPTS,
    _STYLES,
    _IMAGES,
    _FONTS,
    _MEDIA,
    _DATA,
    _OTHER,
]
_EXTENSION_CATEGORY = {
    "js": _SCRIPTS, "mjs": _SCRIPTS, "cjs": _SCRIPTS,
    "css": _STYLES,
    "png": _IMAGES, "jpg": _IMAGES, "jpeg": _IMAGES, "gif": _IMAGES, "svg": _IMAGES,
    "webp": _IMAGES, "ico": _IMAGES, "bmp": _IMAGES, "avif": _IMAGES, "apng": _IMAGES,
    "woff": _FONTS, "woff2": _FONTS, "ttf": _FONTS, "otf": _FONTS, "eot": _FONTS,
    "mp4": _MEDIA, "webm": _MEDIA, "ogg": _MEDIA, "mp3": _MEDIA, "wav": _MEDIA,
    "mov": _MEDIA, "m4a": _MEDIA, "avi": _MEDIA,
    "json": _DATA, "xml": _DATA,
    "html": _DOCUMENTS, "htm": _DOCUMENTS, "xhtml": _DOCUMENTS,
    "php": _DOCUMENTS, "asp": _DOCUMENTS, "aspx": _DOCUMENTS, "jsp": _DOCUMENTS,
}


def _redact_all(items: tuple[str, ...]) -> list[str]:
    """Redact every captured string before it reaches the shared wiki (§2h)."""
    return [redact(item) for item in items]


def _tally(items: tuple[str, ...]) -> list[dict[str, object]]:
    """Redact and collapse repeats into `{text, count}` rows, first-seen order (6c).

    A state's console and network signals are whole-run running buffers, so a chatty
    library or a polled endpoint repeats the same line hundreds of times; showing every
    copy made a state page unreadably large. Each item is redacted first (§2h) and then
    counted, so two raw values that redact to the same placeholder collapse together —
    the page shows each distinct line once with how many times it occurred.
    """
    counts: dict[str, int] = {}
    for item in items:
        redacted = redact(item)
        counts[redacted] = counts.get(redacted, 0) + 1
    return [{"text": text, "count": count} for text, count in counts.items()]


def _request_category(url: str) -> str:
    """Bucket a request URL into one of `_CATEGORY_ORDER` by a URL-only heuristic (6d).

    Reads the file extension of the URL's last path segment (query and fragment
    ignored) and maps it through `_EXTENSION_CATEGORY`. An unrecognised extension is
    "Other"; a segment with no extension is a "Document" (a page navigation) unless the
    path names an API, which reads as "Data". No content-type is available — Spoor
    captures URLs, not responses — so this is a best-effort label, not a guarantee.
    """
    path = urlsplit(url).path
    segment = path.rsplit("/", 1)[-1]
    if "." in segment:
        ext = segment.rsplit(".", 1)[-1].lower()
        return _EXTENSION_CATEGORY.get(ext, _OTHER)
    if "/api/" in path.lower():
        return _DATA
    return _DOCUMENTS


def _categorize_network(urls: tuple[str, ...]) -> list[dict[str, object]]:
    """Group request URLs by kind, each group a tallied `{category, total, rows}` (6d).

    Categorises each raw URL (so the extension is read before redaction), then tallies
    within the group so repeats collapse to one redacted row with a count (`_tally`).
    `total` is the group's request count including repeats. Categories are emitted in
    `_CATEGORY_ORDER`; an empty category is omitted.
    """
    groups: dict[str, list[str]] = {}
    for url in urls:
        groups.setdefault(_request_category(url), []).append(url)
    views: list[dict[str, object]] = []
    for category in _CATEGORY_ORDER:
        raw = groups.get(category)
        if not raw:
            continue
        views.append(
            {"category": category, "total": len(raw), "rows": _tally(tuple(raw))}
        )
    return views


def _state_label(sid: str, signals: StateSignals | None) -> str:
    """A state's human-readable label: its redacted page title, else the short id (6c).

    The abstract state id is a 64-char hash, so a map labelled only by it reads as
    noise. The captured page title is a far better label; it is redacted like any other
    shared value (§2h), and an empty title falls back to the short id so every state
    stays identifiable.
    """
    title = signals.title if signals is not None else ""
    return redact(title) if title else sid[:_SHORT_ID]


def _label(name: str) -> str:
    """An action's redacted display label, or a placeholder for an icon-only one."""
    return redact(name) if name else _UNNAMED


def _mermaid_safe(text: str) -> str:
    """Strip the characters that would break Mermaid's own quoted-label syntax.

    HTML/script safety is handled separately: the diagram source is autoescaped like
    any other template value (not marked safe), and the browser decodes the escaped
    entities back in the element's text content, which is what Mermaid parses — so an
    injected `<script>` renders as inert text. Here we only remove the few characters
    that are structural to Mermaid *after* that decode: the quote and pipe that
    delimit a label, and newlines/backticks that would split it.
    """
    for bad, good in (('"', "'"), ("|", "/"), ("`", "'"), ("\n", " "), ("\r", " ")):
        text = text.replace(bad, good)
    return text


def _mermaid(
    graph: ExplorationGraph, state_index: dict[str, int], labels: dict[str, str]
) -> str:
    """A Mermaid `graph LR` source for the whole state-action graph.

    Nodes are the states (labelled by their page title, or short id when untitled — 6c);
    edges are the transitions (labelled by the redacted action name). Endpoints not in
    the state index are skipped defensively, though the explorer always records a
    transition's states.
    """
    lines = ["graph LR"]
    for sid, i in state_index.items():
        lines.append(f'  S{i}["{_mermaid_safe(labels[sid])}"]')
    for transition in graph.transitions:
        src = state_index.get(transition.from_state)
        dst = state_index.get(transition.to_state)
        if src is None or dst is None:
            continue
        label = _mermaid_safe(_label(transition.action.name))
        lines.append(f'  S{src} -->|"{label}"| S{dst}')
    return "\n".join(lines)


def _state_view(
    graph: ExplorationGraph, sid: str, index: int, label: str
) -> dict[str, object]:
    """The redacted, template-ready view of one state node."""
    node = graph.node(sid)
    signals = node.signals
    return {
        "index": index,
        "id": sid,
        "short_id": sid[:_SHORT_ID],
        "label": label,
        "filename": f"state-{index}.html",
        "has_signals": signals is not None,
        "settled": True if signals is None else signals.settled,
        "ax_node_count": None if signals is None else signals.ax_node_count,
        "console": [] if signals is None else _tally(signals.console_messages),
        "storage": [] if signals is None else _redact_all(signals.storage_keys),
        "network": (
            [] if signals is None else _categorize_network(signals.network_requests)
        ),
        "screenshot_hash": (
            None
            if signals is None or signals.screenshot_hash is None
            else redact(signals.screenshot_hash)
        ),
        "actions": [
            {"role": action.role, "name": _label(action.name)}
            for action in node.actions
        ],
    }


def _image_view(ref: ImageRef | None) -> dict[str, object] | None:
    """A template-ready view of an image reference, or None (§2e slices 8f/8g).

    A whole-file reference (`box` None) renders as an `<img>`; a crop reference — a clip
    that is a region of a bigger picture (§2e slice 8g) — carries the `crop` rectangle,
    so the template shows just that region of the shared `src` (a CSS-cropped box)
    instead of embedding a separate image. `src` is the subfolder-relative filename
    either way — the same path the image sits at beside the pages. Holds only a filename
    and integers, so it adds nothing to redact (§2h).
    """
    if ref is None:
        return None
    if ref.box is None:
        return {"src": ref.src, "crop": None}
    x, y, width, height = ref.box
    return {
        "src": ref.src,
        "crop": {"x": x, "y": y, "width": width, "height": height},
    }


def _elements(
    actions: list[dict[str, object]],
    outgoing: list[dict[str, object]],
    clips: Sequence[ImageRef | None],
    opens: Sequence[ImageRef | None],
) -> list[dict[str, object]]:
    """The state's actionable elements as table rows, each with its destination (6e).

    One row per discovered element (`node.actions`), joined to the transition it fired
    (matched by redacted label + role) so the row can link to that transition page,
    labelled by the target state. An element that was never fired has no destination.
    `clips` is the per-element screen-capture reference, aligned by discovery position
    with `actions` (§2e slices 8d/8g): a row gets its clip — a whole-file `<img>` or a
    crop of the state's full-page picture — when the caller opted in and one was
    captured, else None so the column reads "none" honestly. `opens` is aligned
    the same way, for the element's *opened* capture — the content a dropdown or list
    reveals (§2e slice 8e) — None for a non-disclosure element or one never opened.
    Defensively, a fired transition whose element is somehow absent from the discovered
    list still gets a row (with no clip and no opened image), so no edge the graph
    recorded is dropped from the page.
    """
    destination: dict[tuple[object, object], dict[str, object]] = {}
    for tv in outgoing:
        destination.setdefault((tv["action_name"], tv["action_role"]), tv)
    rows: list[dict[str, object]] = []
    seen: set[tuple[object, object]] = set()
    for i, action in enumerate(actions):
        key = (action["name"], action["role"])
        seen.add(key)
        clip = clips[i] if i < len(clips) else None
        opened = opens[i] if i < len(opens) else None
        rows.append(
            _element_row(
                action["name"], action["role"], destination.get(key), clip, opened
            )
        )
    for tv in outgoing:
        key = (tv["action_name"], tv["action_role"])
        if key not in seen:
            seen.add(key)
            rows.append(
                _element_row(tv["action_name"], tv["action_role"], tv, None, None)
            )
    return rows


def _element_row(
    label: object,
    role: object,
    transition: dict[str, object] | None,
    clip: ImageRef | None,
    opened: ImageRef | None,
) -> dict[str, object]:
    """One Actions row: label, type, clip, opened capture, and destination (6e)."""
    return {
        "label": label,
        "type": role,
        "screenshot": _image_view(clip),  # clip: img or crop of the page (8d/8g)
        "opened": _image_view(opened),  # opened-content capture: img or crop (8e/8g)
        "dest_label": None if transition is None else transition["to_label"],
        "dest_filename": None if transition is None else transition["filename"],
    }


def _transition_view(
    transition: Transition, index: int, states: list[str], labels: dict[str, str]
) -> dict[str, object]:
    """The redacted, template-ready view of one transition edge."""
    signals = transition.signals
    return {
        "index": index,
        "filename": f"transition-{index}.html",
        "from_id": transition.from_state,
        "from_short": transition.from_state[:_SHORT_ID],
        "from_label": labels[transition.from_state],
        "from_index": states.index(transition.from_state),
        "to_id": transition.to_state,
        "to_short": transition.to_state[:_SHORT_ID],
        "to_label": labels[transition.to_state],
        "to_index": states.index(transition.to_state),
        "action_name": _label(transition.action.name),
        "action_role": transition.action.role,
        "recovered_via": (
            None
            if transition.recovered_via is None
            else redact(transition.recovered_via)
        ),
        "has_signals": signals is not None,
        "ax_node_delta": None if signals is None else signals.ax_node_delta,
        "console_added": [] if signals is None else _redact_all(signals.console_added),
        "storage_added": [] if signals is None else _redact_all(signals.storage_added),
        "storage_removed": (
            [] if signals is None else _redact_all(signals.storage_removed)
        ),
        "network_added": [] if signals is None else _redact_all(signals.network_added),
        "screenshot_changed": None if signals is None else signals.screenshot_changed,
        "screenshot_label": (
            "" if signals is None else ("yes" if signals.screenshot_changed else "no")
        ),
    }


def _skip_view(skip: SkippedAction, states: list[str]) -> dict[str, object]:
    """The redacted view of one gate-refused action (shown on the index)."""
    return {
        "from_short": skip.from_state[:_SHORT_ID],
        "action_name": _label(skip.action.name),
        "action_role": skip.action.role,
        "reason": redact(skip.reason),
    }


def build_pages(
    graph: ExplorationGraph,
    *,
    target: str,
    screenshots: Mapping[str, ImageRef] | None = None,
    element_screenshots: Mapping[str, Sequence[ImageRef | None]] | None = None,
    element_opened: Mapping[str, Sequence[ImageRef | None]] | None = None,
) -> dict[str, str]:
    """Render `graph` into a map of wiki filename → HTML (§2e slice 6a).

    Pure: builds the whole static site in memory, touching no disk and no browser, so
    it is fully unit/BDD testable. Every captured value is redacted (§2h) and every
    template autoescapes, so nothing raw or executable reaches a page. `render_wiki`
    is the thin writer around it.

    `screenshots` maps a state id to the `ImageRef` for its full-page screenshot,
    embedded as an `<img>` (slice 8a); dedup means two states with the same screen may
    share one file (§2e slice 8g). It defaults to none, so a default wiki is pixel-free;
    pixels reach this shared surface only behind an explicit opt-in, because a
    screenshot cannot be secret-redacted the way every text signal is (§2h). The image
    bytes
    themselves are written to disk by the explorer as they are captured (§2e slice 8f);
    here a marked state's view just carries the reference.

    `element_screenshots` is the per-element counterpart (§2e slice 8d): a state id maps
    to the clip `ImageRef`s for its actions, aligned by discovery position, so each
    Actions-table row can embed its element's image — a whole picture, or a crop of the
    state's full-page shot when the clip is a region of it (§2e slice 8g).
    `element_opened` is the same shape for the *opened* capture of each element (§2e,
    8e) — the content a disclosure control reveals. Same opt-in posture for both —
    omitted or None means that column stays empty and pixel-free.
    """
    states = graph.states
    shot_files = screenshots or {}
    element_clips = element_screenshots or {}
    element_opens = element_opened or {}
    state_index = {sid: i for i, sid in enumerate(states)}
    labels = {sid: _state_label(sid, graph.node(sid).signals) for sid in states}
    state_views = [
        _state_view(graph, sid, i, labels[sid]) for i, sid in enumerate(states)
    ]
    transition_views = [
        _transition_view(t, j, states, labels)
        for j, t in enumerate(graph.transitions)
    ]
    skip_views = [_skip_view(s, states) for s in graph.skipped]

    # A state's actionable elements (6e), each joined to the transition it fired so the
    # Actions table links onward through the state's edges via its Destination column.
    for view in state_views:
        outgoing = [
            tv for tv in transition_views if tv["from_index"] == view["index"]
        ]
        view["elements"] = _elements(
            view["actions"],  # type: ignore[arg-type]
            outgoing,
            element_clips.get(str(view["id"]), ()),
            element_opens.get(str(view["id"]), ()),
        )
        # A full-page screenshot is embedded only for states the caller opted in (8a);
        # the marked state carries the relative filename its image was written under.
        view["screenshot_image"] = shot_files.get(str(view["id"]))

    env = _environment()
    safe_target = redact(target)
    pages: dict[str, str] = {
        "index.html": env.get_template("index.html").render(
            target=safe_target,
            states=state_views,
            transitions=transition_views,
            skipped=skip_views,
            mermaid=_mermaid(graph, state_index, labels),
        ),
        # A fixed, target-independent glossary of every term the pages use (6f).
        "help.html": env.get_template("help.html").render(target=safe_target),
    }
    for view in state_views:
        pages[str(view["filename"])] = env.get_template("state.html").render(
            state=view, target=safe_target
        )
    for view in transition_views:
        pages[str(view["filename"])] = env.get_template("transition.html").render(
            transition=view, target=safe_target
        )
    return pages


def render_wiki(
    graph: ExplorationGraph,
    out_dir: Path,
    *,
    target: str,
    screenshots: Mapping[str, ImageRef] | None = None,
    element_screenshots: Mapping[str, Sequence[ElementShot]] | None = None,
) -> list[Path]:
    """Write the wiki's HTML pages for `graph` under `out_dir`, returning them sorted.

    Creates `out_dir` (and parents) if needed and writes each page from `build_pages`
    as UTF-8. Paths are returned sorted for a stable, testable result. Only HTML is
    written here: the screenshot images were already streamed to disk by the explorer
    as they were captured (§2e slice 8f), so this writer never holds image bytes — it
    embeds the filename references the explorer produced.

    `screenshots` maps a state id to the `ImageRef` for its full-page screenshot (§2e
    slices 8b/8f/8g). The explorer must have written those images under this same
    `out_dir` (that is why it takes a `screenshot_dir` — pass it `out_dir`); here each
    marked state's page embeds its reference, and dedup means two states may point at
    one shared file. Left None (the default), a page stays pixel-free — embedding pixels
    is always an explicit opt-in, since a screenshot cannot be secret-redacted the way
    every text value on the pages is (§2h).

    `element_screenshots` maps a state id to one `ElementShot` per discovered element,
    in discovery order (§2e slices 8d/8e), each field an `ImageRef`. The closed-clip
    reference embeds in the element's Actions row — as its own image or as a crop of the
    state's full-page picture (§2e slice 8g) — and, when present, the `opened` reference
    embeds the revealed content beside it; the images themselves, again, already on
    disk. Same opt-in, pixel-free-by-default posture as the full-page sink, for the same
    §2h reason.
    """
    shot_files = screenshots or {}
    element_shots = element_screenshots or {}
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # The clip and opened references each Actions row will embed, keyed by state id and
    # aligned by discovery position with the state's actions. The closed clip (8d) and
    # the opened image (8e) are tracked independently, so an element can have one, both,
    # or neither. The bytes are already on disk (streamed by the explorer, 8f); here we
    # only thread the filenames the shots carry into the renderer.
    clip_files: dict[str, list[ImageRef | None]] = {}
    opened_files: dict[str, list[ImageRef | None]] = {}
    for sid in graph.states:
        shots = element_shots.get(sid, ())
        if not shots:
            continue
        clip_files[sid] = [shot.clip for shot in shots]
        opened_files[sid] = [shot.opened for shot in shots]

    for filename, html in build_pages(
        graph,
        target=target,
        screenshots=shot_files,
        element_screenshots=clip_files,
        element_opened=opened_files,
    ).items():
        path = out_dir / filename
        path.write_text(html, encoding="utf-8")
        written.append(path)
    return sorted(written)


def _environment() -> Environment:
    """A Jinja2 environment with autoescape on for every template (§2h defence)."""
    return Environment(
        loader=DictLoader(_TEMPLATES),
        autoescape=select_autoescape(default=True, default_for_string=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


_LAYOUT = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{% block title %}Spoor exploration wiki{% endblock %}</title>
    <style>
      body { font-family: sans-serif; margin: 2rem auto; max-width: 60rem; }
      table { border-collapse: collapse; }
      th, td { border: 1px solid #ccc; padding: 0.3rem 0.6rem; text-align: left; }
      code { background: #f4f4f4; padding: 0 0.2rem; }
      nav { margin-bottom: 1rem; }
      .count { color: #888; font-size: 0.85em; }
      .screenshot { max-width: 100%; height: auto; border: 1px solid #ccc; }
      .screenshot-crop { max-width: none; }
    </style>
  </head>
  <body>
    <nav><a href="index.html">&larr; Overview</a> &middot;
      <a href="help.html">Help / glossary</a> &middot;
      <span>Explored target: <code>{{ target }}</code></span></nav>
    {% block body %}{% endblock %}
  </body>
</html>
"""

_INDEX = """{% extends "layout.html" %}
{% block title %}Exploration wiki — {{ target }}{% endblock %}
{% block body %}
<h1>Exploration wiki</h1>
<p>Explored target: <code>{{ target }}</code></p>
<ul>
  <li><strong>{{ states | length }}</strong> states discovered</li>
  <li><strong>{{ transitions | length }}</strong> transitions</li>
  <li><strong>{{ skipped | length }}</strong> actions skipped</li>
</ul>

<h2>Overview</h2>
<pre class="mermaid">
{{ mermaid }}
</pre>
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  mermaid.initialize({ startOnLoad: true });
</script>

<h2>States</h2>
<ul>
  {% for state in states %}
  <li><a href="{{ state.filename }}">{{ state.label }}</a></li>
  {% endfor %}
</ul>

<h2>Transitions</h2>
<ul>
  {% for transition in transitions %}
  <li><a href="{{ transition.filename }}">{{ transition.from_label }}
    &mdash;{{ transition.action_name }}&rarr; {{ transition.to_label }}</a></li>
  {% endfor %}
</ul>

{% if skipped %}
<h2>Skipped actions</h2>
<table>
  <tr><th>From</th><th>Action</th><th>Role</th><th>Reason</th></tr>
  {% for skip in skipped %}
  <tr><td>{{ skip.from_short }}</td><td>{{ skip.action_name }}</td>
    <td>{{ skip.action_role }}</td><td>{{ skip.reason }}</td></tr>
  {% endfor %}
</table>
{% endif %}
{% endblock %}
"""

_STATE = """{% extends "layout.html" %}
{% block title %}{{ state.label }}{% endblock %}
{# Render one image reference: a whole file as an <img>, or a crop of a shared picture
   (a clip that is a region of a bigger image, §2e slice 8g) as a CSS-cropped box that
   shows just that rectangle of `src`. Both keep the `screenshot` class so existing
   styling and assertions hold; the crop adds `screenshot-crop`. #}
{% macro shot(image, alt) %}
{% if image.crop %}
<span class="screenshot screenshot-crop" role="img" aria-label="{{ alt }}"
  style="display:inline-block;width:{{ image.crop.width }}px;
  height:{{ image.crop.height }}px;background-image:url('{{ image.src }}');
  background-position:-{{ image.crop.x }}px -{{ image.crop.y }}px;
  background-repeat:no-repeat;"></span>
{% else %}
<img class="screenshot" src="{{ image.src }}" alt="{{ alt }}" />
{% endif %}
{% endmacro %}
{% block body %}
<h1>{{ state.label }}</h1>
<p>State id: <code>{{ state.id }}</code></p>
{% if not state.settled %}
<p><strong>⚠ Did not settle:</strong> the page kept changing until the settle timeout,
so this snapshot is best-effort and may be incomplete.</p>
{% endif %}
{% if state.screenshot_image %}
<h2>Screenshot</h2>
{{ shot(state.screenshot_image, "Full-page screenshot of " ~ state.label) }}
{% endif %}

<h2>Actions</h2>
{% if state.elements %}
<table>
  <tr><th>Label</th><th>Type</th><th>Screen capture</th><th>Opened contents</th>
    <th>Destination / target state</th></tr>
  {% for el in state.elements %}
  <tr>
    <td>{{ el.label }}</td>
    <td><em>{{ el.type }}</em></td>
    <td>{% if el.screenshot %}{{ shot(el.screenshot, "Screenshot of " ~ el.label) }}
      {% else %}<em>none</em>{% endif %}</td>
    <td>{% if el.opened %}{{ shot(el.opened, "Opened contents of " ~ el.label) }}
      {% else %}<em>none</em>{% endif %}</td>
    <td>
      {% if el.dest_filename %}<a href="{{ el.dest_filename }}">{{ el.dest_label }}</a>
      {% else %}<em>none</em>{% endif %}</td>
  </tr>
  {% endfor %}
</table>
{% else %}<p><em>none</em></p>{% endif %}

{% if state.has_signals %}
<ul>
  <li>Accessibility nodes: <strong>{{ state.ax_node_count }}</strong></li>
  <li>Screenshot hash:
    {% if state.screenshot_hash %}<code>{{ state.screenshot_hash }}</code>
    {% else %}<em>not captured</em>{% endif %}</li>
</ul>
<h2>Console messages</h2>
{% if state.console %}<ul>{% for msg in state.console %}<li><code>{{ msg.text }}</code>
{% if msg.count > 1 %} <span class="count">× {{ msg.count }}</span>{% endif %}</li>
{% endfor %}</ul>{% else %}<p><em>none</em></p>{% endif %}
<h2>Storage keys</h2>
{% if state.storage %}<ul>{% for key in state.storage %}<li><code>{{ key }}</code></li>
{% endfor %}</ul>{% else %}<p><em>none</em></p>{% endif %}
<h2>Network requests</h2>
{% if state.network %}{% for group in state.network %}
<h3>{{ group.category }} <span class="count">({{ group.total }})</span></h3>
<ul>{% for url in group.rows %}<li><code>{{ url.text }}</code>
{% if url.count > 1 %} <span class="count">× {{ url.count }}</span>{% endif %}</li>
{% endfor %}</ul>
{% endfor %}{% else %}<p><em>none</em></p>{% endif %}
{% else %}
<p><em>No signal bundle was captured for this state.</em></p>
{% endif %}
{% endblock %}
"""

_TRANSITION = """{% extends "layout.html" %}
{% block title %}Transition {{ transition.from_label }} &rarr; {{ transition.to_label }}
{% endblock %}
{% block body %}
<h1>Transition</h1>
<p><a href="state-{{ transition.from_index }}.html">{{ transition.from_label }}</a>
  &mdash;<strong>{{ transition.action_name }}</strong>
  <em>({{ transition.action_role }})</em>&rarr;
  <a href="state-{{ transition.to_index }}.html">{{ transition.to_label }}</a></p>
{% if transition.recovered_via %}
<p><strong>Reached from behind a blocker:</strong> a covering layer
  (<code>{{ transition.recovered_via }}</code>) was cleared before this action could be
  fired.</p>
{% endif %}
{% if transition.has_signals %}
<h2>What this action changed</h2>
<ul>
  <li>Accessibility node delta: <strong>{{ transition.ax_node_delta }}</strong></li>
  <li>Screenshot changed: <strong>{{ transition.screenshot_label }}</strong></li>
</ul>
<h2>Console messages added</h2>
{% if transition.console_added %}<ul>{% for msg in transition.console_added %}
  <li><code>{{ msg }}</code></li>{% endfor %}</ul>{% else %}<p><em>none</em></p>
{% endif %}
<h2>Storage keys added</h2>
{% if transition.storage_added %}<ul>{% for key in transition.storage_added %}
  <li><code>{{ key }}</code></li>{% endfor %}</ul>{% else %}<p><em>none</em></p>
{% endif %}
<h2>Storage keys removed</h2>
{% if transition.storage_removed %}<ul>{% for key in transition.storage_removed %}
  <li><code>{{ key }}</code></li>{% endfor %}</ul>{% else %}<p><em>none</em></p>
{% endif %}
<h2>Network requests added</h2>
{% if transition.network_added %}<ul>{% for url in transition.network_added %}
  <li><code>{{ url }}</code></li>{% endfor %}</ul>{% else %}<p><em>none</em></p>
{% endif %}
{% else %}
<p><em>No signal diff was captured for this transition.</em></p>
{% endif %}
{% endblock %}
"""

# The help page (slice 6f) is a fixed, target-independent glossary of every term the
# other pages use, written in plain language for a reader who did not build Spoor (so no
# internal section references in the wording). It carries no captured values, so nothing
# on it needs redaction; it is linked from every page's nav via the shared layout.
_HELP = """{% extends "layout.html" %}
{% block title %}Help &amp; glossary — exploration wiki{% endblock %}
{% block body %}
<h1>Help &amp; glossary</h1>
<p>This wiki is a map of a site that Spoor explored automatically. It has an
  <a href="index.html">overview</a> with a diagram of the whole map, one page per
  <strong>state</strong> (a distinct screen), and one page per
  <strong>transition</strong> (what happened when Spoor activated one element on a
  screen). The terms each page uses are defined below.</p>

<h2>The map</h2>
<dl>
  <dt>State</dt>
  <dd>A distinct screen of the site. Spoor treats two screens as the same state when
    their structure is equivalent, so a state stands for a <em>kind</em> of screen, not
    one single visit to it.</dd>
  <dt>State id</dt>
  <dd>The fingerprint Spoor computes for a state from its structure. Two screens with
    the same id are considered the same state.</dd>
  <dt>Transition</dt>
  <dd>What happened when Spoor activated one element on a state: which action was taken
    and which screen it led to.</dd>
  <dt>Overview</dt>
  <dd>A diagram of the whole map — each box is a state, each arrow is an action leading
    from one state to another.</dd>
  <dt>Skipped actions</dt>
  <dd>Elements Spoor found but chose not to activate (for example, something that looked
    destructive on a site that is not a safe sandbox), listed with the reason.</dd>
  <dt>[REDACTED]</dt>
  <dd>Wherever a captured value looked like a secret — an authentication token, an API
    key, a session cookie — Spoor replaced it with this placeholder before writing the
    page, so no secret is shared.</dd>
</dl>

<h2>On a state page</h2>
<dl>
  <dt>Actions</dt>
  <dd>The interactive elements (buttons, links, form controls) Spoor found on the
    screen and could act on. Each row lists the element's <strong>Label</strong> (its
    visible or accessible name), its <strong>Type</strong> (the kind of control —
    button, link, and so on), a <strong>Screen capture</strong> of the element when one
    is available, an <strong>Opened contents</strong> picture of what a dropdown or list
    reveals when opened (when that was captured), and the
    <strong>Destination / target state</strong> — the screen reached after activating
    it, linking to what changed, or "none" if Spoor did not follow it.</dd>
  <dt>Accessibility nodes</dt>
  <dd>How many entries the screen exposes in the browser's accessibility tree — the
    structured description assistive technology reads. It is a rough measure of how much
    labelled, interactive content the screen has.</dd>
  <dt>Screenshot</dt>
  <dd>A full-page picture of the screen, shown only when screenshots were turned on for
    the run. Unlike every text value on these pages, a picture cannot have secrets
    automatically blanked out, so it is included only when someone deliberately opts
    in.</dd>
  <dt>Screenshot hash</dt>
  <dd>A short fingerprint of how the screen looks, used to tell visually different
    screens apart without storing the picture itself.</dd>
  <dt>Console messages</dt>
  <dd>Messages the page logged to the browser's developer console during the visit —
    errors, warnings, and debug output. Identical repeated lines are collapsed into one
    row with an "× count".</dd>
  <dt>Storage keys</dt>
  <dd>The names of the values the page kept in the browser's local and session storage
    (the values themselves are not shown).</dd>
  <dt>Network requests</dt>
  <dd>The addresses the page requested during the visit, grouped by kind — Documents,
    Scripts, Styles, Images, Fonts, Media, Data, Other — each with a count. Identical
    repeated requests are collapsed into one row with a count.</dd>
  <dt>Did not settle</dt>
  <dd>A warning that the page kept changing until Spoor's wait timed out, so the
    snapshot of this screen may be incomplete.</dd>
</dl>

<h2>On a transition page</h2>
<dl>
  <dt>Accessibility node delta</dt>
  <dd>How much the accessibility-node count changed because of the action — a positive
    number means the screen's structure grew, a negative one means it shrank.</dd>
  <dt>Screenshot changed</dt>
  <dd>Whether the screen's appearance fingerprint changed after the action.</dd>
  <dt>Console messages added</dt>
  <dd>Console lines that appeared as a result of the action.</dd>
  <dt>Storage keys added</dt>
  <dd>Names the action created in the browser's local or session storage.</dd>
  <dt>Storage keys removed</dt>
  <dd>Names the action deleted from the browser's local or session storage.</dd>
  <dt>Network requests added</dt>
  <dd>New addresses the page requested as a result of the action.</dd>
  <dt>Reached from behind a blocker</dt>
  <dd>The action was only reachable after Spoor cleared a covering layer — a cookie
    banner or dialog, for example — dismissing it the way a visitor would; the page
    names what was cleared.</dd>
</dl>
{% endblock %}
"""

_TEMPLATES = {
    "layout.html": _LAYOUT,
    "index.html": _INDEX,
    "state.html": _STATE,
    "transition.html": _TRANSITION,
    "help.html": _HELP,
}

# The placeholder secrets are replaced with, re-exported so callers/tests can assert
# on redacted output without reaching into the security module.
__all__ = ["build_pages", "render_wiki", "REDACTED"]
