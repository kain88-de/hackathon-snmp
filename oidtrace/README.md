# oidtrace

`oidtrace walk` records an SNMP walk against a single device as a highly detailed,
portable trace. The trace serves downstream diagnosis (a viewer, an automated
settings finder) and is the raw material for fitting device emulation profiles. It
is designed to be produced by a customer admin on-site and attached to a support
ticket, so a trace is: one file per walk, inspectable with nothing but `zcat`/`jq`,
reasonably small, and free of device values.

The file format itself is specified authoritatively in
[`../traceformat/trace-format.md`](../traceformat/trace-format.md); the shared
`traceformat` package holds the schema-generated models both this tool and its
consumers import. This document covers the capture tool: what it records, why the
format is shaped the way it is, and where the current implementation stops.

## What it records, and what it never records

The load-bearing decision is that the transport owns a plain UDP socket and **never
validates**: responses with the wrong request-id, duplicates, and late replies that
arrive after a retry are all recorded, not dropped. High-level SNMP libraries hide
exactly this traffic, so oidtrace cannot sit on top of one for the wire path. Because
request-ids cannot be trusted they are never used to route responses; the walk is
strictly sequential (one outstanding request at a time), so every datagram arriving
in the wait window is attributed to the current exchange and a request-id mismatch is
recorded as a *violation*, not used for matching.

The guiding rule is **device misbehavior is data, not an error.** Wrong request-ids,
malformed packets, duplicates, non-increasing OIDs, and slow OIDs are recorded and
the walk continues. The decoder is tolerant: a decode failure produces a `malformed`
record carrying the error and datagram length, never an exception.

Traces never contain SNMP values or the community string. Format v1 stores **no
packet bytes at all** — parsed evidence (per-attempt timing, varbind types and byte
lengths, returned request-ids, violations, malformed markers) carries the diagnostic
load, and with no bytes on disk the no-values promise holds trivially. The trace also
records no target host name, IP, or port; the optional admin-chosen `--label` is the
only correlation handle, and the admin typed it themselves.

## Why gzipped JSON Lines

The trace is gzipped JSON Lines: one JSON object per line, appended and flushed per
exchange. The alternatives were considered and rejected:

- **vs. CBOR sequence** — CBOR was the initial choice (native bytes, binary-JSONL
  semantics) but fails the transparency test at both ends: the admin needs a tool to
  verify what they are about to share, and support needs one to read a ticket
  attachment. `zcat | jq` works everywhere with zero setup. CBOR's one advantage,
  native bytes, became moot once packet bytes left the format.
- **vs. pcapng (+ sidecar)** — Wireshark support is attractive, but pcapng has no home
  for derived data (settings, retries, violations, walk events), and correlating a
  two-file format is exactly the expensive custom tooling this avoids. A pcapng export
  would also need packet bytes, which v1 does not store.
- **vs. protobuf/Avro/Parquet** — schema artifacts defeat admin transparency, and
  Parquet cannot append.

A large device (~100k OIDs at bulk 10, ~10k exchanges) is tens of MB uncompressed;
gzip brings it to single-digit MB, well within support-ticket limits.

## Adoption thesis and capture-scope guidance

Trace-acquisition friction is the biggest external risk, and the benchmark to beat is
support saying "run `snmpbulkwalk` and paste the output." The mitigation is that
invocation is one command, progress is visible on stderr, and the admin gets an
immediate local payoff (a terminal summary) rather than an opaque upload-and-wait.

Full-tree walks are the wrong default for large devices: monitoring polls specific
subtrees, and the diagnostic question is whether *those* fit the cycle window. The
recommended pattern is **subtree-scoped, time-budgeted runs** — bound the walk with
`--start-oid` and `--time-budget` — not exhaustive coverage. A walk bounded to a
subtree terminates cleanly the moment its cursor advances past that subtree.
Adaptivity (changing settings from observed latency) deliberately stays out of
oidtrace: the capture tool stays deterministic, predictable, and explainable.

## Termination and exit behavior

Only three things change a walk's outcome; everything else is recorded and the walk
continues:

1. **Local/operator errors** — bad CLI args, a `--start-oid` that will not parse, or a
   host that does not resolve. The target is resolved once, up front, before any
   socket opens; a failure exits 2 with a stderr message and writes no trace file.
2. **Total silence** — after `--give-up-after` consecutive fully-timed-out exchanges
   the walk stops with `end_reason: unresponsive`. Still a valid trace.
