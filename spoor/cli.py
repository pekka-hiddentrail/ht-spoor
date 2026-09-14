"""Spoor CLI entry point (ROADMAP.md §2a).

The whole product surface on top of the resolution/extraction machinery:
`spoor run config.yaml -o output.json`. The `run` command dispatches the config
through the resolution ladder (§2), writes the chosen output format, and prints a
run summary (§2d observability); later phases add their own commands as they land.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.observability import RunSummary
from spoor.operational.output import resolve_format, write_records
from spoor.serving.store import MapEntry, MapStore, shareable_api_surface

app = typer.Typer(
    name="spoor",
    help="Give your agents a map of the web.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Give your agents a map of the web.

    A callback (even a no-op) keeps `run` as an explicit subcommand, so the
    documented `spoor run config.yaml` interface holds instead of Typer
    collapsing a single-command app into `spoor config.yaml`.
    """


@app.command()
def run(
    config: Annotated[Path, typer.Argument(help="Path to a config file.")],
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Where to write output.")
    ] = Path("output.json"),
    output_format: Annotated[
        str | None,
        typer.Option(
            "-f",
            "--format",
            help="Output format (json, jsonl, csv); inferred from -o if omitted.",
        ),
    ] = None,
) -> None:
    """Run a config against its target and write the extracted records."""
    cfg = load_config(config.read_text(encoding="utf-8"))
    try:
        fmt = resolve_format(output, output_format)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    result = extract.run_report(cfg)
    write_records(result.records, cfg, output, fmt)
    # Remember this run in the local map so the read-only serving layer (§2f)
    # can answer for this URL later without re-crawling — the records plus the
    # §2h-safe projection of the observed API surface.
    surface = shareable_api_surface(
        api_spec=result.api_spec,
        graphql=result.graphql,
        synthesized_spec=result.synthesized_spec,
        action_correlation=result.action_correlation,
    )
    MapStore().record(
        cfg.target,
        result.records,
        tier=result.tier,
        api_surface=surface,
        # Kept local-only so a caller-forced recheck (§2f) can re-run this exact
        # extraction; never projected into a served response.
        config=cfg.model_dump(mode="json"),
    )
    typer.echo(f"Wrote {len(result.records)} record(s) to {output} ({fmt})")
    typer.echo(RunSummary.from_result(result).render())


@app.command()
def explore(
    url: Annotated[str, typer.Argument(help="URL to start exploring from.")],
    sandbox: Annotated[
        bool,
        typer.Option(
            "--sandbox",
            help=(
                "Declare this target a sandbox so destructive actions (delete, buy, "
                "pay, ...) are exercised. Only ever use this on a local or test "
                "system you own; on any real site those actions are always skipped."
            ),
        ),
    ] = False,
    max_states: Annotated[
        int | None,
        typer.Option(help="Stop after discovering this many distinct states."),
    ] = None,
    max_requests: Annotated[
        int | None, typer.Option(help="Stop after firing this many actions.")
    ] = None,
    max_seconds: Annotated[
        float | None, typer.Option(help="Stop after this many seconds of wall-clock.")
    ] = None,
) -> None:
    """Explore a target with no config, mapping its state-action graph.

    Points a headless browser at the URL, discovers the actionable elements on each
    screen, fires each one, and records where it leads — building a graph of what
    happens when you press every button. Destructive actions are only ever performed
    against a sandbox you declare with --sandbox; on any other site they are always
    skipped and never fired. Bound the run with the budget options, and press Ctrl-C
    to stop it early at any time.
    """
    import signal

    from spoor.exploration.control import RunBudget, RunController
    from spoor.exploration.driver import PlaywrightDriver
    from spoor.exploration.explorer import explore as explore_target

    try:
        budget = RunBudget(
            max_states=max_states,
            max_requests=max_requests,
            max_seconds=max_seconds,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    controller = RunController(budget)
    # Ctrl-C throws the kill switch, so the run stops gracefully at the next action
    # rather than aborting mid-click. Restore the previous handler afterwards so the
    # run doesn't leave a global side effect behind.
    previous_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: controller.kill())
    try:
        with PlaywrightDriver(url) as driver:
            graph = explore_target(
                driver, target=url, controller=controller, declared_sandbox=sandbox
            )
    finally:
        signal.signal(signal.SIGINT, previous_handler)

    typer.echo(f"Explored {url}")
    typer.echo(f"  states discovered: {len(graph.states)}")
    typer.echo(f"  transitions:       {len(graph.transitions)}")
    typer.echo(f"  actions skipped:   {len(graph.skipped)}")
    if not sandbox and graph.skipped:
        typer.echo(
            "  (destructive actions were skipped — this target is not a declared "
            "sandbox)"
        )


@app.command()
def serve(
    host: Annotated[
        str, typer.Option(help="Address to bind the read-only API server to.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to serve on.")] = 8000,
    recheck: Annotated[
        bool,
        typer.Option(
            "--recheck",
            help=(
                "Also allow forcing a re-check of a mapped URL (re-runs its "
                "extraction and refreshes the map). Off by default."
            ),
        ),
    ] = False,
) -> None:
    """Serve the captured map over a read-only REST API (ROADMAP.md §2f).

    Answers questions about what earlier runs mapped; it never changes a target.
    By default every route only reads the stored map. With --recheck it also
    accepts a request to re-check a mapped URL: that re-runs the URL's extraction
    (a fresh read of the site, never a change to it) and refreshes the map.
    Requires the optional serving extras: pip install 'ht-spoor[serve]'.
    """
    try:
        import uvicorn
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via message
        raise typer.BadParameter(
            "The serving extras are not installed. Run: pip install 'ht-spoor[serve]'"
        ) from exc
    from spoor.serving.api import create_app

    store = MapStore()
    recheck_fn = _build_recheck(store) if recheck else None
    uvicorn.run(  # pragma: no cover
        create_app(store, recheck=recheck_fn), host=host, port=port
    )


@app.command(name="serve-mcp")
def serve_mcp(
    recheck: Annotated[
        bool,
        typer.Option(
            "--recheck",
            help=(
                "Also expose a tool to force a re-check of a mapped URL (re-runs "
                "its extraction and refreshes the map). Off by default."
            ),
        ),
    ] = False,
) -> None:
    """Serve the captured map to agents over a read-only MCP server (stdio).

    The same answers as `spoor serve`, exposed as MCP tools for an agent to
    consult; it never changes a target. With --recheck it also exposes a tool to
    re-check a mapped URL (re-runs the URL's extraction and refreshes the map — a
    fresh read of the site, never a change to it). Requires the optional serving
    extras: pip install 'ht-spoor[serve]'.
    """
    try:
        from spoor.serving.mcp_server import create_mcp_server
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via message
        raise typer.BadParameter(
            "The serving extras are not installed. Run: pip install 'ht-spoor[serve]'"
        ) from exc
    import asyncio

    store = MapStore()
    recheck_fn = _build_recheck(store) if recheck else None
    server = create_mcp_server(store, recheck=recheck_fn)
    asyncio.run(server.run_stdio_async())  # pragma: no cover


def _build_recheck(store: MapStore) -> Callable[[str], MapEntry | None]:
    """Bind the force-recheck seam to a store (lazy import keeps core light)."""
    from spoor.serving.recheck import recheck_url

    def recheck(url: str) -> MapEntry | None:
        return recheck_url(store, url)

    return recheck


if __name__ == "__main__":  # pragma: no cover
    app()
