# `fixtures/` — test fixtures (ROADMAP.md §5.1)

Fixtures are the opposite of integrations (§0): they exist purely to prove the
**generic** tiers hold up across different architectural shapes. If a fixture
only passes with a special case added for it, that's a bug in the general
mechanism, never a reason to add the special case.

Present:

- **`static/`** — hand-built HTML fixtures for §2a extraction tests
  (`products.html`, `listing.html`, `catalog/page-{1,2,3}.html` for
  pagination, `feed.html` for the tier-2 infinite-scroll case). Served
  deterministically in tests via an `httpx.MockTransport` — no sockets, no
  network. Deterministic unit-test inputs.
- **`docker-compose.yml`** — the §5.1 archetype bench. Phase 1 stands up only
  **OWASP Juice Shop** (an Angular SPA — a real, uncontrolled tier-2 target);
  the other three archetypes join when the phases that can exercise them arrive
  (see the "Phase-1 in-vivo bench" decision in ROADMAP §5.1). Bring it up with
  `docker compose -f fixtures/docker-compose.yml up -d`. The integration tests
  under `tests/` skip when it isn't reachable, so the fast unit gate stays
  Docker-free.

Planned (added as their phases need them):

- **More static fixture pages** — one mechanism each (class name changes every
  reload → tier-3 healing; JS-required field → tier-2 escalation; WebSocket
  traffic → §2c capture).
- **The rest of the archetype matrix** — Sauce Demo, a self-hosted ERPNext/Odoo,
  and a self-hosted Netflix-clone, added to `docker-compose.yml` as their phases
  (auth, exploration) need them, each declared `sandbox: true`.

Public scraping-practice sandboxes (`books.toscrape.com`,
`quotes.toscrape.com`) are used for integration tests/demos but are not vendored
here.
