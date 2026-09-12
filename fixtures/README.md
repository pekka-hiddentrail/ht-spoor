# `fixtures/` — test fixtures (ROADMAP.md §5.1)

Fixtures are the opposite of integrations (§0): they exist purely to prove the
**generic** tiers hold up across different architectural shapes. If a fixture
only passes with a special case added for it, that's a bug in the general
mechanism, never a reason to add the special case.

Planned contents (added as their phases need them):

- **Static local fixture pages** — hand-built HTML/JS, one mechanism each
  (class name changes every reload → tier-3 healing; JS-required field → tier-2
  escalation; WebSocket traffic → §2c capture). Deterministic unit-test inputs.
- **`docker-compose.yml` test bench** — the four archetype apps at once, each
  declared `sandbox: true` so §2e exploration can exercise destructive actions
  safely: OWASP Juice Shop, Sauce Demo, a self-hosted ERPNext/Odoo, a
  self-hosted Netflix-clone.

Public scraping-practice sandboxes (`books.toscrape.com`,
`quotes.toscrape.com`) are used for integration tests/demos but are not vendored
here.
