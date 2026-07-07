*** Settings ***
Documentation    RFC 7860 interoperability spec: SHA-256 auth crosswalk against net-snmp.
...
...              These scenarios require net-snmp tools (snmpwalk) to be installed.
...              They complement spec_rfc7860.robot by using an independent SHA-2
...              implementation (libnetsnmp) to verify that our key derivation and
...              MAC computation produce wire-correct results — something the emulator
...              tier cannot prove because it shares our auth.py code.
...
...              The emulator accepts auth PDUs from snmpwalk; if snmpwalk can
...              authenticate successfully, our emulator's key derivation is correct.
...              If our walker then produces the same OID sequence as snmpwalk, our
...              walker's key derivation is also correct. Two independent parties on
...              one shared channel, breaking the circularity.
...
...              Run with: just robot-reference
Library          OidtraceLibrary


*** Test Cases ***
RFC 7860 §2.1 - SHA-256 Walk OID Sequence Matches snmpwalk (Interop)
    [Tags]    rfc7860    v3    auth    reference_tools
    [Documentation]    Our walker and snmpwalk independently authenticate against the
    ...                same emulator using SHA-256. The OID sequences they return must
    ...                be identical (our trace is a prefix of snmpwalk's output).
    ...                A mismatch means our HMAC-SHA-256-192 key derivation or MAC
    ...                differs from the libnetsnmp reference implementation.
    ...
    ...                This scenario proves that our emulator correctly enforces 24-byte
    ...                auth_params: snmpwalk sends 24-byte MACs natively; if the emulator
    ...                gates on 12 bytes, snmpwalk produces no output and the assertion fires.
    Start Emulator With Auth User    sha256user    SHA-256    crosspass256
    Walk V3 With Auth    sha256user    SHA-256    crosspass256
    OID Sequence Should Match Snmpwalk V3 Auth    sha256user    SHA-256    crosspass256
    [Teardown]    Stop Emulator

RFC 7860 §2.1 - SHA-256 Walk Against Real SNMP Agent Completes
    [Tags]    rfc7860    v3    auth    reference_tools
    [Documentation]    Our walker authenticates against a real snmpd configured with a
    ...                SHA-256 user. snmpd's libnetsnmp enforces correct 24-byte
    ...                HMAC-SHA-256-192 independently in both directions:
    ...
    ...                - Outgoing walker PDUs must carry 24-byte MACs; snmpd silently
    ...                  drops wrong-length or wrong-value MACs.
    ...                - Walker must parse snmpd's 24-byte response auth_params correctly.
    ...
    ...                A 12-byte truncation bug (copying MD5/SHA-1 logic) causes snmpd to
    ...                drop every data PDU → walk becomes unresponsive instead of completed.
    ...                This is the only scenario that exercises the response-parsing side
    ...                of SHA-256 auth against an independent implementation.
    Start Snmpd With SHA256 User    sha256user    SHA-256    testpass256
    Walk V3 With Auth    sha256user    SHA-256    testpass256
    Trace Should Have End Reason    completed
    [Teardown]    Stop Snmpd
