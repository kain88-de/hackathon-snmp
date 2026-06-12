# OIDTrace Architecture Design

Date: 2026-06-11
Status: approved — **implemented 2026-06-12** (`oidtrace/` + `traceformat/` packages;
plan `docs/superpowers/plans/2026-06-11-oidtrace.md` fully executed)
Validation: core ideas proven end-to-end by `experiments/poc_roundtrip.py` (codec,
quirk-tolerant walk, schema-valid traces); format performance measured by
`experiments/trace_format_perf.py` — results in `experiments/*-results.md`;
implementation verified by 141 tests incl. a net-snmp cross-walk, branch coverage
98–100%, and Hypothesis fuzzing of the tolerant decoder

## Purpose

OIDTrace captures an SNMP walk against a single device in a highly detailed, portable trace.
The trace serves OIDSense (troubleshooting analysis, including an automated settings
finder) and is the raw material for fitting OIDEmu device profiles (deferred until
traces flow — see the OIDEmu spec's scope decision).
Traces are produced by customer admins on-site and
attached to support tickets, so they must be: a single file per walk, inspectable with
nothing but a text tool, reasonably small, and free of device values.

Core requirements:

- Record parsed PDU-level evidence — per-attempt timing, varbind types/lengths, and RFC
  violations, especially responses returning a wrong request-id. (Raw wire bytes are
  not in format v1 at all; see "Raw capture (format v2 remark)" below.)
- Never store SNMP values or the community string — except a small, admin-approved
  system-OID allowlist.
- Support SNMP v2c first; v1 next (explicitly de-scopable); the format must leave room
  for v3 (including priv) later.
- A partial trace (crash, Ctrl-C, unresponsive device) is still a valid, useful trace.

### Usage reality the design serves

The admin almost always runs OIDTrace **on the monitoring server** (SNMP access is ACL'd to
its IP), against a device that is slow by definition. The benchmark to beat is support
saying "run `snmpbulkwalk` and paste the output" — so invocation must be one command,
progress must be visible, and the admin must get an immediate payoff (a terminal summary),
not just an opaque file.

**Adoption thesis**: trace acquisition friction is the suite's biggest external risk.
The mitigation is that the admin's payoff is immediate and local (terminal verdict, an
OIDViz report they see themselves) — not "upload and wait". Long term, capture belongs
_inside_ Checkmk, which already speaks SNMP to the device from the right network
position; the trace format is the durable artifact, the standalone CLI the bootstrap.

## Trace format decision: gzipped JSON Lines

The trace file is **gzipped JSON Lines**: one JSON object per line, appended and flushed
per exchange during the walk.

Why JSONL over the alternatives considered:

- **vs. CBOR sequence**: CBOR was the initial choice (native bytes, binary-JSONL
  semantics), but it fails the transparency test at both ends: the admin needs our tool to
  verify what they are about to share, and support needs it to read a ticket attachment.
  JSONL+gzip means `zcat | less` / `jq` works everywhere with zero setup. CBOR's remaining
  advantage — native bytes — became moot when packet bytes left the format entirely.
- **vs. pcapng (+ JSONL sidecar)**: Wireshark support is attractive, but pcapng has no home
  for derived data (settings, retries, violations, walk events); correlating a two-file
  format is the expensive kind of custom tooling. A pcapng export would anyway need
  packet bytes — format v2 territory.
- **vs. protobuf/Avro/Parquet**: schema artifacts defeat admin transparency; Parquet cannot
  append.

Size estimate: a large device (~100k OIDs, bulk 10) is ~10k exchanges → tens of MB
uncompressed (measured with the since-removed raw fields included — lite v1 traces are
smaller still); gzip brings it to single-digit MB, well within support-ticket limits.

## Components

```
oidtrace CLI
├── walk         capture a trace (prints summary at end, progress on stderr)
└── show         pretty-print a trace [post-MVP — the file is zcat/jq-readable]

walk pipeline:
  Walk Engine ──> Codec ──> Transport ──> device
       │            │           │
       └────────────┴───────────┴──> Trace Writer (JSONL append)
```

`walk` accepts a **settings matrix** (e.g. several bulk sizes / timeouts); the combos run
sequentially and **each run writes its own trace file** into an output directory (zippable
for a ticket). The trace schema stays one-walk-per-file; the matrix is purely a CLI
convenience. Matrix capture (e.g. bulk-10 survey plus bulk-1 over slow ranges) is also the
guidance for capturing a problem device: a single bulk walk contains no per-OID timing, so
an OIDEmu profile fitted from the bundle is only as truthful as the request shapes the
bundle actually contains.

