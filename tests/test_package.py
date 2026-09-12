"""Phase 0 sanity: the package and its subpackages import cleanly."""

import importlib

import spoor

SUBPACKAGES = [
    "core",
    "recognizers",
    "api_discovery",
    "signals",
    "operational",
    "exploration",
    "serving",
    "testgen",
    "security",
]


def test_version_is_exposed() -> None:
    assert isinstance(spoor.__version__, str)


def test_subpackages_import() -> None:
    for name in SUBPACKAGES:
        module = importlib.import_module(f"spoor.{name}")
        assert module is not None
