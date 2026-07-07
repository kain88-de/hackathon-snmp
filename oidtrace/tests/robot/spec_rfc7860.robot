*** Settings ***
Documentation    RFC 7860 compliance spec: HMAC-SHA-2 authentication for SNMPv3 USM.
...
...              RFC 7860 §2.1 defines HMAC-SHA-256-192: HMAC-SHA-256 with the MAC
...              truncated to 192 bits (24 bytes). The password-to-key algorithm is
...              identical to RFC 3414 Appendix A.2 but uses SHA-256 instead of SHA-1.
...
...              These scenarios validate that oidtrace correctly derives keys, sends
...              authenticated messages, and correctly signs outgoing requests for
...              SHA-256 auth users. oidtrace does not verify inbound response
...              authenticity — see the known-limitation scenario below.
Library          OidtraceLibrary


*** Test Cases ***
RFC 7860 §2.1 - SHA-256 Authenticated Walk Completes Successfully
    [Tags]    rfc7860    v3    auth
    [Documentation]    A SHA-256 auth user can complete a full walk against an emulator
    ...                that expects HMAC-SHA-256-192 authentication on every PDU.
    ...                The walk terminates with end_reason=completed.
    Start Emulator With Auth User    sha256user    SHA-256    testpass256
    Walk V3 With Auth    sha256user    SHA-256    testpass256
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator

RFC 7860 §2.1 - Auth Proto Without Password Is A CLI Validation Error
    [Tags]    rfc7860    cli
    [Documentation]    Specifying --auth-proto SHA-256 without --auth-pass is a usage
    ...                error: the CLI exits 2 and the error message names the missing flag.
    Walk V3 With Auth Proto Only    sha256user    SHA-256
    Last Exit Code Should Be    2
    Stderr Should Contain    auth-pass

RFC 7860 §2.1 - SHA-256 Auth Proto Is Case Insensitive
    [Tags]    rfc7860    v3    auth
    [Documentation]    The --auth-proto flag accepts sha-256 and SHA-256 interchangeably.
    ...                The walker normalises the input to uppercase before validation.
    Start Emulator With Auth User    sha256user    SHA-256    testpass256
    Walk V3 With Auth    sha256user    sha-256    testpass256
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator

RFC 7860 §2.1 - Wrong Password Causes HMAC Mismatch And Walk Becomes UNRESPONSIVE
    [Tags]    rfc7860    v3    auth
    [Documentation]    RFC 7860 §2.1: the agent verifies the HMAC on every incoming PDU.
    ...                When the walker derives a key from the wrong password the MAC is
    ...                invalid; the agent silently drops the request. After give_up_after
    ...                consecutive dropped exchanges the walker terminates as unresponsive.
    ...                This confirms that authentication is enforced end-to-end, not just
    ...                syntactically validated by the CLI.
    Start Emulator With Auth User    sha256user    SHA-256    correctpass
    Walk V3 With Auth    sha256user    SHA-256    wrongpass    give_up_after=2
    Trace Should Have End Reason    unresponsive
    [Teardown]    Stop Emulator

RFC 7860 §2.1 - SHA-256 Walk Begins With A Discovery Exchange
    [Tags]    rfc7860    v3    auth
    [Documentation]    SNMPv3 key localisation requires the authoritative engine ID
    ...                (RFC 3414 §4). Even with SHA-256 auth the first exchange is an
    ...                unauthenticated discovery probe, recorded with pdu=discovery.
    Start Emulator With Auth User    sha256user    SHA-256    testpass256
    Walk V3 With Auth    sha256user    SHA-256    testpass256
    Trace First Exchange Should Be Discovery
    [Teardown]    Stop Emulator

RFC 7860 §2.1 - Tampered Response Authenticity Is Not Verified (Known Limitation)
    [Tags]    rfc7860    v3    auth    known-limitation
    [Documentation]    oidtrace authenticates its own outgoing requests but deliberately
    ...                does not verify inbound response authenticity (walker.py:
    ...                "diagnostic tracer, not a security client"). This documents that
    ...                a response signed with the wrong key is still accepted and the
    ...                walk completes normally. Intentional current behavior, not a
    ...                defect this spec expects fixed.
    Start Emulator With Auth User And Corrupted Responses    sha256user    SHA-256    testpass256
    Walk V3 With Auth    sha256user    SHA-256    testpass256
    Trace Should Have End Reason    completed
    [Teardown]    Stop Emulator
