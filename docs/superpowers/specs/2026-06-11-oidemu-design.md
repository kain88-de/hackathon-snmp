# OIDEmu Design (early draft)

Date: 2026-06-11
Status: **draft — captures decisions made during OIDTrace design; not yet fully brainstormed**
Validation: the profile-driven responder shape (tree + latency rules + quirks over real
UDP) is proven by `experiments/poc_roundtrip.py`; serve-path lookup measured at ~1 µs
(`experiments/2026-06-11-trace-format-perf-results.md`)

OIDEmu is the profile-driven SNMP device emulator of the OIDSense suite. It exists for
three consumers:

1. **OIDTrace/OIDSense test suites** — quirky fake devices over loopback UDP.
2. **OIDSense algorithm development** — the settings finder is adaptive and asks novel
   questions; it needs a _model_ that can answer anything, not a recording. (This is why
   standalone trace replay, "OIDPlayback", was dropped.)
3. **Demos** — a library of pathological device personalities, no broken hardware needed.

## Scope decision (2026-06-11): infrastructure now, product later

OIDEmu splits into two halves with very different dependencies:

- **The emulator** (responder core + hand-written profiles) is needed regardless of
  external adoption — it serves all three consumers above and is already being built as
  the OIDTrace test fixture. Build it.
- **`fit-profile`** is the only part gated on customer traces actually existing — i.e.
  on people running OIDTrace and sending results, which is the suite's biggest adoption
  risk. **Deferred** until traces flow. The trace format already guarantees fitting
  stays possible (validated under the emulator-sufficiency review), so deferral costs
  nothing; if traces never materialize, only this spec section is wasted.

## Architecture

Thin asyncio UDP responder + the shared codec package. Per request: decode → ask the
**behavior source** for a response plan → encode (or emit raw bytes for deliberately
malformed responses) → wait out modeled latency → send.

Behavior sources are pluggable:

- **ScriptedSource** — quirks configured in test code. Exists first; this is the test
  fixture from the OIDTrace spec.
- **ProfileSource** — loads a declarative device profile (below). Grows into the product.

## Device profile

A human-readable, hand-editable document (YAML or JSON) with three parts:

1. **Tree shape** — ordered `(OID, vtype, vlen)` list. Values are synthesized at response
   time (zeros of the right type and length) so response packet sizes match the real
   device (from `vlen`). Exact wire-encoding reproduction for non-canonical-BER devices
   would need a future format v2 with packet capture — out of scope.
2. **Timing model** — latency rules attached to OID ranges plus a default; bulk response
   latency = sum of per-OID costs of what the agent processed. Cache modeling
   (first-touch cost, TTL).

   ```yaml
   latency:
     default_ms: 5
     rules:
       - prefix: 1.3.6.1.4.1.2636.3.60 # SFP sensors
         per_oid_ms: 7000
         cache: { after_first_touch_ms: 10, ttl_s: 30 }
   ```

