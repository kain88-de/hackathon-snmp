*** Settings ***
Documentation    RFC 3416 compliance spec: SNMP operations, termination conditions,
...              and protocol violation detection.
...
...              RFC 3416 §4.2 specifies GetBulk response semantics: response PDUs must
...              echo the request-id unchanged, varbind OIDs must be monotonically
...              increasing, and the end-of-MIB view is signalled via endOfMibView (0x82).
Library          OidtraceLibrary


*** Test Cases ***
RFC 3416 - Normal GetBulk Walk Completes With COMPLETED End Reason
    [Tags]    rfc3416
    [Documentation]    A well-behaved agent that returns endOfMibView terminates the walk cleanly.
    Start Emulator
    Walk V2c
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator

RFC 3416 §4.2 - Response With Wrong Request ID Is Recorded As Violation And Walk Continues
    [Tags]    rfc3416    violation
    [Documentation]    RFC 3416 §4.2: the response-id in a GetResponse PDU must equal
    ...                the request-id. The transport never uses request-ids to match
    ...                responses, so a mismatch is recorded as a request-id-mismatch
    ...                violation and the walk still runs to a normal completion
    ...                (device misbehaviour is data, not an error).
    Start Emulator With Fixed Request Id    1
    Walk V2c
    Trace Should Have Violation    request-id-mismatch
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator

RFC 3416 §4.2 - Duplicate Response Is Recorded As A Violation Not Dropped
    [Tags]    rfc3416    violation
    [Documentation]    The transport records every datagram that arrives, including a
    ...                duplicate of the response drained as a stray. The extra copy is
    ...                recorded as a duplicate-response violation; the walk is unaffected
    ...                and completes normally.
    Start Emulator With Duplicate Responses
    Walk V2c
    Trace Should Have Violation    duplicate-response
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator

RFC 3416 - Subtree-Scoped Walk Completes By Leaving The Subtree
    [Tags]    rfc3416
    [Documentation]    A walk bounded to a --start-oid subtree terminates COMPLETED as
    ...                soon as the cursor advances past the subtree — without ever seeing
    ...                EndOfMibView. This is the capture-scope guidance path: bound the
    ...                walk to the subtree monitoring actually polls.
    Start Emulator
    Walk V2c    start_oid=1.3.6.1.2.1.2.2.1.1
    Trace Should Have End Reason    completed
    Trace Should Not Contain End Of Mib
    [Teardown]    Stop Emulator

RFC 3416 §4.2 - Non-Increasing OIDs Terminate Walk With OID_LOOP End Reason
    [Tags]    rfc3416    violation
    [Documentation]    RFC 3416 §4.2: each successive varbind OID must be greater than
    ...                the previous. When the agent wraps around to an earlier OID the
    ...                walker records oid-not-increasing and terminates with oid-loop.
    Start Emulator With End Of Mib Wrap
    Walk V2c
    Trace Should Have End Reason    oid-loop
    [Teardown]    Stop Emulator

RFC 3416 - Silent Agent Terminates Walk With UNRESPONSIVE End Reason
    [Tags]    rfc3416
    [Documentation]    When the agent returns no responses for give_up_after consecutive
    ...                exchanges, the walk terminates with unresponsive. The trace is
    ...                still a valid, readable file.
    Start Emulator With Drop All
    Walk V2c    give_up_after=2
    Trace Should Have End Reason    unresponsive
    Trace File Should Exist
    [Teardown]    Stop Emulator

RFC 3416 §4.2 - Late Reply To A Timed-Out Exchange Must Not Corrupt A Later One
    [Tags]    rfc3416    violation
    [Documentation]    A response that arrives after its own exchange already gave up is
    ...                a stray, not data for whatever exchange happens to be waiting when
    ...                it lands. The walker tracks its own past request-ids and rejects a
    ...                datagram echoing one of them as this exchange's answer, filing it as
    ...                a stray instead — so a late reply to exchange 1 no longer misattributes
    ...                its (already-passed) OIDs and falsely trips oid-not-increasing/oid-loop
    ...                on an otherwise healthy, merely-slow agent.
    Start Emulator With Delayed First Response    0.6
    Walk V2c    timeout=0.2    bulk_size=1
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator

RFC 3416 - V1 Walk Completes With COMPLETED End Reason Via GetNext
    [Tags]    rfc3416    v1
    [Documentation]    SNMPv1 uses GetNext instead of GetBulk and signals end-of-MIB
    ...                via error_status=noSuchName (2) rather than endOfMibView.
    Start Emulator
    Walk V1
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator
