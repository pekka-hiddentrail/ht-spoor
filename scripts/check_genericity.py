"""Enforce ROADMAP.md §0 / the CLAUDE.md hard rule: core is never site-tailored.

Scans Spoor's shipped source for hardcoded hostnames / domain strings / public
IPs. Finding one means the core has baked in knowledge of a specific website,
which §0 forbids. The only allowed homes for site-specific strings are:

  - `spoor/recognizers/`  the pluggable platform-convention table (§0, §2)
  - `fixtures/`           test fixtures, not shipped core logic (§5)

Generic infrastructure addresses (localhost, loopback, unspecified, private
ranges) are allowed everywhere: they are not knowledge of a *target*, they are
how the sandbox registry (§2e) recognises a local target generically. RFC 2606
reserved example domains (`example.com`, `.test`, `.invalid`, `.localhost`) and
RFC 5737 test-net IP ranges are allowed as documentation placeholders.

Detection works on string *constants* parsed from the AST (module/class/function
docstrings excluded) — prose in comments or docstrings that merely mentions a
site is fine; a hostname baked into code logic is not.

Run:  python scripts/check_genericity.py
Exits non-zero (fails CI) if any violation is found.
"""

from __future__ import annotations

import ast
import ipaddress
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Directories (relative to repo root) whose Python source is subject to §0.
SCAN_ROOTS = ("spoor",)

# Package name (leaf directory) allowed to contain site/platform strings.
EXCLUDED_PACKAGES = {"recognizers"}

# Hostnames allowed anywhere — generic infra, not a specific target.
ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",  # noqa: S104 - unspecified address, not a bind directive here
    "::1",
    "::",
}

# Reserved second-level example domains (RFC 2606) allowed as placeholders.
# (RFC 2606 example/test/invalid/localhost TLDs are simply absent from
# KNOWN_TLDS below, so they never register as domains in the first place.)
ALLOWED_DOMAINS = {"example.com", "example.org", "example.net"}

# A dotted string is only treated as a domain if its final label is a real,
# registrable TLD. This is the key to not flagging dotted module paths
# (`spoor.core.dispatcher`), config keys, or filenames (`openapi.json`,
# `robots.txt`). File-extension-colliding TLDs (`.sh`, `.so`, `.io` is fine but
# `.py`/`.js` etc.) are deliberately omitted: the tiny cost is that a target on
# such a TLD could slip past this check, caught instead by review and the §0
# rule itself. Extend this set (via PR) if a real domain uses a TLD not listed.
KNOWN_TLDS = {
    # generic
    "com", "org", "net", "io", "co", "dev", "app", "ai", "info", "biz",
    "xyz", "me", "tv", "cloud", "tech", "store", "online", "site", "shop",
    "gov", "edu", "mil", "int",
    # country-code (common; ambiguous file-ext collisions like "sh"/"so" omitted)
    "uk", "us", "ca", "de", "fr", "jp", "cn", "ru", "au", "nl", "se", "no",
    "fi", "es", "it", "ch", "br", "eu", "kr", "tw", "hk", "sg", "nz", "za",
    "mx", "pl", "cz", "dk", "pt", "ie", "ar", "cl",
}

_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    match: str
    kind: str  # "domain" | "ip"

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: hardcoded {self.kind} {self.match!r}"


def _ip_is_allowed(ip: ipaddress.IPv4Address) -> bool:
    # Loopback, unspecified, private, link-local, and RFC 5737 test-net ranges
    # are generic/local — not a specific external target.
    if ip.is_loopback or ip.is_unspecified or ip.is_private or ip.is_link_local:
        return True
    testnet = (
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("198.51.100.0/24"),
        ipaddress.ip_network("203.0.113.0/24"),
    )
    return any(ip in net for net in testnet)


def _check_string(value: str) -> list[tuple[str, str]]:
    """Return (match, kind) pairs in `value` that violate §0."""
    hits: list[tuple[str, str]] = []
    for m in _DOMAIN_RE.finditer(value):
        host = m.group(0)
        tld = host.rsplit(".", 1)[-1].lower()
        if tld not in KNOWN_TLDS:
            continue  # dotted module path, config key, or filename — not a host
        if host.lower() in ALLOWED_HOSTS or host.lower() in ALLOWED_DOMAINS:
            continue
        hits.append((host, "domain"))
    for m in _IPV4_RE.finditer(value):
        try:
            ip = ipaddress.IPv4Address(m.group(0))
        except ipaddress.AddressValueError:
            continue  # e.g. a version-like "3.400.1.2" — not an IP
        if _ip_is_allowed(ip):
            continue
        hits.append((str(ip), "ip"))
    return hits


def _string_constants(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield (lineno, value) for str constants, excluding docstrings."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            out.append((node.lineno, node.value))
    return out


def check_source(path: Path, source: str) -> list[Violation]:
    """Check one file's source text, returning any §0 violations."""
    tree = ast.parse(source, filename=str(path))
    violations: list[Violation] = []
    for lineno, value in _string_constants(tree):
        for match, kind in _check_string(value):
            violations.append(Violation(path, lineno, match, kind))
    return violations


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        parts = set(path.parts)
        if parts & EXCLUDED_PACKAGES or "__pycache__" in parts:
            continue
        files.append(path)
    return files


def find_violations(repo_root: Path) -> list[Violation]:
    """Scan every in-scope source file under `repo_root` for §0 violations."""
    violations: list[Violation] = []
    for root_name in SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in _iter_files(root):
            violations.extend(
                check_source(path, path.read_text(encoding="utf-8"))
            )
    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    violations = find_violations(repo_root)
    if violations:
        print("§0 genericity check FAILED — core must never be site-tailored:")
        for v in violations:
            print(f"  {v}")
        print(
            "\nMove site/platform-specific strings into spoor/recognizers/, or "
            "fix the general mechanism. See ROADMAP.md §0 / CLAUDE.md."
        )
        return 1
    print("§0 genericity check passed: no hardcoded targets in core.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
