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
- Full evidence capture (OIDTrace) and visualization (OIDViz) slot in underneath and
  behind it, staged.

## Stage 1 (the real MVP): ladder over net-snmp

- Driver: subprocess `snmpbulkwalk` / `snmpgetnext` with varied `-Cr` (bulk), `-t`
  (timeout), `-r` (retries); subtree-scoped (`--start-oid`, multiple allowed) and
  time-budgeted per rung (~15 s; subprocess timeout enforces it).
- Measurement: wall clock per rung; completed-vs-timed-out; OID count from stdout.
  Streaming stdout with per-line timestamps gives rough slow-region attribution for
  free (inter-line gaps).
- Output: terminal verdict ("works at bulk 5, timeout 3 s — set these Checkmk knobs"),
  a self-contained HTML report (rung table, slow regions, recommendation), and a small
  JSON result document per session.
- Hard runtime dependency on net-snmp — acceptable: it is preinstalled on monitoring
  servers, and the doctor runs there.
- What stage 1 cannot see: per-request timing, returned request-ids, stray/duplicate
  responses, ICMP-vs-silence distinction. Acceptable for the ladder verdict.

## Stage 2: swap the driver for the OIDTrace stack

Same ladder, same report — the net-snmp subprocess is replaced by the
codec/transport/walker pipeline (already planned and PoC-proven). Gains: per-request
timing, violation evidence ("your device answers with request-id 1 — that is why your
library fails"), ICMP-vs-silence, and **lite traces (format v1) as the escalation
artifact**: when the ladder finds no working settings, the admin already holds the
session bundle for support.

## Testing

Stage 1 is tested against the quirk emulator (net-snmp talks to it — proven by the
reference-tools cross-walk pattern); these tests require `snmpbulkwalk` on PATH, which
is a hard dependency of stage 1 anyway. Stage 2 inherits the OIDTrace plan's test
pyramid.

## Open questions (for the real brainstorming session)

- Exact ladder definition and stopping rules (first-working-rung vs full fingerprint).
- Verdict wording and the exact Checkmk ruleset fields it should name.
- HTML report rendering stack (shared with OIDViz; must stay single-file).
- Whether stage 1's JSON result document should be a profile of the trace format's
  header/summary records or its own tiny schema.
