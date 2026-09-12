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

Planned (added as their phases need them):

- **More static fixture pages** — one mechanism each (class name changes every
  reload → tier-3 healing; JS-required field → tier-2 escalation; WebSocket
  traffic → §2c capture).
- **`docker-compose.yml` test bench** — the four archetype apps at once, each
  declared `sandbox: true` so §2e exploration can exercise destructive actions
  safely: OWASP Juice Shop, Sauce Demo, a self-hosted ERPNext/Odoo, a
  self-hosted Netflix-clone.

Public scraping-practice sandboxes (`books.toscrape.com`,
`quotes.toscrape.com`) are used for integration tests/demos but are not vendored
here.
