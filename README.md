# OIDSense

OIDSense is a suite of programs to trouble shoot snmp devices.

OIDTrace: capture a queries in a highly detailed trace
OIDViz: render a trace as a self-contained HTML report — waterfall, violations, verdict
OIDEmu: device emulator for tests, OIDSense development and demos (internal infrastructure;
trace-fitted profiles deferred until traces actually flow)
OIDSense: Troubleshoot the device — trace analysis plus an adaptive settings finder

MVP: the **doctor** — one command that runs the support settings ladder automatically
(bulk 10 → 8 → 5 → 1, then timeouts), subtree-scoped and time-budgeted, driving the
OIDTrace pipeline: per-request timing, request-id evidence, traces as the escalation
artifact. It produces a paste-ready settings verdict plus a self-contained HTML report.
The record stream is live — the same trace records feed the file, terminal progress,
and (later) an SSE web UI showing the walk as it happens. Captures are behavioral
fingerprints in under a minute, never exhaustive walks. Long term, capture belongs
inside Checkmk; the trace format is the durable artifact, the CLI the bootstrap.

## OIDTrace

OIDTrace can do an snmp walk with different settings.
The results are portable json, so we can show to admins what we collect.
We do not record values, not interesting for trouble shooting — except a small
system-OID allowlist (sysDescr, sysObjectID, sysUpTime) that is shown to the admin
at capture time for approval, used to identify the device and to prove mid-walk reboots.
