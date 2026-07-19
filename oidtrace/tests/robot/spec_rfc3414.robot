*** Settings ***
Documentation    RFC 3414 compliance spec: SNMPv3 USM engine discovery and walk.
...
...              RFC 3414 §4 defines the discovery mechanism: a client that does not know
...              the authoritative engine's parameters sends an empty GetRequest; the
...              engine replies with a Report PDU carrying its engineID, engineBoots, and
...              engineTime. The client uses these parameters for all subsequent messages.
Library          OidtraceLibrary


*** Test Cases ***
RFC 3414 §4 - V3 Walk Begins With A Discovery Exchange Recorded As PDU Type discovery
    [Tags]    rfc3414    v3
    [Documentation]    The discovery probe is recorded as seq=1 with pdu=discovery and
    ...                empty oids — distinguishing it from data exchanges in the trace.
    Start Emulator
    Walk V3 As User    noAuthUser
    Trace First Exchange Should Be Discovery
    [Teardown]    Stop Emulator

RFC 3414 §4 - V3 Walk After Successful Discovery Completes Normally
    [Tags]    rfc3414    v3
    [Documentation]    Once engine parameters are obtained, the walker issues GetBulk
    ...                requests and the walk terminates as completed.
    Start Emulator
    Walk V3 As User    noAuthUser
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator

RFC 3414 §4 - V3 Discovery Failure Terminates Walk As UNRESPONSIVE
    [Tags]    rfc3414    v3
    [Documentation]    If the agent drops the discovery probe, the walker cannot obtain
    ...                engine parameters and terminates the walk as unresponsive rather
    ...                than proceeding without authentication context.
    Start Emulator With Drop All
    Walk V3 As User    noAuthUser    give_up_after=2
    Trace Should Have End Reason    unresponsive
    [Teardown]    Stop Emulator

RFC 3414 §4 - Malformed Discovery Reply Terminates Walk As UNRESPONSIVE, With A Violation
    [Tags]    rfc3414    v3
    [Documentation]    A discovery reply that fails to BER-decode carries no usable
    ...                engine parameters, so the walker cannot proceed — but unlike a
    ...                dropped/no-response discovery, the garbled datagram did arrive.
    ...                It must be surfaced as a malformed-ber violation on the trace,
    ...                not silently treated as if nothing had been received.
    Start Emulator With Corrupted Discovery Reply
    Walk V3 As User    noAuthUser    give_up_after=2
    Trace Should Have End Reason    unresponsive
    Trace Should Have Violation    malformed-ber
    [Teardown]    Stop Emulator

RFC 3414 §4 - V3 Discovery Report PDU Is Not Flagged As A Violation
    [Tags]    rfc3414    v3
    [Documentation]    The discovery response is a Report PDU (0xA8), a different PDU
    ...                type than the Response PDU (0xA2) every other exchange returns.
    ...                oidtrace does not validate the response PDU tag, so this expected
    ...                type difference is never recorded as a violation on the exchange.
    Start Emulator
    Walk V3 As User    noAuthUser
    Trace First Exchange Should Be Discovery
    Trace First Exchange Should Have No Violations
    [Teardown]    Stop Emulator

RFC 3414 §4 - V3 Walk Requires A Username
    [Tags]    rfc3414    v3
    [Documentation]    USM has no anonymous identity — every message carries a
    ...                msgUserName — so `--user` is mandatory on the v3 subcommand.
    ...                A missing value is an argparse error (exit 2, no trace file, no
    ...                network I/O), not a defaulted or silently accepted omission.
    Walk V3 With No User
    Last Exit Code Should Be    2
    Stderr Should Contain    --user
    No Trace File Should Exist

RFC 3414 §11.2 - Auth Passphrase Shorter Than 8 Characters Still Walks, With A Warning
    [Tags]    rfc3414    v3    validation
    [Documentation]    RFC 3414 §11.2 recommends a minimum passphrase length of 8
    ...                characters to resist dictionary attacks against the derived key,
    ...                but this is not a wire requirement — a real device may be
    ...                configured with a shorter one. A shorter --auth-pass prints a
    ...                warning naming the flag but still completes the walk.
    Start Emulator With Auth User    someuser    MD5    short1
    Walk V3 With Auth    someuser    MD5    short1
    Trace Should Have End Reason    completed
    Stderr Should Contain    auth-pass
    [Teardown]    Stop Emulator
