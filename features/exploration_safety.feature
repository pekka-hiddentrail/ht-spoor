# Exploration safety: destructive actions are sandbox-only — ROADMAP.md §2e.
#
# The first slice of exploration mode (§2e) is its safety foundation, built before
# anything that can fire an action exists. Two pieces plus the gate that combines
# them: a sandbox registry (is this target local/self-hosted or explicitly declared
# a sandbox?) and a destructive-action classifier (does this action's label/role
# read as delete/buy/pay/confirm/log-out?).
#
# NON-NEGOTIABLE (§2e/CLAUDE.md): destructive/irreversible actions are sandbox-only
# and NON-CONFIGURABLE. Against a sandbox (localhost / 127.0.0.1, or a target
# explicitly declared `sandbox: true`) the gate may perform them; against anything
# else — any real external site — they are ALWAYS skipped and logged as skipped,
# and there is deliberately no flag or option that relaxes this. Non-destructive
# actions are performed anywhere. The worst case for exploring a real, unvetted
# site is "missed a state", never "placed a real order" or "deleted real data".

Feature: Exploration performs destructive actions only inside a sandbox
  As someone pointing autonomous exploration at a target
  I want destructive actions gated to sandboxes I control
  So that exploring a real site can never place an order or delete real data

  Scenario Outline: Local and self-hosted targets are recognized as sandboxes
    Given an exploration target "<url>"
    Then the target is recognized as a sandbox

    Examples:
      | url                     |
      | http://localhost:3000/  |
      | https://localhost/      |
      | http://127.0.0.1:8080/  |
      | http://127.0.0.1/admin  |
      | http://127.10.0.9/      |
      | http://[::1]:3000/      |

  Scenario Outline: Real external targets are not sandboxes
    # Only localhost/127.0.0.1 or an explicit declaration count today; a private-
    # range IP does not (tightening the registry to IP ranges is future work, §9).
    Given an exploration target "<url>"
    Then the target is not recognized as a sandbox

    Examples:
      | url                    |
      | https://shop.example/  |
      | http://10.0.0.5/       |
      | http://192.0.2.10/     |
      | http://127.evil.com/   |
      | http://localhost.evil.com/ |

  Scenario: A target explicitly declared a sandbox is recognized as one
    Given an exploration target "https://staging.example/" declared as a sandbox
    Then the target is recognized as a sandbox

  Scenario Outline: Actions are classified by whether they are destructive
    # A maintainable, PR-extendable keyword/role list, not a fixed set (§2e).
    Then an action labeled "<label>" is <classification>

    Examples:
      | label            | classification |
      | Delete account   | destructive    |
      | Remove item      | destructive    |
      | Buy Now          | destructive    |
      | Purchase         | destructive    |
      | Pay now          | destructive    |
      | Confirm order    | destructive    |
      | Send message     | destructive    |
      | Log out          | destructive    |
      | View details     | safe           |
      | Next page        | safe           |
      | Open menu        | safe           |
      | Order history    | safe           |

  Scenario Outline: Inside a sandbox, destructive actions are performed
    Given an exploration target "<url>"
    When the interaction gate considers an action labeled "<label>"
    Then the action is allowed

    Examples:
      | url                     | label          |
      | http://localhost:3000/  | Delete account |
      | http://127.0.0.1:3000/  | Buy Now        |

  Scenario Outline: Outside a sandbox, destructive actions are skipped
    Given an exploration target "<url>"
    When the interaction gate considers an action labeled "<label>"
    Then the action is skipped as unsafe outside a sandbox

    Examples:
      | url                    | label          |
      | https://shop.example/  | Delete account |
      | https://shop.example/  | Pay now        |

  Scenario Outline: Non-destructive actions are performed on any target
    Given an exploration target "<url>"
    When the interaction gate considers an action labeled "<label>"
    Then the action is allowed

    Examples:
      | url                     | label        |
      | https://shop.example/   | View details |
      | http://localhost:3000/  | Next page    |

  Scenario: A declared sandbox permits destructive actions
    Given an exploration target "https://staging.example/" declared as a sandbox
    When the interaction gate considers an action labeled "Delete account"
    Then the action is allowed

  Scenario: Nothing relaxes the non-sandbox skip — the §2e non-negotiable
    # Structural pin: the gate's public decision is a pure function of the target
    # and the action alone — there is no bypass/override/force parameter that could
    # ever permit a destructive action on a non-sandbox target.
    Then the interaction gate exposes no option to permit destructive actions outside a sandbox