3. **Quirks** — declarative switches: `request_id: echo | fixed:<n>`;
   `end_of_mib: endOfMibView | silence | wrap`;
   `bulk_crash: {threshold: 8, mode: reboot, dead_for_s: 45}` (reboot resets emulated
   sysUpTime — makes OIDTrace's allowlist reboot-proof testable end to end);
   `refusal: icmp-port-unreachable | silence` for down states;
   `source_port: queried | other` (response-from-unexpected-source);
   raw-byte response overrides keyed by request, for malformed-BER cases.

## Provenance: measured vs assumed

**Every profile entry carries provenance** — `measured` (fitted from trace data) or
`assumed` (default / interpolation). This is the core honesty mechanism; without it,
results obtained against a partially fitted profile get mistaken for device truth.

## Fitting profiles from traces (`fit-profile`)

Pure function: trace bundle (files sharing one `session.id`, see
`docs/trace-format.md`) → profile draft.

- **Tree shape** ← union of response varbinds in walk order; `vlen` for sizes.
- **Timing** ← per-attempt timestamps, **single-attempt exchanges only** (trace format
  § 4.3 normative rules: multi-attempt latency is ambiguous between retries and would
  systematically underestimate when device latency exceeds the timeout; stray-correlated
  pairs may be used where present). Bulk-N runs support only range-level rules; bulk-1
  runs give per-OID rules; repeated passes expose caching. Ranges yielding only
  multi-attempt exchanges are fitted as `assumed` and flagged in the fiction report:
  "recapture with larger timeout".
- **Quirks** ← recorded violations (request-id pattern, end-of-MIB behavior, source
  mismatch), attempt-level socket errors (refusal vs silence), sysUpTime resets between
  `system_info` records (reboot/crash thresholds, correlated with bulk-size changes
  across runs).

Scope limit (inherited from the trace format): fitted profiles reproduce **protocol
behavior and timing, not values** — an emulated device cannot feed value-parsing
consumers (e.g. Checkmk checks). Value-faithful emulation is snmpsim's territory.

## Partial-matrix behavior

The emulator never refuses to run on incomplete data; it degrades per dimension:

| Profile dimension   | Full matrix              | Single bulk-10 walk                       |
| ------------------- | ------------------------ | ----------------------------------------- |
| Tree shape          | measured                 | measured (complete if the walk completed) |
| Range-level latency | measured                 | measured                                  |
| Per-OID latency     | measured (bulk-1 runs)   | assumed — range total spread uniformly    |
| Bulk-size threshold | measured (varied bulks)  | assumed — compliant at all sizes          |
| Cache/TTL           | measured (repeated runs) | assumed — no caching                      |
| Quirks              | measured                 | measured, but only those triggered        |

**Fiction report**: at runtime the emulator logs every answer that came from `assumed`
territory. After a run: "23% of probes hit assumed territory: per-OID timing in range X,
bulk behavior above 10." This report **is the capture plan for the next matrix** — the
incremental loop is: capture cheaply → fit → develop against the profile → fiction report
names the runs that would buy real confidence → request only those. A full matrix is the
converged end state, not a prerequisite.

Caveat to keep visible: results against assumed dimensions validate an algorithm's
_mechanics_, not its _accuracy_ on that device.

## Performance model

**Serving never touches traces.** The request path reads only the in-memory profile:
tree successor lookup is a sorted OID array + bisect (O(log n), measured 1.05 µs at 100k
OIDs; ~few MB resident). This is an architectural rule, not an optimization — traces are
offline inputs to `fit-profile`, full stop. There is no "which file to look into" at
request time: `fit-profile` merges the whole session bundle into **one** profile;
file selection happens at fit time, never at serve time.

**Per-request cost arithmetic**: one bisect per request (a bulk-10 response is one
search plus an array slice, not ten searches); latency rules are precompiled at profile
load into a per-OID cost array, so timing lookup is O(1). Total request-path overhead
~1–2 µs against modeled response times of ≥1 ms: 0.1–0.2%, non-compounding.

**Timing fidelity floor**: emulated latency is produced by sleeping, and OS scheduler
granularity puts ±50–100 µs jitter on any sleep — ~50× the lookup cost. Below that sits
Python's UDP stack (~tens of µs per recv/send). Devices with ≥1 ms response times are
comfortably emulatable; sub-100 µs timing fidelity would be limited by Python and the
kernel, not by the profile data structures or the trace format.

**Fitting is one streaming pass per file** (guaranteed by the trace format's streaming
guarantee, `docs/trace-format.md` § 6a), with per-file aggregates merged across the
bundle. Memory is proportional to distinct OIDs, not trace bytes. Worst realistic bundle
(100k-OID device, 5-run matrix incl. a bulk-1 run, ~300 MB uncompressed) is seconds of
one-time CPU. Profiles, not traces, are the artifact that must stay compact and
loadable.

## Open questions (for the real brainstorming session)

- Profile file format details (YAML vs JSON, schema, versioning) and a JSON Schema like
  the trace format has.
- Latency model fidelity: is sum-of-per-OID-costs good enough for bulk responses, or do
  devices have per-request overhead worth modeling separately?
- How interpolation marks granularity: range-level measured + per-OID assumed within the
  same rule.
- Fiction report format and how OIDSense consumes it to emit a capture plan.
- CLI shape (`oidemu serve <profile>`, `oidemu fit-profile <bundle>`), package boundary
  with the test fixture.
