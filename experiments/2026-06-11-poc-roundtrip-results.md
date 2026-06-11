# End-to-end PoC — results

Date: 2026-06-11
Script: `experiments/poc_roundtrip.py` (`uv run --with jsonschema,pysnmp python experiments/poc_roundtrip.py`)

Thinnest vertical slice of the suite against a 1000-OID emulated device (20 ms/OID slow
column, fixed-request-id quirk) over real loopback UDP. **All five ideas under test pass:**

1. **Hand-rolled minimal BER codec is feasible and small** (~150 lines for encode
   GetBulk / decode Response). Every emitted packet decodes against pysnmp's v2c
   `Message` spec — the independent cross-validation works.
2. **Quirk-tolerant walking works**: a device answering every request with request-id `1`
   (which strict libraries reject) is walked to completion; `request-id-mismatch` is
   recorded on all 206 exchanges.
3. **Trace emission per the format spec**: every line of both runs validates against
   `docs/trace-format.schema.json`; survey + pinpoint share a `session.id`.
4. **Profile-driven emulator**: tree + latency rules + quirk switches served from a
   declarative profile (the OIDEmu shape).
5. **The settings-finder loop closes**: survey (bulk 10) finds the slow exchanges →
   pinpoint (bulk 1, slow subtree only) attributes latency per OID → fit recovers the
   exact ground truth: full tree (1000/1000 OIDs, types, vlens), quirk `fixed:1`,
   100/100 slow OIDs, derived settings (timeout ≥ max latency + margin, subtree to
   exclude).

## Lessons that fed back into the specs

- **pyasn1's schemaless decoder cannot walk SNMP's context-tagged PDUs** (`0xA5` GetBulk
  fails with a length error). The codec cross-validation in the test plan must be
  spec-driven: `decoder.decode(raw, asn1Spec=pysnmp Message())`, not a generic BER parse.
- The PoC deliberately skips: scrubber, asyncio transport, retries/timeout edge cases,
  v1, CLI. Nothing in those gaps blocks the validated ideas.
