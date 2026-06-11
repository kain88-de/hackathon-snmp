# OIDTrace Architecture Design

Date: 2026-06-11
Status: approved

## Purpose

OIDTrace captures an SNMP walk against a single device in a highly detailed, portable trace.
The trace is the input for OIDPlayback (replay the device as truthfully as possible) and
OIDSense (troubleshooting analysis). Traces are produced by customer admins on-site and
attached to support tickets, so they must be: a single file, inspectable, reasonably small,
and free of device values.

Core requirements:

- Record both parsed PDU-level data (human-readable) and raw wire bytes, to capture
  RFC violations — especially responses returning a wrong request-id.
- Never store SNMP values or the community string. Raw packets are scrubbed.
- Support SNMP v1 + v2c first; the format must leave room for v3 (including priv) later.
- A partial trace (crash, Ctrl-C, unresponsive device) is still a valid, useful trace.

## Trace format decision: CBOR sequence

The trace file is a **CBOR sequence (RFC 8949 + RFC 8742)**: concatenated CBOR records,
appended one per exchange during the walk.

Why CBOR over the alternatives considered:

- **vs. JSONL+gzip**: same data model and same streaming/append property, but CBOR has a
  native bytes type — raw packets are stored as bytes, not hex/base64. JSON remains the
  *presentation* format: `oidtrace show` renders the trace as JSON losslessly (bytes → hex),
  which satisfies the "portable json we can show to admins" requirement.
- **vs. pcapng (+ JSONL sidecar)**: Wireshark support is attractive, but pcapng has no home
  for derived data (settings, retries, violations, walk events); correlating a two-file
  format is the expensive kind of custom tooling. Instead, `oidtrace export-pcap` generates
  a pcapng *view* on demand from the stored raw bytes.
- **vs. protobuf/Avro/Parquet**: schema artifacts defeat admin transparency; Parquet cannot
  append.

Size estimate: a large device (~100k OIDs, bulk 10) is ~10k exchanges → tens of MB,
well within support-ticket limits; scrubbed packets compress extremely well if needed.

## Components

```
oidtrace CLI
├── walk         capture a trace
├── show         render trace as JSON (the portable view for admins)
└── export-pcap  emit pcapng of captured packets for Wireshark

walk pipeline:
  Walk Engine ──> Codec ──> Transport ──> device
       │            │           │
       └────────────┴───────────┴──> Scrubber ──> Trace Writer (CBOR append)
```

### Transport

Owns a plain UDP socket. Sends datagrams, receives everything that comes back with precise
timestamps, and never validates: responses with wrong request-ids, duplicates, and late
replies arriving after a retry are recorded, not dropped. This is the load-bearing decision —
high-level SNMP libraries hide exactly this traffic, so OIDTrace cannot sit on top of one
for the wire path.

### Codec

BER encoding for requests (v1 GetNext, v2c GetBulk initially) and a **tolerant decoder** for
responses: decode failures do not raise, they produce a "malformed" record carrying the raw
bytes and whatever was salvageable. Violation checks (request-id mismatch, non-increasing
OIDs, missing endOfMibView) are pure functions over decoded PDUs.

### Walk engine

Drives the GetNext/GetBulk loop with configurable settings (bulk size, timeout, retries,
start OID), handles retries, and decides termination: endOfMibView, walked past subtree,
OID-loop detection, or overall time budget.

### Scrubber

Re-encodes each packet with value octets zeroed before anything touches disk, and redacts
the community string (present in every v1/v2c message header). Unparseable packets are
flagged and kept verbatim — "we couldn't even parse it" is evidence — with a
`--drop-unparsed` escape hatch. `show` highlights verbatim packets so the admin knows
exactly what they would be sharing.

### Trace writer

Appends one CBOR record per exchange, flushed as the walk proceeds, so a crash or Ctrl-C
leaves a valid trace.

### Packaging

Python package managed with uv, following the existing monorepo layout. OIDPlayback and
OIDSense will need the codec and trace-reading code; the trace schema + codec should live
where both can import them (small shared package now, or extracted when OIDPlayback starts).