3. **Runaway walks** — OID loops and devices with no end-of-MIB signal are capped by
   the loop detector (`oid-loop`) and the wall-time budget (`time-budget-exceeded`),
   each recorded as an event plus an end reason.

A normal walk ends `completed` (EndOfMibView, a v1 `noSuchName`, an empty varbind
list, or the cursor leaving the `--start-oid` subtree). **Ctrl-C is a first-class
exit**: the current record is flushed, a summary with `end_reason: interrupted` is
written, and the process exits 0. Because every record is flushed as it is produced, a
crash or interrupt leaves a valid, readable (possibly truncated) trace.

## What is implemented, and what is not

Implemented today:

- **SNMP v2c** (GetBulk), **v1** (GetNext; end-of-MIB via `noSuchName`), and **v3**
  `noAuthNoPriv` and `authNoPriv` with USM auth protocols MD5, SHA-1, and SHA-256
  (RFC 7860 HMAC-SHA-256-192), including engine discovery.
- `--community` as a CLI flag (default `public`) — parity with `snmpbulkwalk -c` won
  over the original never-a-CLI-argument rule.
- `-v/--verbose` counting flag (WARNING → INFO → DEBUG) to stderr; the `\r` progress
  line shows only at default verbosity. Log lines obey trace privacy (never values,
  never the community string).

Not implemented (the format leaves room; the tooling does not emit or accept these):

- **SNMPv3 privacy (authPriv)** — `--priv-proto`/`--priv-pass` are parsed but warn and
  are ignored. Full priv requires storing decrypted PDU bytes and is format-v2/reuse
  territory.
- **System-OID allowlist** (`system_info` records for sysDescr/sysObjectID/sysUpTime).
  The format and the record builder support it; the walk tool does not emit it and has
  no `--hide-system-info` approval flow. (A consumer may still display `system_info`
  records from traces produced by other means.)
- **`show` subcommand** — a trace is `zcat`/`jq`-readable, so this stayed post-MVP.
- **Settings-matrix CLI, multiple `--start-oid`, `--resume`** — one walk per
  invocation; the trace schema is one-walk-per-file and the format reserves
  `settings.resume_from` for a future resume.
- **Interactive community prompt.**

Known limitation, deliberately current behavior rather than a defect: oidtrace
authenticates its own outgoing v3 requests but **does not verify inbound response
authenticity** — a response signed with the wrong key is still accepted. It is a
diagnostic tracer, not a security client. This is pinned by a `known-limitation`
scenario in `tests/robot/spec_rfc7860.robot`.

## Out of scope

- **SNMPv3 privacy** as above; when it arrives the plan is to reuse an existing
  USM/crypto implementation below our own message layer rather than hand-rolling key
  localization and DES/AES.
- **Recording SNMP values in any form** — the sole acknowledged exception is the
  (not-yet-emitted) system-OID allowlist. Unparseable packets are recorded as markers
  (decode error + datagram length), never as bytes.
- **Emulation and analysis products** (device-profile fitting, an adaptive settings
  finder, a viewer) are separate components that *consume* this trace format. Note the
  scope line: a profile fitted from traces reproduces protocol behavior and timing,
  **not values**, so it cannot stand in for the device against value-parsing consumers.

## Tests

The living specification is the Robot Framework suite under `tests/robot/`
(`spec_cli.robot`, `spec_rfc3416.robot`, `spec_rfc3414.robot`, `spec_rfc7860.robot`,
`spec_crash_safety.robot`), which drives the `oidtrace` binary via subprocess against
an in-process quirk emulator — so the spec is language-agnostic and any conforming
reimplementation passes. **Prefer a `spec_*.robot` scenario for any claim with an
externally observable effect** through the CLI/emulator boundary, even for internal
machinery; reserve pytest for claims that are structurally impossible to observe that
way (the Hypothesis-driven codec fuzzing of the never-raises decoder contract is the
one such case here).

- `just test` — fast pytest layers (unit + loopback-UDP integration).
- `just robot` — the living-spec suite (fast tier; excludes `reference_tools`).
- `just robot-reference` — reference-tool scenarios that cross-check against net-snmp.
- `just ci` — `lint types deadcode test robot`, the required gate.
- `just cov` — branch coverage; `just test-all` runs everything and hard-fails when
  reference tools are missing.
