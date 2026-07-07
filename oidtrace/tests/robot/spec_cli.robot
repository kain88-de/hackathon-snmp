*** Settings ***
Documentation    CLI surface spec: exit codes, output files, verbosity, filenames.
...              These scenarios document the observable contract of the oidtrace CLI
...              independent of SNMP protocol details.
Library          OidtraceLibrary


*** Test Cases ***
Successful Walk Exits 0 And Writes One Trace File
    [Tags]    cli
    Start Emulator
    Walk V2c
    Last Exit Code Should Be    0
    Trace File Should Exist
    [Teardown]    Stop Emulator

Unresolvable Host Exits 2 And Writes No Trace File
    [Tags]    cli
    Walk V2c    host=host.invalid
    Last Exit Code Should Be    2
    Stderr Should Contain       resolve
    No Trace File Should Exist

Bad Start OID Exits 2 And Writes No Trace File
    [Tags]    cli
    Walk V2c    host=127.0.0.1    start_oid=1.3.x
    Last Exit Code Should Be    2
    Stderr Should Contain       start-oid
    No Trace File Should Exist

Label Flag Is Recorded In Trace Header
    [Tags]    cli
    Start Emulator
    Walk V2c    label=myrun
    Trace Header Label Should Be    myrun
    [Teardown]    Stop Emulator

Trace Filename Uses Label As Prefix When Label Is Given
    [Tags]    cli
    Start Emulator
    Walk V2c    label=testlabel
    Trace Filename Should Start With    testlabel-
    [Teardown]    Stop Emulator

Trace Filename Uses Walk As Prefix When No Label Is Given
    [Tags]    cli
    Start Emulator
    Walk V2c
    Trace Filename Should Start With    walk-
    [Teardown]    Stop Emulator

Terminal Summary Contains End Reason And Exchange Count
    [Tags]    cli
    Start Emulator
    Walk V2c
    Stdout Should Contain    end_reason
    Stdout Should Contain    exchanges
    [Teardown]    Stop Emulator

Community String Never Appears In The Trace File
    [Tags]    cli    privacy
    [Documentation]    Privacy contract: the community string is a credential and must
    ...                never be written to the trace. A walk with a distinctive community
    ...                produces a trace whose decompressed bytes do not contain it.
    Start Emulator
    Walk V2c    community=topsecretcommunity
    Trace File Should Exist
    Trace Bytes Should Not Contain    topsecretcommunity
    [Teardown]    Stop Emulator

Walk With No Version Prints Usage And Exits 2
    [Tags]    cli
    [Documentation]    `oidtrace walk` with no v1/v2c/v3 sub-subcommand prints usage to
    ...                stderr and exits 2 — no network I/O, no trace file.
    Run Oidtrace Walk With No Version
    Last Exit Code Should Be    2
    Stderr Should Contain    usage

V1 Subcommand Rejects The bulk-size Flag
    [Tags]    cli    v1
    [Documentation]    SNMP v1 uses GetNext (one OID per request); `--bulk-size` is a
    ...                GetBulk-only concept and does not exist on the v1 subcommand.
    ...                Supplying it is an argparse error, not a silently ignored flag.
    Walk V1 With Bulk Size Flag
    Last Exit Code Should Be    2
    Stderr Should Contain    unrecognized
    No Trace File Should Exist
