"""Spoor CLI entry point (ROADMAP.md §2a).

The whole product surface on top of the resolution/extraction machinery:
`spoor run config.yaml -o output.json`. Commands raise NotImplementedError
until their phase lands — the scaffold exists so wiring and packaging are real
from Phase 0, not the behaviour.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(
    name="spoor",
    help="Give your agents a map of the web.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def run(
    config: Path = typer.Argument(..., help="Path to a declarative §2a config file."),
    output: Path = typer.Option(
        Path("output.json"), "-o", "--output", help="Where to write structured output."
    ),
) -> None:
    """Run an extraction config against its target (Phase 1)."""
    raise NotImplementedError(
        "Extraction is implemented in Phase 1 (ROADMAP.md §4, §2a)."
    )


if __name__ == "__main__":  # pragma: no cover
    app()
