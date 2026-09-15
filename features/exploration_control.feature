# Exploration run-level controls: budget + kill switch — ROADMAP.md §2e.
#
# The fourth slice of exploration mode (§2e), still pure logic. Per §2e, run-level
# controls are core safety, not optional hardening: every exploration run carries a
# hard, user-set budget (max states discovered, max requests, max wall-clock time)
# that auto-stops the run the moment any bound is reached, plus a manual kill switch
# to stop a running exploration on command. A run that can't be bounded or stopped is
# itself a reliability/safety gap (§1), so these ship *with* the safety system.
#
# This slice only decides "keep going or stop, and why"; the explorer loop (slice 5)
# is what records progress and honours the decision. Wall-clock time is read through
# an injectable clock, so the time bound is exercised deterministically in-process.

Feature: An exploration run is always bounded and stoppable
  As the operator of an exploration run
  I want a hard budget and a manual kill switch
  So that a run can never wander unbounded and I can always stop it on command

  Scenario: A run within all its bounds keeps running
    Given a run budget of max_states 5, max_requests 10, max_seconds 60
    When 2 states are discovered
    And 3 requests are made
    And 30 seconds of wall-clock time pass
    Then the run is still running

  Scenario: The state budget stops the run when the state count reaches it
    Given a run budget of max_states 3
    When 2 states are discovered
    Then the run is still running
    When 1 state is discovered
    Then the run stops with a reason mentioning "max_states"

  Scenario: The request budget stops the run when the request count reaches it
    Given a run budget of max_requests 4
    When 3 requests are made
    Then the run is still running
    When 1 request is made
    Then the run stops with a reason mentioning "max_requests"

  Scenario: The wall-clock budget stops the run when the time limit passes
    Given a run budget of max_seconds 30
    When 29 seconds of wall-clock time pass
    Then the run is still running
    When 1 second of wall-clock time passes
    Then the run stops with a reason mentioning "max_seconds"

  # Pins the §2e non-negotiable: the manual kill switch always stops a run on
  # command, even one nowhere near any budget bound.
  Scenario: The kill switch stops even an unbounded run that is within budget
    Given a run budget with no limits
    When 100 states are discovered
    And 100 requests are made
    Then the run is still running
    When the kill switch is thrown
    Then the run stops with a reason mentioning "kill switch"

  # The kill switch is checked before the budget, so a stop-on-command is reported
  # as the kill switch even when a budget bound is also reached.
  Scenario: The kill switch takes precedence over a reached budget bound
    Given a run budget of max_states 1
    When 1 state is discovered
    And the kill switch is thrown
    Then the run stops with a reason mentioning "kill switch"

  Scenario: A budget bound must be positive
    Then building a run budget of max_states 0 is rejected
    And building a run budget of max_requests -1 is rejected
    And building a run budget of max_depth 0 is rejected
