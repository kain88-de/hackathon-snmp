# OIDSense

OIDSense is a suite of tools to troubleshoot SNMP devices — the slow, the
RFC-violating, and the silently broken.

## The tools

**doctor** — the MVP. One command that automates the support settings ladder
(bulk 10 → 8 → 5 → 1, then timeouts), subtree-scoped and time-budgeted, and answers:
_which settings make this device work?_ Output: a paste-ready Checkmk settings verdict,
a self-contained HTML report, and a trace bundle as the escalation artifact. Progress
streams live while it runs.

**OIDTrace** — the capture layer and CLI underneath everything. Walks a device and
records parsed wire evidence — per-attempt timing, the request-id the device actually
returned, protocol violations — into a portable gzipped-JSONL trace. Traces contain no
values (except a small, admin-approved system-OID allowlist), no packet bytes, and no
device identity; an admin can read one with `zcat` before sharing it. Format spec:
`docs/trace-format.md` (+ JSON Schema).

**OIDViz** — renders a trace or session bundle as a self-contained HTML report:
verdict panel, latency waterfall, subtree heat, run comparison. Opens by double-click,
attaches to a ticket, works offline. Shares its rendering with the doctor's report.

**OIDSense** — the troubleshooting brain: offline trace analysis plus an adaptive
settings finder that evolves from the doctor's deterministic ladder (survey → pinpoint
slow OIDs → derive settings).

**OIDEmu** — a quirk-faithful device emulator (latency curves, bulk-size crashes, fixed
request-ids) for tests, algorithm development, and demos. Internal infrastructure;
fitting profiles from customer traces is deferred until traces actually flow.

## Where things stand

Design specs live in `docs/superpowers/specs/`; the trace format
(`docs/trace-format.md` + `docs/trace-format.schema.json`) is authoritative and
validated by experiments in `experiments/`. Implementation plan for the capture layer:
`docs/superpowers/plans/2026-06-11-oidtrace.md`.
