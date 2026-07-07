*** Settings ***
Documentation    Crash-safety and walk-lifecycle spec: a partial trace (time budget,
...              Ctrl-C) is still a valid, readable file, and Ctrl-C is a first-class
...              exit rather than a stack trace.
...
...              These scenarios cover the architecture doc's "Error handling" contract:
...              only local/operator errors, total silence, and runaway walks change the
...              outcome; every other stop still flushes a valid trace ending in a
...              summary record.
Library          OidtraceLibrary


*** Test Cases ***
Time Budget Exceeded Terminates Walk With TIME_BUDGET_EXCEEDED End Reason
    [Tags]    crash-safety    lifecycle
    [Documentation]    A runaway walk against a slow device is capped by the wall-time
    ...                budget: the walk stops with end_reason=time-budget-exceeded and
    ...                the trace is still a valid, readable file.
    Start Emulator With Slow Oids    0.05
    Walk V2c    time_budget=0.1
    Trace Should Have End Reason    time-budget-exceeded
    Trace File Should Exist
    [Teardown]    Stop Emulator

Ctrl-C Is A First-Class Exit: Flushes An Interrupted Summary And Exits 0
    [Tags]    crash-safety    lifecycle
    [Documentation]    SIGINT mid-walk flushes the current record, writes a summary with
    ...                end_reason=interrupted, prints the terminal verdict, and exits 0.
    ...                The partial trace is a valid, useful file.
    Start Emulator With Slow Oids    0.1
    Walk V2c And Interrupt After    0.3
    Last Exit Code Should Be    0
    Trace File Should Exist
    Trace Should Have End Reason    interrupted
    [Teardown]    Stop Emulator
