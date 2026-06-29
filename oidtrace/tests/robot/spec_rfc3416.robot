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

RFC 3416 §4.2 - Response With Wrong Request ID Is Recorded As Violation
    [Tags]    rfc3416    violation
    [Documentation]    RFC 3416 §4.2: the response-id in a GetResponse PDU must equal
    ...                the request-id. Mismatches are recorded as request-id-mismatch
    ...                violations; the walk continues (device misbehaviour is data).
    Start Emulator With Fixed Request Id    1
    Walk V2c
    Trace Should Have Violation    request-id-mismatch
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

RFC 3416 - V1 Walk Completes With COMPLETED End Reason Via GetNext
    [Tags]    rfc3416    v1
    [Documentation]    SNMPv1 uses GetNext instead of GetBulk and signals end-of-MIB
    ...                via error_status=noSuchName (2) rather than endOfMibView.
    Start Emulator
    Walk V1
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator
