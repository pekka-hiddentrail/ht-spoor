"""Test automation run generation (ROADMAP.md §2g).

Exports a captured map (a §2a run or a §2e exploration graph) as generated
assertion-style regression tests or human-readable test plans — never
hand-written. Consumes the map; produces no new capture.
"""

from spoor.testgen.pytest_gen import build_tests, render_suite

__all__ = ["build_tests", "render_suite"]
