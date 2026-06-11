# OIDTrace Architecture Design

Date: 2026-06-11
Status: approved

## Purpose

OIDTrace captures an SNMP walk against a single device in a highly detailed, portable trace.
The trace serves OIDSense (troubleshooting analysis, including an automated settings
finder) and is the raw material for fitting OIDEmu device profiles (a recording cannot
answer the novel probes an adaptive algorithm asks; a model fitted from recordings can).
Traces are produced by customer admins on-site and
attached to support tickets, so they must be: a single file per walk, inspectable with
nothing but a text tool, reasonably small, and free of device values.

Core requirements:

- Record both parsed PDU-level data (human-readable) and raw wire bytes, to capture
  RFC violations — especially responses returning a wrong request-id.
- Never store SNMP values or the community string — except a small, admin-approved
  system-OID allowlist (see Scrubber). Raw packets are always scrubbed.
- Support SNMP v1 + v2c first; the format must leave room for v3 (including priv) later.
- A partial trace (crash, Ctrl-C, unresponsive device) is still a valid, useful trace.

### Usage reality the design serves

The admin almost always runs OIDTrace **on the monitoring server** (SNMP access is ACL'd to
its IP), against a device that is slow by definition. The benchmark to beat is support
saying "run `snmpbulkwalk` and paste the output" — so invocation must be one command,
progress must be visible, and the admin must get an immediate payoff (a terminal summary),
not just an opaque file.

## Trace format decision: gzipped JSON Lines

The trace file is **gzipped JSON Lines**: one JSON object per line, appended and flushed
per exchange during the walk. Raw packet bytes are lowercase hex strings.

Why JSONL over the alternatives considered:

- **vs. CBOR sequence**: CBOR was the initial choice (native bytes, binary-JSONL
  semantics), but it fails the transparency test at both ends: the admin needs our tool to
  verify what they are about to share, and support needs it to read a ticket attachment.
  JSONL+gzip means `zcat | less` / `jq` works everywhere with zero setup. CBOR's remaining
  advantage — no hex encoding of raw bytes — is an efficiency argument that gzip makes
  irrelevant.
- **vs. pcapng (+ JSONL sidecar)**: Wireshark support is attractive, but pcapng has no home
  for derived data (settings, retries, violations, walk events); correlating a two-file
  format is the expensive kind of custom tooling. Instead, `oidtrace export-pcap` can
  generate a pcapng *view* on demand from the stored raw bytes (explicitly deferrable, see
  De-scoping order).
- **vs. protobuf/Avro/Parquet**: schema artifacts defeat admin transparency; Parquet cannot
  append.

Size estimate: a large device (~100k OIDs, bulk 10) is ~10k exchanges → tens of MB
uncompressed (hex roughly doubles the raw-bytes share); gzip brings it to single-digit MB —
well within support-ticket limits.

## Components

```
oidtrace CLI
├── walk         capture a trace (prints summary at end, progress on stderr)
├── show         summarize / pretty-print a trace (the raw file is readable without it)
└── export-pcap  emit pcapng of captured packets for Wireshark [deferrable]

walk pipeline:
  Walk Engine ──> Codec ──> Transport ──> device
       │            │           │
       └────────────┴───────────┴──> Scrubber ──> Trace Writer (JSONL append)
```

`walk` accepts a **settings matrix** (e.g. several bulk sizes / timeouts); the combos run
sequentially and **each run writes its own trace file** into an output directory (zippable
for a ticket). The trace schema stays one-walk-per-file; the matrix is purely a CLI
convenience. Matrix capture (e.g. bulk-10 survey plus bulk-1 over slow ranges) is also the
guidance for capturing a problem device: a single bulk walk contains no per-OID timing, so
an OIDEmu profile fitted from the bundle is only as truthful as the request shapes the
bundle actually contains.

The walk engine is **one pluggable driver** of the codec/transport/scrubber/writer
pipeline. The future OIDSense settings finder (survey walk → pinpoint slow OIDs at bulk 1 →
derive settings) is another driver of the same stack; every probing session emits a trace.

### CLI usability requirements

- `--label "switch-floor3"` — admin-chosen run label recorded in the header; the only
  device-correlating information in a trace, and the admin typed it themselves.
- Community string is taken from a prompt or environment variable, never a CLI argument
  (shell history on a shared monitoring server).
