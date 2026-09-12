"""Spoor CLI entry point (ROADMAP.md §2a).

The whole product surface on top of the resolution/extraction machinery:
`spoor run config.yaml -o output.json`. Commands raise NotImplementedError
until their phase lands — the scaffold exists so wiring and packaging are real
from Phase 0, not the behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from spoor.core import extract
from spoor.core.config import load_config

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
    config: Annotated[Path, typer.Argument(help="Path to a §2a config file.")],
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Where to write output.")
    ] = Path("output.json"),
) -> None:
    """Run an extraction config against its target (Phase 1)."""
    cfg = load_config(config.read_text(encoding="utf-8"))
    records = extract.run(cfg)
    output.write_text(json.dumps(records, indent=2), encoding="utf-8")
    typer.echo(f"Wrote {len(records)} record(s) to {output}")


if __name__ == "__main__":  # pragma: no cover
    app()