**Capture scope guidance**: full-tree walks are the wrong default for large devices —
monitoring polls specific subtrees, and the diagnostic question is whether _those_ fit
the cycle window. The recommended pattern is **subtree-scoped, time-budgeted runs**
(e.g. three ~15 s runs: bulk 10 baseline, bulk 0/GetNext slow-check, bulk-stress),
not exhaustive coverage; a bounded behavioral fingerprint in under a minute beats an
hours-long map. Mechanics: multiple `--start-oid` values spawn one run per subtree
within the same session (one-walk-per-file preserved); `--resume <trace>` continues
where a previous run's time budget hit, recording the optional `settings.resume_from`
field (additive, no format version bump) while `start_oid` remains the subtree bound.
Adaptivity (changing settings based on observed latency) deliberately stays out of
OIDTrace — that is OIDSense's settings finder driving the same pipeline; the
admin-facing capture tool stays deterministic, predictable, and explainable.

The walk engine is **one pluggable driver** of the codec/transport/writer
pipeline — the **doctor** (the suite's MVP) is the first additional driver, running the
support settings ladder over the same stack, and the OIDSense adaptive finder follows.
Records flow to **pluggable sinks**: the gzip trace file is the canonical
sink, terminal progress is a second, and an SSE endpoint for a live web UI is a third —
the format's streaming guarantee (one self-contained record per line) makes every sink
see the same stream with no second data path. The future OIDSense settings finder (survey walk → pinpoint slow OIDs at bulk 1 →
derive settings) is another driver of the same stack; every probing session emits a trace.

### CLI usability requirements

- `--label "switch-floor3"` — admin-chosen run label recorded in the header; the only
  device-correlating information in a trace, and the admin typed it themselves.
- Community string is taken from the `OIDTRACE_COMMUNITY` environment variable
  (default `public`; interactive prompt post-MVP) — never a CLI argument
  (shell history on a shared monitoring server).
- Progress on stderr during the walk; a terminal summary at the end (exchange count,
  violations found, path of the written trace). Slowest-ranges in the terminal summary
  is deferred to the doctor/OIDViz latency analysis (plan backlog).

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

BER encoding for requests (v2c Get/GetNext/GetBulk initially; v1 later) and a **tolerant decoder** for
responses: decode failures do not raise, they produce a "malformed" record carrying the
decode error, the datagram length, and whatever was salvageable. Violation checks (request-id mismatch, non-increasing
OIDs, missing endOfMibView) are pure functions over decoded PDUs.

### Walk engine

Drives the GetNext/GetBulk loop with configurable settings (bulk size, timeout, retries,
start OID), handles retries, and decides termination: end of MIB (`endOfMibView` in v2c,
`noSuchName` error-status in v1), walked past subtree, OID-loop detection, or overall time
budget.

### Raw capture (format v2 remark)

Format v1 stores **no packet bytes at all** — parsed evidence (timing, varbind
types/lengths, returned request-ids, violations, malformed markers with error + length)
carries the diagnostic load, and with no bytes on disk the no-values promise holds
trivially. If wire-level forensics or exact-encoding reproduction (e.g. for better
emulation) ever earns its keep, that is a **format v2** with redacted packet capture —
a problem to design then, not now.

**System-OID allowlist (post-MVP — format supports it, v1 tooling does not emit it)** —
the one deliberate exception to "no values": a handful of system
OIDs (sysDescr, sysObjectID, sysUpTime) are read with a dedicated Get at walk start and
walk end and stored with values in `system_info` records. Rationale: sysDescr/sysObjectID
answer support's first question ("what device/firmware is this?"), and sysUpTime
before/after is the only proof of the worst quirk — _device reboots on large bulk
requests_. The captured values are **shown to the admin at capture time for approval**;
they can be excluded interactively or via `--hide-system-info`. Allowlisted values live
only in the explicit, visible `system_info` records.

### Trace writer

Appends one JSON line per record to the gzipped trace, flushed as the walk proceeds, so a
crash or Ctrl-C leaves a valid (possibly truncated, still readable) trace.

### Packaging

Python packages managed with uv in one workspace. A shared `traceformat` package holds
the format types: pydantic models **generated from** `docs/trace-format.schema.json`
(datamodel-code-generator; the schema stays authoritative, CI checks freshness) plus the
producer-side vocabulary StrEnums. `oidtrace` depends on it; OIDViz and the doctor import
the same models, getting validated round-trips instead of re-tested dict shapes.

## Trace record schema

The file format is specified authoritatively in **`docs/trace-format.md`** (record types
`header`, `system_info`, `exchange`, `event`, `summary`; field tables, type vocabularies,
timestamp semantics, privacy guarantees, versioning rules). Where this
design document and the format spec disagree, the format spec wins.

Design-level points worth restating here:

- Timing is derivable from per-attempt timestamps (latency, retry cost, cumulative
  `timeout × retries × OIDs`); no duplicated duration fields.
- The exchange record stores the request-id **as returned by the device** next to the one
  sent — the wrong-request-id smoking gun.
- Varbinds carry `oid`, `vtype`, and `vlen` (value byte length) but never values; `vlen`
  is the format's only source of value sizes (for size-aware analysis and profile
  fitting).
