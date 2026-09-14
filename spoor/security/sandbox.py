"""Sandbox registry for exploration mode (ROADMAP.md §2e / §2h).

Exploration may perform destructive/irreversible actions *only* against a sandbox:
a target the operator controls. This module answers the one question "is this
target a sandbox?", so the interaction gate (`spoor/exploration/safety.py`) can
enforce the §2e non-negotiable that destructive actions never fire on a real site.

A target counts as a sandbox when either:

- its host is loopback — ``localhost``, ``127.0.0.0/8`` (any ``127.*``), or IPv6
  ``::1`` — i.e. self-hosted on the operator's own machine; or
- the operator has explicitly declared it one (``sandbox: true`` in config), passed
  in as ``declared``.

Nothing else qualifies today. Tightening the registry (e.g. accepting private-range
IPs, or refusing a config's declaration unless the host is also loopback) is known,
accepted future work — see §9 — not something this slice decides. Deliberately no
site knowledge here: the rule is generic to any target.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def _is_loopback_host(host: str) -> bool:
    """Whether `host` (a URL hostname) is loopback: ``localhost`` or a loopback IP.

    Loopback IPs are decided by the `ipaddress` module — the whole ``127.0.0.0/8``
    range and IPv6 ``::1`` — never by string prefix, so a *hostname* like
    ``127.evil.com`` (attacker-registerable, not loopback) is correctly rejected.
    """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # Not an IP literal (an ordinary hostname) — not loopback.
        return False


def is_sandbox(target: str, *, declared: bool = False) -> bool:
    """Whether `target` may host destructive exploration actions (§2e).

    True when the operator declared it a sandbox, or its host is loopback
    (``localhost``, any ``127.0.0.0/8`` address, or IPv6 ``::1``). Everything else
    is a real target and returns False — the caller must then skip destructive
    actions against it.
    """
    if declared:
        return True
    return _is_loopback_host((urlsplit(target).hostname or "").lower())
