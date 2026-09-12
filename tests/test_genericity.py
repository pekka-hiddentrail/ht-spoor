"""Tests for the §0 genericity checker (scripts/check_genericity.py).

The checker is itself a non-negotiable enforcement mechanism, so its detection
logic is unit-tested here rather than only exercised in CI.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "check_genericity", REPO_ROOT / "scripts" / "check_genericity.py"
)
assert _SPEC and _SPEC.loader
checker = importlib.util.module_from_spec(_SPEC)
# Register before exec so dataclass annotation resolution can find the module.
sys.modules["check_genericity"] = checker
_SPEC.loader.exec_module(checker)


def _check(source: str) -> list:
    return checker.check_source(Path("fake.py"), source)


def test_hardcoded_domain_is_flagged() -> None:
    violations = _check('if host == "netflix.com":\n    pass\n')
    assert len(violations) == 1
    assert violations[0].match == "netflix.com"
    assert violations[0].kind == "domain"


def test_public_ip_is_flagged() -> None:
    violations = _check('TARGET = "8.8.8.8"\n')
    assert [v.match for v in violations] == ["8.8.8.8"]


def test_localhost_and_loopback_allowed() -> None:
    source = 'SANDBOX = ("localhost", "127.0.0.1", "0.0.0.0")\n'
    assert _check(source) == []


def test_private_ip_allowed() -> None:
    assert _check('HOST = "192.168.1.10"\n') == []


def test_reserved_example_domains_allowed() -> None:
    assert _check('URL = "https://example.com/products"\n') == []


def test_conventional_paths_and_module_paths_not_flagged() -> None:
    # §2b probe paths and dotted module paths look domain-ish but are not hosts.
    source = (
        'PROBES = ["/openapi.json", "/swagger.json", "robots.txt"]\n'
        'MOD = "spoor.core.dispatcher"\n'
    )
    assert _check(source) == []


def test_domain_inside_a_url_is_flagged() -> None:
    violations = _check('BASE = "https://api.stripe.com/v1/charges"\n')
    assert [v.match for v in violations] == ["api.stripe.com"]


def test_filename_like_extensions_not_flagged() -> None:
    # `.sh`/`.so`/`.csv` collide with file extensions and are not treated as TLDs.
    assert _check('FILES = ["build.sh", "lib.so", "data.csv"]\n') == []


def test_docstring_mention_is_not_flagged() -> None:
    source = '"""Handles the shopify.com convention."""\nX = 1\n'
    assert _check(source) == []


def test_repo_core_is_clean() -> None:
    # The shipped source must always pass its own check.
    assert checker.find_violations(REPO_ROOT) == []
