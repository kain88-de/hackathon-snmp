# OIDSense

OIDSense is a suite of programs to trouble shoot snmp devices.

OIDTrace: capture a queries in a highly detailed trace
OIDViz: render a trace as a self-contained HTML report — waterfall, violations, verdict
OIDEmu: profile-driven device emulator — hand-written quirk profiles now, trace-fitted later
OIDSense: Troubleshoot the device — trace analysis plus an adaptive settings finder

MVP: OIDTrace + OIDViz — capture the evidence, see the problem. OIDSense and OIDEmu
build on top.

## OIDTrace

OIDTrace can do an snmp walk with different settings.
The results are portable json, so we can show to admins what we collect.
We do not record values, not interesting for trouble shooting — except a small
system-OID allowlist (sysDescr, sysObjectID, sysUpTime) that is shown to the admin
at capture time for approval, used to identify the device and to prove mid-walk reboots.

