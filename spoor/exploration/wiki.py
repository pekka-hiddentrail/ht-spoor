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
- **Hash-only screenshots**: the captured screenshot signal is a perceptual hash
  (5c-ii), so a state page shows its hash and a transition page reports whether the
  screenshot *changed* — no image bytes are embedded yet (a deliberate follow-on).

The wiki is a **shared-output surface**, so §2h redaction is mandatory and applied two
ways, defensively overlapping: every captured value rendered (console messages,
storage keys, network URLs, action labels, and the operator-supplied target URL) is
passed through `spoor.security.redaction.redact` before rendering, and Jinja2
autoescaping — on for every template — independently neutralizes any HTML/script a
captured value might carry. Nothing here is site-specific (§0): the same templates
render every target's graph.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import DictLoader, Environment, select_autoescape

from spoor.exploration.graph import ExplorationGraph, SkippedAction, Transition
from spoor.security.redaction import REDACTED, redact

# Length of the state-id prefix shown as a human-readable label. State ids are
# 64-char SHA-256 hex digests (slice 2); the full id stays on the state page, but a
# 12-char prefix is enough to tell states apart in links and the overview diagram.
_SHORT_ID = 12
_UNNAMED = "(unnamed)"


def _redact_all(items: tuple[str, ...]) -> list[str]:
    """Redact every captured string before it reaches the shared wiki (§2h)."""
    return [redact(item) for item in items]


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


def _mermaid(graph: ExplorationGraph, state_index: dict[str, int]) -> str:
    """A Mermaid `graph LR` source for the whole state-action graph.

    Nodes are the states (labelled by their short id); edges are the transitions
    (labelled by the redacted action name). Endpoints not in the state index are
    skipped defensively, though the explorer always records a transition's states.
    """
    lines = ["graph LR"]
    for sid, i in state_index.items():
        lines.append(f'  S{i}["{_mermaid_safe(sid[:_SHORT_ID])}"]')
    for transition in graph.transitions:
        src = state_index.get(transition.from_state)
        dst = state_index.get(transition.to_state)
        if src is None or dst is None:
            continue
        label = _mermaid_safe(_label(transition.action.name))
        lines.append(f'  S{src} -->|"{label}"| S{dst}')
    return "\n".join(lines)