- The trace stores no target host name, IP, or port; the optional admin-chosen `label` is
  the only correlation handle.
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
   decode against hand-crafted malformed BER. Trace format round-trips,
   including truncated-file reads (the crash-safety claim is tested, not assumed) and every
   written line validating against `docs/trace-format.schema.json`. Cross-validation
   without system tools: **pysnmp as a test-only dependency** must parse packets our
   codec encodes into the same fields — decoding **spec-driven**
   (`asn1Spec=Message()`); pyasn1's schemaless decoder cannot walk SNMP's
   context-tagged PDUs (learned in the PoC, see
   `experiments/2026-06-11-poc-roundtrip-results.md`).
2. **Integration over loopback UDP**: the quirk emulator runs in-process as an asyncio UDP
   server on `127.0.0.1:<random port>` (the fast pattern from the previous project). Each
   test configures a quirk — wrong request-id, no end-of-MIB, fixed sequence numbers, slow
   OIDs, crash above bulk size 8 — runs a real walk, and asserts the trace records the
   violation.
3. **Reference-tool tests** (marked `reference_tools`, skipped with a visible warning when
   the tool is absent):
   - **net-snmp cross-walk**: `snmpbulkwalk` (subprocess) and our walker both walk the same
     emulator; the OID sequences must match.

Runner: pytest with async test functions. `just test` runs layers 1–2 (fast default);
`just test-all` runs everything and **fails hard** if reference tools are missing, so
skip-if-missing cannot silently become never-runs.

As built, the gates exceed this plan: `just ci` chains ruff strict → pyrefly → a
vulture dead-code gate (documented whitelist) → pytest; `just cov` reports branch
coverage (100% traceformat, 98% oidtrace — remaining misses are defensive branches);
Hypothesis fuzzes the decoder's never-raises contract; the codec's fault branches are
individually exercised by per-layer crafted malformations.

### Quirk emulator = seed of OIDEmu

The test emulator is a **scripted simple device** — small hardcoded OID tree, quirks
injected via test configuration — not a trace consumer, so there is no chicken-and-egg
with traces. It is built as a **responder core with a pluggable behavior source**:
scripted source now for tests; a fuller OIDEmu product (declarative profiles, fitting
from traces, provenance) was explored and shelved — design sketch in git history. The
emulator reuses the shared codec package (with raw-byte escape hatches for deliberately
malformed quirks).

Sharing the codec between walker and emulator means a shared encoding bug could pass tests
silently; the reference-tool layer (`snmpbulkwalk` cross-walk) and the pysnmp spec-driven
decode in unit tests exist to break exactly that circularity, independently of our code.

## De-scoping order

If time runs short, cut in this order (decided now, not under pressure):

Already cut from the MVP for implementor simplicity (design retained, see plan
backlog): system-OID allowlist capture, GetNext walk mode (GetBulk max-repetitions 1
covers it), `show` subcommand, interactive community prompt.

1. SNMP v1 support — v2c GetBulk covers the troubleshooting doc's cases.
2. The settings-matrix CLI convenience — admins can invoke the tool repeatedly.

The codec, transport, trace writer, and walk-end summary are the product and cannot be
cut; the codec's scope stays ruthlessly minimal (encode two PDU types, decode one).

## Out of scope (for now)

- SNMPv3 (all security levels) — format leaves room via versioning and unknown-field
  tolerance; full support including priv requires storing decrypted PDU bytes. When v3
  arrives, the plan is to reuse pysnmp's USM/crypto machinery _below_ our own message
  layer rather than hand-rolling key localization and DES/AES.
- OIDEmu (beyond the test fixture) and OIDSense — separate specs; they consume this trace
  format. Note the scope line: an emulator profile fitted from traces reproduces protocol
  behavior and timing, **not values** — it cannot stand in for the device against
  value-parsing consumers (e.g. Checkmk checks); value-faithful replay is snmpsim's
  territory, quirk-faithful emulation is ours. (Standalone trace replay — "OIDPlayback" —
  was dropped: a recording cannot answer the novel probes an adaptive settings finder asks.)
- Recording SNMP values in any form — with one acknowledged exception: the admin-approved
  system-OID allowlist (`system_info` records). Unparseable packets are recorded as
  markers (decode error + datagram length), never as bytes.
