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
values, no packet bytes, and no device identity; an admin can read one with `zcat`
before sharing it. Format spec:
`docs/trace-format.md` (+ JSON Schema).

**OIDViz** — renders a trace or session bundle as a self-contained HTML report:
verdict panel, latency waterfall, subtree heat, run comparison. Opens by double-click,
attaches to a ticket, works offline. Shares its rendering with the doctor's report.

Under the hood, a **quirk emulator** (fixed request-ids, bulk-size crashes, slow
subtrees, end-of-MIB silence) lives in the test suite — every pathology the tools must
handle is reproducible over loopback UDP. An **adaptive settings finder** (survey →
pinpoint slow OIDs → derive settings) is the doctor's planned successor; its design
sketches live in git history.

## Where things stand

**The capture layer is implemented**: workspace packages `oidtrace/` (codec, transport,
walker, CLI) and `traceformat/` (schema-generated pydantic models + vocabulary), 159
tests including a net-snmp cross-walk, 98–100% branch coverage, dead-code and codegen
freshness gates in CI. Design specs live in `docs/superpowers/specs/`; the trace format
(`docs/trace-format.md` + `docs/trace-format.schema.json`) is authoritative and
validated by experiments in `experiments/`. The executed plan:
`docs/superpowers/plans/2026-06-11-oidtrace.md`. Next: the doctor, then OIDViz.
