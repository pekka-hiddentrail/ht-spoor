"""Spoor CLI entry point (ROADMAP.md §2a).

The whole product surface on top of the resolution/extraction machinery:
`spoor run config.yaml -o output.json`. The `run` command drives a tier-1
extraction and writes the chosen output format; later phases add their own
commands as they land.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from spoor.core import extract
from spoor.core.config import load_config
from spoor.operational.output import resolve_format, write_records

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
    output_format: Annotated[
        str | None,
        typer.Option(
            "-f",
            "--format",
            help="Output format (json, jsonl, csv); inferred from -o if omitted.",
        ),
    ] = None,
) -> None:
    """Run an extraction config against its target (Phase 1)."""
    cfg = load_config(config.read_text(encoding="utf-8"))
    try:
        fmt = resolve_format(output, output_format)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    records = extract.run(cfg)
    write_records(records, cfg, output, fmt)
    typer.echo(f"Wrote {len(records)} record(s) to {output} ({fmt})")


if __name__ == "__main__":  # pragma: no cover
    app()
