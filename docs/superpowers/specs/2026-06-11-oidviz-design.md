# OIDViz Design (early draft)

Date: 2026-06-11
Status: **draft — captures the idea and scope; not yet fully brainstormed**

OIDViz renders a trace (or a session bundle) for humans. Premise: for many support
cases the trace alone, made visible, is the diagnosis — a latency waterfall with
violation markers points at the problem without any automation. **OIDTrace + OIDViz is
the suite's MVP**: capture the evidence, see the problem. OIDSense (automated settings
finder) and OIDEmu build on top.

## Product shape

`oidviz report <trace-or-bundle> -> report.html` — a **self-contained, single-file HTML
report** (inline JS/CSS/data, no server, no external assets). Rationale from the usage
reality: traces travel through support tickets; the report must open by double-click on
any machine, attach to a ticket, and work offline. (Precedent: the previous project's
waterfall/heatmap/flamegraph demo pages.)

## Views (initial set)

1. **Verdict panel** — the `summary` record plus header settings: end reason, exchange
   count, violation tally, slowest ranges. The first screen; often the only one needed.
2. **Latency waterfall** — per-exchange duration in walk order (from `attempts`
   timestamps), violation markers inline, retries visible as stacked attempt bars.
3. **Subtree aggregation** — latency rolled up by OID prefix (table or treemap): finds
   "the sensor subtree is slow" at a glance.
4. **Run comparison** — for session bundles: the same device at bulk 10 vs bulk 8 vs
   bulk 1, side by side. This is the visual form of the troubleshooting workflow.
5. **Exchange detail** — drill-down per exchange: parsed request/response, returned vs
   sent request-id, per-attempt timing. `malformed` markers (decode error + datagram
   length) prominently flagged.

## Constraints

- **Streaming reader** (format spec § 6a): report generation is a single pass per file;
  the embedded data is the _aggregated_ view model, not the raw trace, so report size
  stays small even for 100k-line traces.
- No values and no packet bytes exist in traces (except the admin-approved
  `system_info` allowlist), so none can leak into reports.
- Reads only the documented format (`docs/trace-format.md`); no private coupling to
  OIDTrace internals.

## Open questions (for the real brainstorming session)

- Rendering stack: hand-rolled SVG/canvas vs a small embeddable chart lib (must be
  inlineable and license-clean).
- How much interactivity (zoom/filter) the single-file constraint allows before it
  becomes an app.
- Whether `oidtrace show` and `oidviz` share a reader/aggregation library (likely yes —
  same shared package as the codec).
- Name: OIDViz vs OIDPlot vs OIDSee.
