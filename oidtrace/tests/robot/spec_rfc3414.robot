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
