# Doctor MVP Design (early draft)

Date: 2026-06-11
Status: **draft — captures the MVP rethink; not yet fully brainstormed**

The **doctor** is the suite's MVP: one command that automates the support mental script
for SNMP timeout tickets — _"drop bulk size to 8, then 5, then 1; raise the timeout;
reduce retries"_ — and turns it into a verdict plus a self-contained HTML report.

## Why this is the MVP

- The ladder solves the large majority of real tickets (the 80/20 of SNMP
  troubleshooting); it is deterministic and explainable — the same script support
  recites, automated.
- The admin's payoff is immediate and local: a terminal verdict with **paste-ready
  Checkmk settings** and an HTML report. No upload-and-wait.
- Full evidence capture (OIDTrace) sits underneath it; visualization (OIDViz) renders
  what it produces.

## Architecture: the ladder drives the OIDTrace pipeline

The doctor is a **driver of the OIDTrace stack** (codec/transport/walker) from day one —
no net-snmp orchestration stage. Two reasons:

1. **Evidence quality**: per-request timing, returned request-ids, ICMP-vs-silence — the
   verdict can say _why_, not just _which rung worked_.
2. **Streaming architecture**: the trace format's streaming guarantee (one
   self-contained record per line) means the record stream is also a **live event
   stream**. The walker emits each record to pluggable sinks: the gzip trace file
   (canonical), terminal progress (stderr), and later an SSE endpoint for an
   interactive web UI that shows the walk live — same records, three consumers, no
   second data path. (The previous project's SSE diagnose streaming validated this UX.)

Per ladder rung: subtree-scoped, time-budgeted walk via `run_walk` with that rung's
settings; all rungs share one session id, one trace file per rung (the escalation
bundle when no rung works). net-snmp remains a **test-time reference tool only**
(cross-walk validation), not a runtime dependency.

Output: terminal verdict ("works at bulk 5, timeout 3 s — set these Checkmk knobs"),
a self-contained HTML report (rung table, slow regions, violations, recommendation),
and the trace bundle.

## Testing

Ladder logic is pure (rung results in → verdict out): unit-testable. End-to-end:
doctor vs the quirk emulator with each pathology, asserting the verdict and the trace
bundle. Inherits the OIDTrace plan's test pyramid; the net-snmp cross-walk stays the
independent reference check.

## Open questions (for the real brainstorming session)

- Exact ladder definition and stopping rules (first-working-rung vs full fingerprint).
- Verdict wording and the exact Checkmk ruleset fields it should name.
- HTML report rendering stack (shared with OIDViz; must stay single-file).
- Whether the verdict document is derived purely from the trace bundle's
  header/summary records or needs its own tiny schema.