## Trace record schema

Each record is a CBOR map with a `type` field. Readers ignore unknown fields; `format_version`
in the header gates breaking changes. This is the whole compatibility story — enough room to
add v3 fields (auth params, decrypted-PDU bytes) later without breaking readers.

### `header` (always first)

```
{type: "header", format_version: 1, tool: "oidtrace 0.1.0",
 started_at: <timestamp>,
 target: {host: <as given on CLI>, resolved_ip: <IP used>, port: 161},
 snmp: {version: "2c"},                  # community redacted, never stored
 settings: {bulk_size: 10, timeout_s: 2.0, retries: 2, start_oid: "1.3.6.1"}}
```

### `exchange` (one per logical request)

```
{type: "exchange", seq: 42,
 request: {pdu: "getbulk", request_id: 1042, oids: ["1.3.6.1.2.1.2.2.1.3"],
           non_repeaters: 0, max_repetitions: 10, raw: <bytes, scrubbed>},
 attempts: [{sent_at: <ts>, received_at: <ts> | null}, ...],   # one per send incl. retries
 response: {request_id: 1,                # request_id AS RETURNED by the device
            error_status: 0, error_index: 0,
            varbinds: [{oid: "...", vtype: "OctetString"}, ...],  # types only, no values
            raw: <bytes, scrubbed>} | null,                       # null = never answered
 stray_responses: [...],          # datagrams matching no outstanding request
 violations: ["request-id-mismatch"],
 malformed: {raw: <bytes>, error: "..."} | absent}
```

Timing is derivable from per-attempt timestamps (latency, retry cost, cumulative
`timeout × retries × OIDs`); no duplicated duration fields.

### `event`

Walk-level observations not tied to one exchange: `oid-loop-detected`,
`walk-aborted-by-user`, `time-budget-exceeded`.

### `summary` (last, best-effort)

Exchange count, duration, end reason, violation tally — `show` prints a one-screen verdict
without re-scanning.

## Error handling

Guiding rule: **device misbehavior is data, not an error.** Wrong request-ids, malformed
packets, partial responses, and slow OIDs are recorded in exchange records and the walk
continues. Only three things abort a walk:

1. **Local/operator errors** — bad CLI args, DNS name does not resolve, cannot bind socket,
   cannot write trace file. The target is resolved **once, up front, before any socket is
   opened**; resolution failure fails fast with a clear message and no trace file. The
   resolved IP is pinned for the whole walk and recorded in the header.
2. **Total silence** — device never answers. Give up after the first N fully-timed-out
   exchanges (configurable); write `summary` with `end_reason: "unresponsive"`. Still a
   valid trace.
3. **Runaway walks** — OID loops and devices without end-of-MIB signal are capped by the
   loop detector and time budget; recorded as an `event` plus `end_reason`.

Ctrl-C is a first-class exit: flush the current record, write `summary` with
`end_reason: "interrupted"`, exit 0.

## Testing

1. **Codec + scrubber unit tests** (the bulk): encode/decode round-trips; tolerant decode
   against hand-crafted malformed BER; the critical scrubber property — *a scrubbed packet
   parses identically to the original except values are zeroed, and contains no byte
   sequence from any original value*. Candidate for Hypothesis property-based tests.
2. **Trace format tests**: write → read round-trip; truncated-file reads (the crash-safety
   claim is tested, not assumed); `show` output is valid JSON; `export-pcap` output parses
   with tshark where available.
3. **Integration against a quirk emulator**: walk a local fake device injecting the known
   pathologies — wrong request-id, no end-of-MIB, fixed sequence numbers, slow OIDs, crash
   above bulk size 8 — and assert the trace records each violation. The deleted `emulator/`
   package in git history covers much of this; resurrect rather than rewrite.

Async test functions; `just` targets for the suite.

## Out of scope (for now)

- SNMPv3 (all security levels) — format leaves room via versioning and unknown-field
  tolerance; full support including priv requires storing decrypted PDU bytes.
- OIDPlayback and OIDSense themselves — separate specs; they consume this trace format.
- Recording SNMP values in any form.
