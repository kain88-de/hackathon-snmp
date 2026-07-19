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

Label With Path Separator Is Rejected
    [Tags]    cli    security
    [Documentation]    --label becomes part of the trace filename, so it must
    ...                not contain a path separator: a label like "sub/evil"
    ...                would be treated as a subdirectory of --out that does
    ...                not exist, rather than as a plain filename component.
    Start Emulator
    Walk V2c    label=sub/evil
    Last Exit Code Should Be    2
    Stderr Should Contain    label
    No Trace File Should Exist
    [Teardown]    Stop Emulator

Label With Parent Traversal Is Rejected And Does Not Escape Out Dir
    [Tags]    cli    security
    [Documentation]    --label must not contain ".." or be an absolute path
    ...                either: either could place the trace file somewhere
    ...                other than --out, or ignore --out entirely. A walk must
    ...                never write its trace file outside the requested output
    ...                directory.
    Start Emulator
    Walk V2c    label=../escape-marker
    Last Exit Code Should Be    2
    Stderr Should Contain    label
    No Trace File Should Exist
    No File Matching Should Exist In Out Dir Parent    escape-marker-*.oidtrace.jsonl.gz
    [Teardown]    Stop Emulator

Give-Up-After Of Zero Is Rejected
    [Tags]    cli    validation
    [Documentation]    --give-up-after sets how many consecutive non-responses
    ...                the walker tolerates before concluding a target is
    ...                unresponsive. It must be at least 1: a walk must miss at
    ...                least one response before it can end with an
    ...                unresponsive verdict, so even a fully healthy, responding
    ...                device is never reported unresponsive.
    Walk V2c    host=127.0.0.1    give_up_after=0
    Last Exit Code Should Be    2
    Stderr Should Contain    give-up-after
    No Trace File Should Exist

Negative Retries Is Rejected
    [Tags]    cli    validation
    [Documentation]    --retries sets how many retransmissions the walker
    ...                sends after the first request of an exchange. A
    ...                negative count has no meaningful interpretation — it
    ...                cannot mean "fewer than zero retransmissions" — so it is
    ...                rejected up front, before any request is sent or trace
    ...                file written.
    Walk V2c    host=127.0.0.1    retries=-1
    Last Exit Code Should Be    2
    Stderr Should Contain    retries
    No Trace File Should Exist

Zero Bulk Size Is Rejected
    [Tags]    cli    validation
    [Documentation]    --bulk-size sets GetBulk's max-repetitions: how many
    ...                varbinds each v2c exchange requests. It must be at
    ...                least 1, since a GetBulk requesting zero repetitions
    ...                per exchange could never advance the walk.
    Walk V2c    host=127.0.0.1    bulk_size=0
    Last Exit Code Should Be    2
    Stderr Should Contain    bulk-size
    No Trace File Should Exist

V1 Subcommand Rejects The bulk-size Flag
    [Tags]    cli    v1
    [Documentation]    SNMP v1 uses GetNext (one OID per request); `--bulk-size` is a
    ...                GetBulk-only concept and does not exist on the v1 subcommand.
    ...                Supplying it is a command-line error (exit 2), not a silently
    ...                ignored flag.
    Walk V1 With Bulk Size Flag
    Last Exit Code Should Be    2
    Stderr Should Contain    no such option
    No Trace File Should Exist