def _state_view(
    graph: ExplorationGraph, sid: str, index: int
) -> dict[str, object]:
    """The redacted, template-ready view of one state node."""
    node = graph.node(sid)
    signals = node.signals
    return {
        "index": index,
        "id": sid,
        "short_id": sid[:_SHORT_ID],
        "filename": f"state-{index}.html",
        "has_signals": signals is not None,
        "settled": True if signals is None else signals.settled,
        "ax_node_count": None if signals is None else signals.ax_node_count,
        "console": [] if signals is None else _redact_all(signals.console_messages),
        "storage": [] if signals is None else _redact_all(signals.storage_keys),
        "network": [] if signals is None else _redact_all(signals.network_requests),
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


def _transition_view(
    transition: Transition, index: int, states: list[str]
) -> dict[str, object]:
    """The redacted, template-ready view of one transition edge."""
    signals = transition.signals
    return {
        "index": index,
        "filename": f"transition-{index}.html",
        "from_id": transition.from_state,
        "from_short": transition.from_state[:_SHORT_ID],
        "from_index": states.index(transition.from_state),
        "to_id": transition.to_state,
        "to_short": transition.to_state[:_SHORT_ID],
        "to_index": states.index(transition.to_state),
        "action_name": _label(transition.action.name),
        "action_role": transition.action.role,
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


def build_pages(graph: ExplorationGraph, *, target: str) -> dict[str, str]:
    """Render `graph` into a map of wiki filename → HTML (§2e slice 6a).

    Pure: builds the whole static site in memory, touching no disk and no browser, so
    it is fully unit/BDD testable. Every captured value is redacted (§2h) and every
    template autoescapes, so nothing raw or executable reaches a page. `render_wiki`
    is the thin writer around it.
    """
    states = graph.states
    state_index = {sid: i for i, sid in enumerate(states)}
    state_views = [_state_view(graph, sid, i) for i, sid in enumerate(states)]
    transition_views = [
        _transition_view(t, j, states) for j, t in enumerate(graph.transitions)
    ]
    skip_views = [_skip_view(s, states) for s in graph.skipped]

    # A state's outgoing transitions, so each state page links onward through its edges.
    for view in state_views:
        view["outgoing"] = [
            tv for tv in transition_views if tv["from_index"] == view["index"]
        ]

    env = _environment()
    safe_target = redact(target)
    pages: dict[str, str] = {
        "index.html": env.get_template("index.html").render(
            target=safe_target,
            states=state_views,
            transitions=transition_views,
            skipped=skip_views,
            mermaid=_mermaid(graph, state_index),
        )
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


def render_wiki(graph: ExplorationGraph, out_dir: Path, *, target: str) -> list[Path]:
    """Write the wiki for `graph` under `out_dir`, returning the paths written.

    Creates `out_dir` (and parents) if needed and writes each page from `build_pages`
    as UTF-8. Paths are returned sorted for a stable, testable result.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, html in build_pages(graph, target=target).items():
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
    </style>
  </head>
  <body>
    <nav><a href="index.html">&larr; Overview</a> &middot;
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
  <li><a href="{{ state.filename }}">State {{ state.short_id }}</a></li>
  {% endfor %}
</ul>

<h2>Transitions</h2>
<ul>
  {% for transition in transitions %}
  <li><a href="{{ transition.filename }}">{{ transition.from_short }}
    &mdash;{{ transition.action_name }}&rarr; {{ transition.to_short }}</a></li>
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
{% block title %}State {{ state.short_id }}{% endblock %}
{% block body %}
<h1>State {{ state.short_id }}</h1>
<p>State id: <code>{{ state.id }}</code></p>
{% if not state.settled %}
<p><strong>⚠ Did not settle:</strong> the page kept changing until the settle timeout,
so this snapshot is best-effort and may be incomplete.</p>
{% endif %}
{% if state.has_signals %}
<ul>
  <li>Accessibility nodes: <strong>{{ state.ax_node_count }}</strong></li>
  <li>Screenshot hash:
    {% if state.screenshot_hash %}<code>{{ state.screenshot_hash }}</code>
    {% else %}<em>not captured</em>{% endif %}</li>
</ul>
<h2>Console messages</h2>
{% if state.console %}<ul>{% for msg in state.console %}<li><code>{{ msg }}</code></li>
{% endfor %}</ul>{% else %}<p><em>none</em></p>{% endif %}
<h2>Storage keys</h2>
{% if state.storage %}<ul>{% for key in state.storage %}<li><code>{{ key }}</code></li>
{% endfor %}</ul>{% else %}<p><em>none</em></p>{% endif %}
<h2>Network requests</h2>
{% if state.network %}<ul>{% for url in state.network %}<li><code>{{ url }}</code></li>
{% endfor %}</ul>{% else %}<p><em>none</em></p>{% endif %}
{% else %}
<p><em>No signal bundle was captured for this state.</em></p>
{% endif %}

<h2>Actions here</h2>
{% if state.actions %}
<ul>{% for action in state.actions %}<li>{{ action.name }}
  <em>({{ action.role }})</em></li>{% endfor %}</ul>
{% else %}<p><em>none</em></p>{% endif %}

<h2>Outgoing transitions</h2>
{% if state.outgoing %}
<ul>{% for transition in state.outgoing %}
  <li><a href="{{ transition.filename }}">{{ transition.action_name }}
    &rarr; State {{ transition.to_short }}</a></li>
{% endfor %}</ul>
{% else %}<p><em>none</em></p>{% endif %}
{% endblock %}
"""

_TRANSITION = """{% extends "layout.html" %}
{% block title %}Transition {{ transition.from_short }} &rarr; {{ transition.to_short }}
{% endblock %}
{% block body %}
<h1>Transition</h1>
<p><a href="state-{{ transition.from_index }}.html">State
  {{ transition.from_short }}</a> &mdash;<strong>{{ transition.action_name }}</strong>
  <em>({{ transition.action_role }})</em>&rarr;
  <a href="state-{{ transition.to_index }}.html">State {{ transition.to_short }}</a></p>
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

_TEMPLATES = {
    "layout.html": _LAYOUT,
    "index.html": _INDEX,
    "state.html": _STATE,
    "transition.html": _TRANSITION,
}

# The placeholder secrets are replaced with, re-exported so callers/tests can assert
# on redacted output without reaching into the security module.
__all__ = ["build_pages", "render_wiki", "REDACTED"]
