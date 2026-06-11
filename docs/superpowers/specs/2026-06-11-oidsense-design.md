# OIDSense Design (early draft)

Date: 2026-06-11
Status: **draft — captures the settings-finder algorithm discussed during OIDTrace
design; not yet fully brainstormed**
Validation: the survey → pinpoint → fit loop is proven end-to-end in miniature by
`experiments/poc_roundtrip.py` (found 100/100 slow OIDs and derived settings against an
emulated quirky device)

OIDSense is the troubleshooting brain of the suite: offline analysis of traces plus an
**online adaptive settings finder**. The visualization of traces is OIDViz's job
(separate spec); OIDSense produces _verdicts and recommended settings_.

**Phase 0 is the doctor** (the suite's MVP, separate spec): the deterministic support
ladder over the same pipeline. The adaptive finder described here evolves from it —
same drivers, same verdict output, smarter probe selection.

## Why the settings finder must be online

A GetBulk exchange yields one latency number for ~10 OIDs — attribution inside a bulk is
impossible from bulk data alone. Finding the slow OIDs therefore requires _new, adaptively
chosen_ requests. A recording cannot answer those (this is why standalone trace replay
was dropped); a live device or an OIDEmu profile can.

## The algorithm (three phases)

1. **Survey** — bulk walk with conservative settings (bulk 8–10, generous timeout).
   Per-exchange latency from the trace's `attempts` timestamps yields a latency profile
   over OID ranges; slow _ranges_ identified.
2. **Pinpoint** — re-walk each slow range at bulk 1 (per-OID attribution), several
   passes: first-touch caching is common (sensor reads cached after first query), so
   median-of-N separates consistent slowness from jitter. Binary search with
   intermediate bulk sizes is an optimization for very large ranges.
3. **Derive settings** — mechanical from measurements:
   - `timeout = max observed single-OID latency + 1 s margin`
   - `retries = 2` (repeated silent failures rarely recover; see
     docs/snmp-trouble-shooting.md)
   - slow-OID / subtree exclusion list (often the pragmatic fix)
   - optional **bulk-size threshold probe** — increase max-repetitions on a known-fast
     range until failure. **Opt-in only**: on the wrong device the failure mode is a
     reboot.

Output should be phrased in the consumer's terms — concretely, Checkmk's per-host SNMP
knobs (timing, bulk size) — so the recommendation is paste-ready, not a prose diagnosis.

## Architecture notes

- The settings finder is **another driver of the OIDTrace pipeline**
  (codec/transport/writer); every probing session emits a trace. No second SNMP stack.
- Development and CI run against OIDEmu profiles. The emulator's **fiction report**
  (answers served from `assumed` profile territory) is consumed by OIDSense to emit a
  _capture plan_: which additional runs (e.g. bulk-1 over range X) would turn assumed
  dimensions into measured ones. Results obtained against assumed dimensions validate
  the algorithm's mechanics, not its accuracy on that device.
- Offline analysis (verdicts over existing traces: violation patterns, reboot proof via
  `system_info` sysUpTime, latency-budget arithmetic `timeout × retries × OIDs`) shares
  the streaming reader with OIDViz.

## Open questions (for the real brainstorming session)

- Slow-exchange threshold for phase 1 (fixed ms vs statistical outlier detection).
- How many pinpoint passes; cache-detection heuristics.
- Verdict taxonomy (map of violation patterns → known device pathologies → remedies).
- Exact Checkmk ruleset fields the recommendations target.
