*** Settings ***
Documentation    System-info capture spec (trace-format.md §4.2): a walk captures each
...              OID in the system-group allowlist (sysDescr, sysObjectID, sysUpTime,
...              sysName) if the device exposes it, at walk start and again at walk
...              end. sysName is the device identifier behind the "walk naming"/
...              "oidviz missing device info" customer reports; the other three are
...              covered here for full allowlist parity.
...
...              Not implemented yet: the walker never emits `system_info` records
...              (oidtrace/README.md, "Not implemented"). Every scenario below is
...              expected to fail until that capture is built; tagged `not-implemented`
...              so they can be excluded from `just ci` until then.
Library          OidtraceLibrary


*** Test Cases ***
System Info Captures SysName When The Device Exposes It
    [Tags]    system-info    not-implemented
    [Documentation]    A device that answers Get for sysName.0 gets that value recorded
    ...                in the system_info record at both walk start and walk end.
    Start Emulator With System Info    sys_name=switch-floor3
    Walk V2c
    Trace System Info At Should Have    start    sysName    switch-floor3
    Trace System Info At Should Have    end    sysName    switch-floor3
    [Teardown]    Stop Emulator

System Info Captures All Allowlisted OIDs When The Device Exposes Them
    [Tags]    system-info    not-implemented
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
    [Tags]    system-info    not-implemented
    [Documentation]    "Only allowlisted OIDs appear" applies per-OID, not
    ...                all-or-nothing: a device missing sysDescr.0 still gets a
    ...                system_info record, just without that key.
    Start Emulator With System Info    sys_object_id=1.3.6.1.4.1.9.1.516    sys_uptime=1000
    Walk V2c
    Trace System Info At Should Have No    start    sysDescr
    [Teardown]    Stop Emulator

System Info Omits SysObjectID When The Device Does Not Expose It
    [Tags]    system-info    not-implemented
    Start Emulator With System Info    sys_descr=Generic Router    sys_uptime=1000
    Walk V2c
    Trace System Info At Should Have No    start    sysObjectID
    [Teardown]    Stop Emulator

System Info Omits SysUpTime When The Device Does Not Expose It
    [Tags]    system-info    not-implemented
    Start Emulator With System Info    sys_descr=Generic Router    sys_object_id=1.3.6.1.4.1.9.1.516
    Walk V2c
    Trace System Info At Should Have No    start    sysUpTime
    [Teardown]    Stop Emulator

System Info Omits SysName When The Device Does Not Expose It
    [Tags]    system-info    not-implemented
    [Documentation]    A device that has no sysName.0 (Get for it returns NoSuchObject)
    ...                produces a system_info record that simply omits sysName, rather
    ...                than fabricating a value.
    Start Emulator With System Info    sys_descr=Generic Router
    Walk V2c
    Trace System Info At Should Have No    start    sysName
    [Teardown]    Stop Emulator
