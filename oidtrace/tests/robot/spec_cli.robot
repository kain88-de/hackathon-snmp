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
    [Documentation]    findings.md #7: --label is spliced unsanitized into the trace
    ...                filename (out_dir / f"{prefix}-{timestamp}..."), and Path treats
    ...                any "/" in that string as a real subdirectory separator. Before
    ...                the fix, a label like "sub/evil" was accepted as-is and the walk
    ...                crashed with an uncaught FileNotFoundError (the implied "sub/"
    ...                directory under --out never exists) instead of a clean CLI error.
    ...                The CLI must reject the label up front, before path construction.
    Start Emulator
    Walk V2c    label=sub/evil
    Last Exit Code Should Be    2
    Stderr Should Contain    label
    No Trace File Should Exist
    [Teardown]    Stop Emulator

Label With Parent Traversal Is Rejected And Does Not Escape Out Dir
    [Tags]    cli    security
    [Documentation]    findings.md #7: before the fix, a label containing ".." (e.g.
    ...                "../escape-marker") was not rejected, and Path silently resolved
    ...                out_dir / "../escape-marker-<ts>.oidtrace.jsonl.gz" to a location
    ...                outside --out entirely — reproduced during development as a real
    ...                file landing directly in /tmp. A label that is a full absolute
    ...                path (e.g. "/etc/cron.d/x") is worse still: Path discards out_dir
    ...                completely and --out is silently ignored. Both cases go through
    ...                the same path-separator check as the sibling scenario above.
    Start Emulator
    Walk V2c    label=../escape-marker
    Last Exit Code Should Be    2
    Stderr Should Contain    label
    No Trace File Should Exist
    No File Matching Should Exist In Out Dir Parent    escape-marker-*.oidtrace.jsonl.gz
    [Teardown]    Stop Emulator

Give-Up-After Of Zero Is Rejected
    [Tags]    cli    validation
    [Documentation]    findings.md #8: walker.py declares UNRESPONSIVE once
    ...                consecutive_no_response >= give_up_after, and that check
    ...                runs after every exchange, success or not. Before the
    ...                fix, --give-up-after 0 was accepted as-is, so the check
    ...                (0 >= 0) fired unconditionally after the very first
    ...                exchange — the walk exited 0 and reported end_reason
    ...                "unresponsive" after exactly one exchange, even against
    ...                a fully healthy, responding device. The CLI must reject
    ...                a --give-up-after below 1 up front.
    Walk V2c    host=127.0.0.1    give_up_after=0
    Last Exit Code Should Be    2
    Stderr Should Contain    give-up-after
    No Trace File Should Exist

Negative Retries Is Rejected
    [Tags]    cli    validation
    [Documentation]    findings.md #8: --retries feeds transport.py's
    ...                total_sends = 1 + retries; before the fix, a negative
    ...                value like -1 was accepted by argparse and passed all
    ...                the way through WalkSettings into traceformat's own
    ...                Settings model, which rejected it deep inside the
    ...                running walk with an uncaught pydantic ValidationError
    ...                (a crash, not a clean CLI exit) — and only after a
    ...                trace file had already been created on disk. The CLI
    ...                must reject a negative --retries up front, before any
    ...                file or network I/O.
    Walk V2c    host=127.0.0.1    retries=-1
    Last Exit Code Should Be    2
    Stderr Should Contain    retries
    No Trace File Should Exist

Zero Bulk Size Is Rejected
    [Tags]    cli    validation
    [Documentation]    findings.md #8: --bulk-size becomes GetBulk's
    ...                max-repetitions. WalkSettings.__post_init__ already
    ...                rejects bulk_size < 1, but only once WalkSettings() is
    ...                constructed inside main() — so before the fix, the CLI
    ...                let argparse accept --bulk-size 0 and then crashed with
    ...                an uncaught ValueError instead of a clean exit 2. The
    ...                CLI must reject this at the argument-validation
    ...                boundary, before WalkSettings is ever constructed.
    Walk V2c    host=127.0.0.1    bulk_size=0
    Last Exit Code Should Be    2
    Stderr Should Contain    bulk-size
    No Trace File Should Exist

V1 Subcommand Rejects The bulk-size Flag
    [Tags]    cli    v1
    [Documentation]    SNMP v1 uses GetNext (one OID per request); `--bulk-size` is a
    ...                GetBulk-only concept and does not exist on the v1 subcommand.
    ...                Supplying it is an argparse error, not a silently ignored flag.
    Walk V1 With Bulk Size Flag
    Last Exit Code Should Be    2
    Stderr Should Contain    unrecognized
    No Trace File Should Exist
