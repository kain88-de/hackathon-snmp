# OIDEmu Design (early draft)

Date: 2026-06-11
Status: **draft — captures decisions made during OIDTrace design; not yet fully brainstormed**

OIDEmu is the profile-driven SNMP device emulator of the OIDSense suite. It exists for
three consumers:

1. **OIDTrace/OIDSense test suites** — quirky fake devices over loopback UDP.
2. **OIDSense algorithm development** — the settings finder is adaptive and asks novel
   questions; it needs a *model* that can answer anything, not a recording. (This is why
   standalone trace replay, "OIDPlayback", was dropped.)
3. **Demos** — a library of pathological device personalities, no broken hardware needed.

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
   device. Exact wire encodings for non-canonical-BER devices come from trace `raw`
   fields, not parsed records.
2. **Timing model** — latency rules attached to OID ranges plus a default; bulk response
   latency = sum of per-OID costs of what the agent processed. Cache modeling
   (first-touch cost, TTL).

   ```yaml
   latency:
     default_ms: 5
     rules:
       - prefix: 1.3.6.1.4.1.2636.3.60   # SFP sensors
         per_oid_ms: 7000
         cache: {after_first_touch_ms: 10, ttl_s: 30}
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
- **Timing** ← per-attempt timestamps. Bulk-N runs support only range-level rules;
  bulk-1 runs give per-OID rules; repeated passes expose caching.
- **Quirks** ← recorded violations (request-id pattern, end-of-MIB behavior, source
  mismatch), attempt-level socket errors (refusal vs silence), sysUpTime resets between
  `system_info` records (reboot/crash thresholds, correlated with bulk-size changes
  across runs).

Scope limit (inherited from the trace format): fitted profiles reproduce **protocol
behavior and timing, not values** — an emulated device cannot feed value-parsing
consumers (e.g. Checkmk checks). Value-faithful emulation is snmpsim's territory.

## Partial-matrix behavior

The emulator never refuses to run on incomplete data; it degrades per dimension:

| Profile dimension      | Full matrix              | Single bulk-10 walk                          |
|------------------------|--------------------------|----------------------------------------------|
| Tree shape             | measured                 | measured (complete if the walk completed)    |
| Range-level latency    | measured                 | measured                                     |
| Per-OID latency        | measured (bulk-1 runs)   | assumed — range total spread uniformly       |
| Bulk-size threshold    | measured (varied bulks)  | assumed — compliant at all sizes             |
| Cache/TTL              | measured (repeated runs) | assumed — no caching                         |
| Quirks                 | measured                 | measured, but only those triggered           |

**Fiction report**: at runtime the emulator logs every answer that came from `assumed`
territory. After a run: "23% of probes hit assumed territory: per-OID timing in range X,
bulk behavior above 10." This report **is the capture plan for the next matrix** — the
incremental loop is: capture cheaply → fit → develop against the profile → fiction report
names the runs that would buy real confidence → request only those. A full matrix is the
converged end state, not a prerequisite.

Caveat to keep visible: results against assumed dimensions validate an algorithm's
*mechanics*, not its *accuracy* on that device.

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
