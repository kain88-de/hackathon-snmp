*** Settings ***
Documentation    System-info capture spec (trace-format.md §4.2): every walk captures
...              each OID in the system-group allowlist (sysDescr, sysObjectID,
...              sysUpTime, sysName) if the device exposes it, at walk start and again
...              at walk end -- unconditional, no flag to disable it. sysName is the
...              device identifier behind the "walk naming"/"oidviz missing device
...              info" customer reports; the other three are covered here for full
...              allowlist parity.
Library          OidtraceLibrary


*** Test Cases ***
System Info Captures SysName When The Device Exposes It
    [Tags]    system-info
    [Documentation]    A device that answers Get for sysName.0 gets that value recorded
    ...                in the system_info record at both walk start and walk end.
    Start Emulator With System Info    sys_name=switch-floor3
    Walk V2c
    Trace System Info At Should Have    start    sysName    switch-floor3
    Trace System Info At Should Have    end    sysName    switch-floor3
    [Teardown]    Stop Emulator

System Info Captures All Allowlisted OIDs When The Device Exposes Them
    [Tags]    system-info
    [Documentation]    A device answering Get for the full allowlist gets every one of
    ...                sysDescr/sysObjectID/sysUpTime/sysName recorded in the same
    ...                system_info record.
    Start Emulator With System Info
    ...    sys_descr=Generic Router
    ...    sys_object_id=1.3.6.1.4.1.9.1.516
    ...    sys_uptime=492711442
    ...    sys_name=switch-floor3
    Walk V2c
    Trace System Info At Should Have    start    sysDescr    Generic Router
    Trace System Info At Should Have    start    sysObjectID    1.3.6.1.4.1.9.1.516
    Trace System Info At Should Have    start    sysUpTime    492711442
    Trace System Info At Should Have    start    sysName    switch-floor3
    [Teardown]    Stop Emulator

System Info Omits SysDescr When The Device Does Not Expose It
    [Tags]    system-info
    [Documentation]    "Only allowlisted OIDs appear" applies per-OID, not
    ...                all-or-nothing: a device missing sysDescr.0 still gets a
    ...                system_info record, just without that key.
    Start Emulator With System Info    sys_object_id=1.3.6.1.4.1.9.1.516    sys_uptime=1000
    Walk V2c
    Trace System Info At Should Have No    start    sysDescr
    [Teardown]    Stop Emulator

System Info Omits SysObjectID When The Device Does Not Expose It
    [Tags]    system-info
    Start Emulator With System Info    sys_descr=Generic Router    sys_uptime=1000
    Walk V2c
    Trace System Info At Should Have No    start    sysObjectID
    [Teardown]    Stop Emulator

System Info Omits SysUpTime When The Device Does Not Expose It
    [Tags]    system-info
    Start Emulator With System Info    sys_descr=Generic Router    sys_object_id=1.3.6.1.4.1.9.1.516
    Walk V2c
    Trace System Info At Should Have No    start    sysUpTime
    [Teardown]    Stop Emulator

System Info Omits SysName When The Device Does Not Expose It
    [Tags]    system-info
    [Documentation]    A device that has no sysName.0 (Get for it returns NoSuchObject)
    ...                produces a system_info record that simply omits sysName, rather
    ...                than fabricating a value.
    Start Emulator With System Info    sys_descr=Generic Router
    Walk V2c
    Trace System Info At Should Have No    start    sysName
    [Teardown]    Stop Emulator

System Info Captures SysName Over SNMPv3
    [Tags]    system-info    v3
    [Documentation]    The system-info Get is version-agnostic: v3 (one Get, four
    ...                varbinds, same as v2c) captures sysName at both walk start
    ...                and walk end, same as v2c.
    Start Emulator With System Info    sys_name=switch-floor3
    Walk V3 As User    probe
    Trace System Info At Should Have    start    sysName    switch-floor3
    Trace System Info At Should Have    end    sysName    switch-floor3
    [Teardown]    Stop Emulator

System Info Omits SysName Over SNMPv1 Without Affecting Other OIDs
    [Tags]    system-info    v1
    [Documentation]    SNMPv1 has no per-varbind exceptions (RFC 1157): the walker
    ...                sends one Get per allowlisted OID instead of one Get for all
    ...                four, so a device missing only sysName still gets the other
    ...                three captured -- per-OID omission holds on v1 too, not just
    ...                v2c/v3.
    Start Emulator With System Info    sys_descr=Generic Router
    Walk V1
    Trace System Info At Should Have    start    sysDescr    Generic Router
    Trace System Info At Should Have No    start    sysName
    [Teardown]    Stop Emulator
