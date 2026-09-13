# Bring-your-own-session — authenticated targets via a supplied storage state
# (ROADMAP.md §2h, §2c).
#
# §2h decided auth deliberately narrow for v1: Spoor does NOT implement login,
# MFA, or SSO flows — a large, fragile, per-provider surface that would violate
# §0's no-tailoring rule almost by definition. Instead the user authenticates
# once in a real browser and supplies the resulting storage state — Playwright's
# context.storage_state() JSON (cookies + per-origin localStorage) — as a run
# input via the config's `session:` path. This is the read/input counterpart of
# the storage-state *capture* signal (storage_state.feature): that one writes the
# file, this one consumes it. Multi-role is just running the same config once per
# supplied session file (one per role) — no new machinery.
#
# The supplied state is secret-bearing and stays a local-only input: its cookies
# are loaded into the static tier's fetch and the whole state (cookies +
# localStorage) into the browser tier's context, but its contents are NEVER
# echoed to shared output — nothing here writes the session into the run summary
# or the records (§2h). The static tier (no JS) can use cookie-based auth; a
# target gated behind a localStorage token renders empty without a browser, so it
# naturally escalates to the browser tier, which applies the full state. Nothing
# here is site-specific (§0): the same file format and loading run for every
# target. A missing or malformed session file fails the run loudly rather than
# silently running unauthenticated.

Feature: A run authenticates with a supplied browser session (bring-your-own-session)
  As someone scraping a login-gated app
  I want to hand Spoor a session I captured in my own browser
  So that a run reaches authenticated content without Spoor automating any login

  Scenario: The static tier sends the session's cookies to a cookie-gated page
    Given an auth-aware fixture server that reveals items only to an authenticated session
    And a session file carrying the server's session cookie
    When I run a static config with that session
    Then the members-only item is extracted

  Scenario: A static run without a session sees no authenticated content
    Given an auth-aware fixture server that reveals items only to an authenticated session
    When I run a static config with no session
    Then no item is extracted

  Scenario: The browser tier loads the session's localStorage to reach JS-gated content
    Given an auth-aware fixture server whose items render only for a localStorage token
    And a session file carrying that localStorage token
    When I run a browser config with that session
    Then the members-only item is extracted

  Scenario: A missing session file fails the run loudly
    Given an auth-aware fixture server that reveals items only to an authenticated session
    And a session path that points to no file
    When I run a static config with that session expecting an error
    Then the run raises a session error and fetches nothing