- Progress on stderr during the walk; a terminal summary at the end (exchange count,
  violations found, slowest ranges, path of the written trace).

### Transport

Owns a plain UDP socket. Sends datagrams, receives everything that comes back with precise
timestamps, and never validates: responses with wrong request-ids, duplicates, and late
replies arriving after a retry are recorded, not dropped. This is the load-bearing decision —
high-level SNMP libraries hide exactly this traffic, so OIDTrace cannot sit on top of one
for the wire path.

Because request-ids cannot be trusted, they are never used to match responses to requests.
The walk is strictly sequential — exactly one outstanding request at a time — so every
datagram arriving during the wait window is attributed to the current exchange; a
request-id mismatch is recorded as a violation, not used for routing.

### Codec

BER encoding for requests (v1 GetNext, v2c GetBulk initially) and a **tolerant decoder** for
responses: decode failures do not raise, they produce a "malformed" record carrying the raw
bytes and whatever was salvageable. Violation checks (request-id mismatch, non-increasing
OIDs, missing endOfMibView) are pure functions over decoded PDUs.

### Walk engine

Drives the GetNext/GetBulk loop with configurable settings (bulk size, timeout, retries,
start OID), handles retries, and decides termination: end of MIB (`endOfMibView` in v2c,
`noSuchName` error-status in v1), walked past subtree, OID-loop detection, or overall time
budget.

### Scrubber

Re-encodes each packet before anything touches disk: value octets and the community string
(present in every v1/v2c message header) are replaced with zero bytes **of the same
length**, so packet sizes and structure are preserved exactly — sizes affect real device
behavior, and fitted OIDEmu profiles want to reproduce them. Unparseable packets are
flagged and kept verbatim — "we couldn't even parse it" is evidence — with a
`--drop-unparsed` escape hatch. `show` highlights verbatim packets so the admin knows
exactly what they would be sharing.

**System-OID allowlist** — the one deliberate exception to "no values": a handful of system
OIDs (sysDescr, sysObjectID, sysUpTime) are read with a dedicated Get at walk start and
walk end and stored with values in `system_info` records. Rationale: sysDescr/sysObjectID
answer support's first question ("what device/firmware is this?"), and sysUpTime
before/after is the only proof of the worst quirk — *device reboots on large bulk
requests*. The captured values are **shown to the admin at capture time for approval**;
they can be excluded interactively or via `--hide-system-info`. Raw packets are scrubbed
regardless — allowlisted values live only in the explicit, visible `system_info` records.

### Trace writer

Appends one JSON line per record to the gzipped trace, flushed as the walk proceeds, so a
crash or Ctrl-C leaves a valid (possibly truncated, still readable) trace.

### Packaging

Python package managed with uv, following the existing monorepo layout. OIDEmu and
OIDSense will need the codec and trace-reading code; the trace schema + codec should live
where all of them can import it (small shared package now, or extracted when OIDEmu grows
beyond a test fixture).

## Trace record schema

The file format is specified authoritatively in **`docs/trace-format.md`** (record types
`header`, `system_info`, `exchange`, `event`, `summary`; field tables, type vocabularies,
timestamp and scrubbing semantics, privacy guarantees, versioning rules). Where this
design document and the format spec disagree, the format spec wins.

Design-level points worth restating here:

- Timing is derivable from per-attempt timestamps (latency, retry cost, cumulative
  `timeout × retries × OIDs`); no duplicated duration fields.
- The exchange record stores the request-id **as returned by the device** next to the one
  sent — the wrong-request-id smoking gun.
- Varbinds carry `oid`, `vtype`, and `vlen` (value byte length) but never values; `vlen`
  makes parsed records self-sufficient for OIDEmu profile fitting without re-parsing raw
  hex.
- The trace stores no target host name, IP, or port; the optional admin-chosen `label` is
  the only correlation handle. `export-pcap` uses placeholder addresses in its
  synthesized frames.
- `walk` prints the same verdict to the terminal that the `summary` record carries.

## Error handling

Guiding rule: **device misbehavior is data, not an error.** Wrong request-ids, malformed
packets, partial responses, and slow OIDs are recorded in exchange records and the walk
continues. Only three things abort a walk:

