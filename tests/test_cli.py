"""End-to-end CLI tests for `spoor run` output wiring (ROADMAP.md §2a, §2d).

`extract.run_report` is monkeypatched to a fixed `RunResult` so the CLI surface —
format selection, the output pipeline, and the run summary — is exercised without
any network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from spoor import cli
from spoor.core import extract
from spoor.core.extract import RunResult

runner = CliRunner()


def _stub_result() -> RunResult:
    return RunResult(
        records=[{"title": "A", "price": 1.0}],
        tier=1,
        pages_fetched=1,
        tiers_attempted=[1],
    )

_CONFIG = """
target: http://localhost:8000/x.html
fields:
  title: { selector: "h1" }
  price: { selector: ".price", type: number }
"""


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(_CONFIG, encoding="utf-8")
    return path


def test_run_infers_csv_from_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extract, "run_report", lambda cfg: _stub_result())
    out = tmp_path / "out.csv"
    result = runner.invoke(
        cli.app, ["run", str(_config_file(tmp_path)), "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8").splitlines()[0] == "title,price"


def test_run_format_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extract, "run_report", lambda cfg: _stub_result())
    out = tmp_path / "out.dat"
    result = runner.invoke(
        cli.app,
        ["run", str(_config_file(tmp_path)), "-o", str(out), "-f", "json"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8")) == [
        {"title": "A", "price": 1.0}
    ]


def test_bad_format_aborts_before_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def _record_call(cfg: object) -> RunResult:
        calls["n"] += 1
        return RunResult()

    monkeypatch.setattr(extract, "run_report", _record_call)
    out = tmp_path / "out.dat"  # unknown extension, no --format
    result = runner.invoke(
        cli.app, ["run", str(_config_file(tmp_path)), "-o", str(out)]
    )
    assert result.exit_code != 0
    assert calls["n"] == 0  # format is resolved before anything is fetched
    assert not out.exists()