1. **Local/operator errors** — bad CLI args, DNS name does not resolve, cannot bind socket,
   cannot write trace file. The target is resolved **once, up front, before any socket is
   opened**; resolution failure fails fast with a clear message and no trace file. The
   resolved IP is pinned for the whole walk (but not recorded in the trace).
2. **Total silence** — device never answers. Give up after the first N fully-timed-out
   exchanges (configurable); write `summary` with `end_reason: "unresponsive"`. Still a
   valid trace.
3. **Runaway walks** — OID loops and devices without end-of-MIB signal are capped by the
   loop detector and time budget; recorded as an `event` plus `end_reason`.

Ctrl-C is a first-class exit: flush the current record, write `summary` with
`end_reason: "interrupted"`, exit 0.

## Testing

Three layers, ordered fast-to-slow:

1. **Unit tests** (pure Python, no network): codec encode/decode round-trips; tolerant
   decode against hand-crafted malformed BER; the critical scrubber property — *a scrubbed
   packet parses identically to the original except values are zeroed, and contains no byte
   sequence from any original value* (Hypothesis candidate). Trace format round-trips,
   including truncated-file reads (the crash-safety claim is tested, not assumed) and every
   line parsing as valid JSON. Cross-validation without system tools: **pysnmp as a
   test-only dependency** must parse packets our codec encodes into the same fields.
2. **Integration over loopback UDP**: the quirk emulator runs in-process as an asyncio UDP
   server on `127.0.0.1:<random port>` (the fast pattern from the previous project). Each
   test configures a quirk — wrong request-id, no end-of-MIB, fixed sequence numbers, slow
   OIDs, crash above bulk size 8 — runs a real walk, and asserts the trace records the
   violation.
3. **Reference-tool tests** (marked `reference_tools`, skipped with a visible warning when
   the tool is absent):
   - **net-snmp cross-walk**: `snmpbulkwalk` (subprocess) and our walker both walk the same
     emulator; the OID sequences must match.
   - **tshark validation** (with export-pcap, deferrable): `export-pcap` output fed to
     `tshark -T json`; the SNMP dissector must see the same request-ids/OIDs the trace
     claims.

Runner: pytest with async test functions. `just test` runs layers 1–2 (fast default);
`just test-all` runs everything and **fails hard** if reference tools are missing, so
skip-if-missing cannot silently become never-runs.

### Quirk emulator = seed of OIDEmu

The test emulator is a **scripted simple device** — small hardcoded OID tree, quirks
injected via test configuration — not a trace consumer, so there is no chicken-and-egg
with traces. It is built as a **responder core with a pluggable behavior source**:
scripted source now for tests; profile-driven sources later grow into OIDEmu (including
profiles fitted from traces). The emulator reuses the shared codec package (with raw-byte
escape hatches for deliberately malformed quirks).

Sharing the codec between walker and emulator means a shared encoding bug could pass tests
silently; the reference-tool layer exists to break exactly that circularity —
`snmpbulkwalk` validates the emulator and tshark validates the walker, independently of
our code.

## De-scoping order

If time runs short, cut in this order (decided now, not under pressure):

1. `export-pcap` (and its tshark test) — zero critical-path value.
2. SNMP v1 support — v2c GetBulk covers the troubleshooting doc's cases.
3. The settings-matrix CLI convenience — admins can invoke the tool repeatedly.

The codec, transport, scrubber, trace writer, and walk-end summary are the product and
cannot be cut; the codec's scope stays ruthlessly minimal (encode two PDU types, decode
one).

## Out of scope (for now)

- SNMPv3 (all security levels) — format leaves room via versioning and unknown-field
  tolerance; full support including priv requires storing decrypted PDU bytes.
- OIDEmu (beyond the test fixture) and OIDSense — separate specs; they consume this trace
  format. Note the scope line: an emulator profile fitted from traces reproduces protocol
  behavior and timing, **not values** — it cannot stand in for the device against
  value-parsing consumers (e.g. Checkmk checks); value-faithful replay is snmpsim's
  territory, quirk-faithful emulation is ours. (Standalone trace replay — "OIDPlayback" —
  was dropped: a recording cannot answer the novel probes an adaptive settings finder asks.)
- Recording SNMP values in any form — with two acknowledged exceptions: the admin-approved
  system-OID allowlist (`system_info` records), and unparseable packets kept verbatim
  (flagged, highlighted by `show`, removable via `--drop-unparsed`).
